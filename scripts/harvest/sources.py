"""Bibliographic and patent sources, behind one interface.

Every source returns the same envelope and the same normalized record shape, so
downstream stages never branch on where a record came from. The envelope
carries a typed `code` (see cache.SOURCE_CODES) because "the query ran and
found nothing" and "the query never ran" must stay distinguishable all the way
into the coverage report.

Identifiers — DOIs, patent numbers, years, journal names — come from these APIs
and only from these APIs. The LLM is never asked to produce one. That single
rule removes the highest-severity class of fabrication outright.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse

from . import cache

CONTACT = os.environ.get("CONTACT_EMAIL", "research@example.org")

OPENALEX_SELECT = ",".join([
    "id", "doi", "title", "publication_year", "type", "primary_location",
    "open_access", "best_oa_location", "authorships", "abstract_inverted_index",
    "cited_by_count", "language",
])


def _clean_doi(doi: str | None) -> str:
    if not doi:
        return ""
    d = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d.strip()


def work_id(rec: dict) -> str:
    """Stable id so resume survives a re-harvest from a different source."""
    if rec.get("doi"):
        return "doi:" + _clean_doi(rec["doi"])
    if rec.get("source") == "openalex" and rec.get("source_id"):
        return "openalex:" + str(rec["source_id"]).rsplit("/", 1)[-1]
    if rec.get("pmcid"):
        return "epmc:" + rec["pmcid"]
    import hashlib
    norm = re.sub(r"\W+", " ", (rec.get("title") or "")).strip().lower()
    return "title:" + hashlib.sha1(norm.encode()).hexdigest()[:12]


def _authors_str(names: list[str], limit: int = 6) -> str:
    if not names:
        return ""
    if len(names) <= limit:
        return "; ".join(names)
    return "; ".join(names[:limit]) + f"; et al. (+{len(names) - limit})"


class Source:
    """Base interface. Subclasses raise RuntimeError from __init__ if unusable."""

    name = "base"
    kind = "work"

    def search(self, query: str, *, limit: int = 200, cursor: str | None = None) -> dict:
        raise NotImplementedError

    def _ok(self, query: str, records: list[dict], next_cursor: str | None = None,
            total: int | None = None) -> dict:
        return {"source": self.name, "query": query, "success": True,
                "code": "ok" if records else "empty", "records": records,
                "next_cursor": next_cursor, "total": total, "error": None}

    def _fail(self, query: str, code: str, detail: str) -> dict:
        return {"source": self.name, "query": query, "success": False, "code": code,
                "records": [], "next_cursor": None, "total": None, "error": detail}


class OpenAlexSource(Source):
    """Primary discovery.

    Uses `title_and_abstract.search` with explicit boolean operators, never the
    bare `search=` parameter: measured during planning, `search=` returned 2000+
    largely irrelevant hits where the filtered form returned 61 on-topic ones.
    Commas are stripped from queries because OpenAlex reads a comma as a filter
    separator, which would silently truncate the query.
    """

    name = "openalex"

    def search(self, query: str, *, limit: int = 200, cursor: str | None = None) -> dict:
        q = query.replace(",", " ")
        params = {
            "filter": f"title_and_abstract.search:{q}",
            "per-page": str(min(limit, 200)),
            "cursor": cursor or "*",
            "select": OPENALEX_SELECT,
            "mailto": CONTACT,
        }
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params, safe=':()"|')
        res = cache.fetch_json(url, source=self.name, ttl_days=14)
        if res["code"] != "ok" or not res.get("data"):
            return self._fail(query, res["code"], res.get("error") or "no data")
        data = res["data"]
        records = [self._norm(w) for w in data.get("results", [])]
        return self._ok(query, records,
                        next_cursor=(data.get("meta") or {}).get("next_cursor"),
                        total=(data.get("meta") or {}).get("count"))

    @staticmethod
    def _abstract(inverted: dict | None) -> str:
        if not inverted:
            return ""
        positions: list[tuple[int, str]] = []
        for word, idxs in inverted.items():
            for i in idxs:
                positions.append((i, word))
        if not positions:
            return ""
        positions.sort()
        return " ".join(w for _, w in positions)

    def _norm(self, w: dict) -> dict:
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        best = w.get("best_oa_location") or {}
        oa = w.get("open_access") or {}
        authors = [
            (a.get("author") or {}).get("display_name", "")
            for a in (w.get("authorships") or [])
        ]
        rec = {
            "kind": "work",
            "source": self.name,
            "source_id": (w.get("id") or "").rsplit("/", 1)[-1],
            "doi": _clean_doi(w.get("doi")),
            "title": (w.get("title") or "").strip(),
            "abstract": self._abstract(w.get("abstract_inverted_index")),
            "year": w.get("publication_year"),
            "venue": src.get("display_name") or "",
            "type": w.get("type") or "",
            "authors": [a for a in authors if a],
            "oa_status": oa.get("oa_status") or "",
            "oa_url": best.get("landing_page_url") or oa.get("oa_url") or "",
            "pdf_url": best.get("pdf_url") or "",
            "url": (w.get("doi") or loc.get("landing_page_url") or ""),
            "cited_by": w.get("cited_by_count") or 0,
        }
        rec["work_id"] = work_id(rec)
        return rec


class CrossrefSource(Source):
    """Metadata truth: the reference string and DOI verification come from here."""

    name = "crossref"

    def search(self, query: str, *, limit: int = 100, cursor: str | None = None) -> dict:
        params = {"query.bibliographic": query, "rows": str(min(limit, 100)),
                  "mailto": CONTACT, "select":
                  "DOI,title,author,issued,container-title,type,volume,page,article-number,abstract"}
        if cursor:
            params["cursor"] = cursor
        else:
            params["cursor"] = "*"
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
        res = cache.fetch_json(url, source=self.name, ttl_days=14)
        if res["code"] != "ok" or not res.get("data"):
            return self._fail(query, res["code"], res.get("error") or "no data")
        msg = res["data"].get("message", {})
        records = [self._norm(it) for it in msg.get("items", [])]
        return self._ok(query, records, next_cursor=msg.get("next-cursor"),
                        total=msg.get("total-results"))

    def by_doi(self, doi: str) -> dict | None:
        """Authoritative metadata for one DOI. Also the existence check."""
        url = f"https://api.crossref.org/works/{urllib.parse.quote(_clean_doi(doi))}"
        res = cache.fetch_json(url + f"?mailto={CONTACT}", source=self.name, ttl_days=None)
        if res["code"] != "ok" or not res.get("data"):
            return None
        return self._norm(res["data"].get("message", {}))

    @staticmethod
    def _year(item: dict) -> int | None:
        for key in ("issued", "published-print", "published-online", "created"):
            parts = ((item.get(key) or {}).get("date-parts") or [[None]])[0]
            if parts and parts[0]:
                return parts[0]
        return None

    def _norm(self, item: dict) -> dict:
        authors = [
            " ".join(x for x in [a.get("given"), a.get("family")] if x)
            for a in (item.get("author") or [])
        ]
        abstract = re.sub(r"<[^>]+>", " ", item.get("abstract") or "")
        rec = {
            "kind": "work",
            "source": self.name,
            "source_id": item.get("DOI", ""),
            "doi": _clean_doi(item.get("DOI")),
            "title": (item.get("title") or [""])[0].strip(),
            "abstract": re.sub(r"\s+", " ", abstract).strip(),
            "year": self._year(item),
            "venue": (item.get("container-title") or [""])[0],
            "type": item.get("type") or "",
            "authors": [a for a in authors if a],
            "volume": item.get("volume") or "",
            "pages": item.get("page") or item.get("article-number") or "",
            "oa_status": "", "oa_url": "", "pdf_url": "",
            "url": f"https://doi.org/{_clean_doi(item.get('DOI'))}" if item.get("DOI") else "",
        }
        rec["work_id"] = work_id(rec)
        return rec

    @staticmethod
    def reference_string(rec: dict) -> str:
        """Author-year-title-journal string. Built from API fields only."""
        authors = rec.get("authors") or []
        if not authors:
            who = "[No author listed]"
        elif len(authors) == 1:
            who = authors[0]
        elif len(authors) == 2:
            who = f"{authors[0]} & {authors[1]}"
        else:
            who = f"{authors[0]} et al."
        bits = [f"{who} ({rec.get('year') or 'n.d.'})", rec.get("title") or "[No title]"]
        venue = rec.get("venue") or ""
        if venue:
            vol = rec.get("volume") or ""
            pages = rec.get("pages") or ""
            tail = venue + (f", {vol}" if vol else "") + (f", {pages}" if pages else "")
            bits.append(tail)
        return ". ".join(b.rstrip(".") for b in bits if b) + "."


class EuropePMCSource(Source):
    """Discovery plus the highest-value open full text (JATS XML)."""

    name = "epmc"
    BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    def search(self, query: str, *, limit: int = 100, cursor: str | None = None) -> dict:
        params = {"query": query, "format": "json", "pageSize": str(min(limit, 100)),
                  "resultType": "core", "cursorMark": cursor or "*"}
        url = f"{self.BASE}/search?" + urllib.parse.urlencode(params)
        res = cache.fetch_json(url, source=self.name, ttl_days=14)
        if res["code"] != "ok" or not res.get("data"):
            return self._fail(query, res["code"], res.get("error") or "no data")
        data = res["data"]
        records = [self._norm(r) for r in (data.get("resultList") or {}).get("result", [])]
        nxt = data.get("nextCursorMark")
        return self._ok(query, records,
                        next_cursor=nxt if nxt != cursor else None,
                        total=data.get("hitCount"))

    def full_text(self, pmcid: str) -> str:
        res = cache.fetch(f"{self.BASE}/{pmcid}/fullTextXML", source=self.name, ttl_days=None)
        return res["body"] if res["code"] == "ok" else ""

    def _norm(self, r: dict) -> dict:
        rec = {
            "kind": "work",
            "source": self.name,
            "source_id": r.get("id") or "",
            "doi": _clean_doi(r.get("doi")),
            "title": (r.get("title") or "").strip().rstrip("."),
            "abstract": (r.get("abstractText") or "").strip(),
            "year": int(r["pubYear"]) if str(r.get("pubYear", "")).isdigit() else None,
            "venue": r.get("journalTitle") or "",
            "type": (r.get("pubType") or "").split(";")[0].strip(),
            "authors": [a.strip() for a in (r.get("authorString") or "").split(",") if a.strip()],
            "pmcid": r.get("pmcid") or "",
            "oa_status": "gold" if r.get("isOpenAccess") == "Y" else "",
            "oa_url": "", "pdf_url": "",
            "has_full_text": r.get("hasTextMinedTerms") == "Y" or r.get("inEPMC") == "Y",
            "url": f"https://europepmc.org/article/{r.get('source','MED')}/{r.get('id','')}",
        }
        rec["work_id"] = work_id(rec)
        return rec


class UnpaywallSource(Source):
    """OA location lookup for DOIs where OpenAlex has none."""

    name = "unpaywall"

    def best_oa(self, doi: str) -> dict | None:
        url = (f"https://api.unpaywall.org/v2/{urllib.parse.quote(_clean_doi(doi))}"
               f"?email={urllib.parse.quote(CONTACT)}")
        res = cache.fetch_json(url, source=self.name, ttl_days=30)
        if res["code"] != "ok" or not res.get("data"):
            return None
        d = res["data"]
        best = d.get("best_oa_location") or {}
        return {"is_oa": bool(d.get("is_oa")), "oa_status": d.get("oa_status") or "",
                "pdf_url": best.get("url_for_pdf") or "",
                "landing_url": best.get("url_for_landing_page") or ""}


class TavilySource(Source):
    """Web search and page extraction.

    Two roles: gap-filling for grey literature and commercial/regulatory pages,
    and — importantly — fetching patent pages, because Google Patents blocks
    this IP directly but Tavily's own crawler reaches it fine.

    Auth is the Bearer header. The legacy `api_key`-in-body form now returns
    HTTP 432. Keys rotate on the codes that mean "this key is spent".
    """

    name = "tavily"
    ROTATE = {401, 402, 403, 429, 432, 433}

    def __init__(self) -> None:
        raw = os.environ.get("TAVILY_API_KEYS") or os.environ.get("TAVILY_API_KEY") or ""
        self.keys = [k.strip() for k in raw.split(",") if k.strip()]
        if not self.keys:
            raise RuntimeError("TAVILY_API_KEYS not set")
        self.ki = 0

    def _post(self, path: str, payload: dict, ttl_days: float | None) -> dict:
        body = json.dumps(payload).encode("utf-8")
        last = {"code": "key_exhausted", "status": 0, "body": "", "error": "all keys spent"}
        for _ in range(len(self.keys)):
            key = self.keys[self.ki]
            res = cache.fetch_json(
                f"https://api.tavily.com/{path}", source=self.name, method="POST", body=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                ttl_days=ttl_days, retries=1,
            )
            if res["code"] == "ok":
                return res
            last = res
            if res["status"] in self.ROTATE:
                self.ki = (self.ki + 1) % len(self.keys)
                continue
            break
        return last

    def search(self, query: str, *, limit: int = 8, cursor: str | None = None) -> dict:
        res = self._post("search", {"query": query, "max_results": min(limit, 20),
                                    "search_depth": "basic"}, ttl_days=None)
        if res["code"] != "ok" or not res.get("data"):
            return self._fail(query, res["code"], res.get("error") or "no data")
        records = [{"kind": "web", "source": self.name, "title": r.get("title", ""),
                    "url": r.get("url", ""), "snippet": r.get("content", ""),
                    "rank": i}
                   for i, r in enumerate(res["data"].get("results", []))]
        return self._ok(query, records)

    def extract(self, url: str) -> str:
        """Full page text via Tavily's crawler. The patent-text workhorse."""
        res = self._post("extract", {"urls": [url]}, ttl_days=None)
        if res["code"] != "ok" or not res.get("data"):
            return ""
        results = res["data"].get("results") or []
        return results[0].get("raw_content", "") if results else ""


class GooglePatentsSource(Source):
    """Patent discovery via the undocumented XHR endpoint.

    Paced hard and single-threaded on purpose: this endpoint blocked our IP
    during planning after roughly six rapid requests, and stayed blocked
    through four rounds of exponential backoff. Everything is cached forever so
    a re-run never re-queries. When it does block, `patents.py` falls back to
    Tavily site-restricted search rather than reporting an empty landscape.
    """

    name = "gpatents"
    kind = "patent"

    def search(self, query: str, *, limit: int = 10, cursor: str | None = None) -> dict:
        page = int(cursor) if cursor and str(cursor).isdigit() else 0
        inner = "q=" + urllib.parse.quote(query, safe="")
        if page:
            inner += f"&page={page}"
        url = "https://patents.google.com/xhr/query?url=" + urllib.parse.quote(inner, safe="")
        res = cache.fetch_json(
            url, source=self.name, ttl_days=None,
            headers={"Accept": "application/json", "Referer": "https://patents.google.com/"},
        )
        if res["code"] != "ok" or not res.get("data"):
            return self._fail(query, res["code"], res.get("error") or "blocked or no data")
        results = (res["data"].get("results") or {})
        clusters = results.get("cluster") or []
        records: list[dict] = []
        for cl in clusters:
            for item in cl.get("result") or []:
                records.append(self._norm(item))
        total = results.get("total_num_results")
        pages = results.get("total_num_pages") or 0
        nxt = str(page + 1) if page + 1 < pages else None
        return self._ok(query, records, next_cursor=nxt, total=total)

    @staticmethod
    def _strip(s: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()

    def _norm(self, item: dict) -> dict:
        p = item.get("patent") or {}
        pubnum = p.get("publication_number") or ""
        return {
            "kind": "patent",
            "source": self.name,
            "pub_number": pubnum,
            "gp_id": item.get("id") or "",
            "title": self._strip(p.get("title")),
            "snippet": self._strip(p.get("snippet")),
            "assignee": self._strip(p.get("assignee")),
            "inventor": self._strip(p.get("inventor")),
            "priority_date": p.get("priority_date") or "",
            "filing_date": p.get("filing_date") or "",
            "grant_date": p.get("grant_date") or "",
            "publication_date": p.get("publication_date") or "",
            "pdf": p.get("pdf") or "",
            "url": f"https://patents.google.com/patent/{pubnum}/en" if pubnum else "",
        }


_REGISTRY = {
    "openalex": OpenAlexSource,
    "crossref": CrossrefSource,
    "epmc": EuropePMCSource,
    "unpaywall": UnpaywallSource,
    "tavily": TavilySource,
    "gpatents": GooglePatentsSource,
}


def make_source(kind: str) -> Source:
    if kind not in _REGISTRY:
        raise ValueError(f"unknown source {kind!r}; have {sorted(_REGISTRY)}")
    return _REGISTRY[kind]()


def available(kinds: list[str]) -> dict[str, Source]:
    """Instantiate what we can; a missing key disables a source, never crashes."""
    out: dict[str, Source] = {}
    for k in kinds:
        try:
            out[k] = make_source(k)
        except Exception as e:
            print(f"  ! source {k} unavailable: {e}")
    return out
