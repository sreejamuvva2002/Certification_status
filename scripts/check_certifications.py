"""Research certification status for each GNEM company/facility record using real web
evidence (gathered via a search backend) judged by a LOCAL LLM, and emit one structured
16-column table plus a rich CSV.

Flow per record (gather-then-extract — economical on search credits):
  1. GATHER: a few broad searches (--max-queries, default 4) covering the main cert families
     (ISO 9001, IATF 16949, ISO 14001/45001/27001, AS9100, TISAX, UL/CE/RoHS/REACH, ...),
     then open the strongest few result pages directly (--fetch-pages).
  2. EXTRACT: ONE model call turns that evidence into a JSON array of certification rows,
     each with the full research schema below.

Per certification the model extracts (see TABLE_COLS / TABLE_PROMPT):
    cert_status         confirmed_active | active_expiry_unknown | confirmed_expired |
                        company_claim_only | parent_only | affiliate_only | historical_only |
                        unclear | conflicting | not_found_after_search | search_failed
    facility_status     facility_confirmed | facility_not_confirmed | parent_only |
                        affiliate_only | unclear | not_applicable
    certification_body, reference_no, issue_date, expiry_date, scope, source_type,
    source_url, evidence_quote, confidence (high|medium|low), notes  — all verbatim, never invented.

Outputs:
    outputs/certification_table.md       the single 16-column research table (primary deliverable)
    outputs/certification_status.csv     same rows as CSV (resumable, keyed on record_no)
    outputs/evidence_log.jsonl           raw evidence text per record (audit trail)

Search backends:
    --backend tavily   Tavily API (needs TAVILY_API_KEYS/TAVILY_API_KEY); reliable, rotates keys
    --backend browser  browser-use/browser-harness driving your real Chrome via CDP
    --backend http     plain HTTPS DuckDuckGo (anti-bot; often IP-blocked from datacenters)
    --backend auto     Tavily if a key is set, else browser, else http   [default]

Duplicate GNEM names are kept as separate records (see extract_companies.py --keep-duplicates);
the sheet's location/address are UNVERIFIED hints, flagged as such in the model prompt.

Usage:
    python scripts/check_certifications.py --limit 3          # smoke test (auto backend)
    python scripts/check_certifications.py                    # full 205-record run
"""
from __future__ import annotations

import argparse
import csv
import html as html_lib
import http.cookiejar
import json
import random
import re
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import llm_client  # noqa: E402

DEFAULT_COMPANIES = PKG_ROOT / "data" / "companies.csv"
DEFAULT_OUT = PKG_ROOT / "outputs" / "certification_status.csv"
DEFAULT_LOG = PKG_ROOT / "outputs" / "evidence_log.jsonl"
DEFAULT_TABLE = PKG_ROOT / "outputs" / "certification_table.md"

# Certifications commonly held by automotive/manufacturing companies — used as hints in
# the discovery prompt so the model recognizes them, NOT as a hard limit: the model is
# told to report ANY certification it finds evidence of, listed here or not.
KNOWN_CERTS = [
    "ISO 9001", "IATF 16949", "ISO/TS 16949", "ISO 14001", "ISO 45001", "ISO 50001",
    "ISO/IEC 27001", "TISAX", "ISO 13485", "ISO/IEC 17025", "AS9100", "VDA 6.3",
    "FSSC 22000", "ISO 22000", "C-TPAT", "AEO", "MMOG/LE", "UL", "CE marking",
    "RoHS", "REACH", "EPA", "CARB", "ITAR registration",
    "MBE/WBE/DBE (minority/women/disadvantaged business)", "OSHA VPP",
]

# --- DuckDuckGo request identity & pacing -------------------------------------
# DDG's html endpoint serves an anti-bot "anomaly" page (HTTP 202 / no results) to bare
# clients. A POST carrying a real browser User-Agent plus Referer/Origin gets genuine
# results. DDG also rate-limits per IP, so we pace requests and back off on throttle.
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DDG_HTML = "https://html.duckduckgo.com/html/"

DDG_MIN_INTERVAL = 5.0        # min seconds between DDG requests (see --ddg-min-interval)
DDG_MAX_RETRIES = 3           # backoff attempts on throttle (see --ddg-max-retries)
_DDG_BACKOFFS = (20, 45, 90)  # seconds to wait before each successive retry

# One cookie-jar-backed opener reused for every DDG hit, so a session's cookies carry
# forward like a browser would.
_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

_last_ddg_ts = 0.0

# --- Full 16-column research-table schema -------------------------------------
# TABLE_COLS are the human-facing columns (in order) rendered to the markdown table;
# OUT_FIELDS is the CSV schema (same columns + provenance).
TABLE_COLS = [
    ("record_no", "Record No."),
    ("company", "Company"),
    ("location", "Likely Georgia facility/location"),
    ("certification", "Certification / Standard"),
    ("cert_status", "Certification status"),
    ("facility_status", "Facility status"),
    ("certification_body", "Certification body / registrar"),
    ("reference_no", "Certificate number or reference"),
    ("issue_date", "Issue date"),
    ("expiry_date", "Expiry date"),
    ("scope", "Scope"),
    ("source_type", "Source type"),
    ("source_url", "Source URL"),
    ("evidence_quote", "Evidence quote"),
    ("confidence", "Confidence"),
    ("notes", "Notes"),
]
OUT_FIELDS = [c[0] for c in TABLE_COLS] + ["checked_at", "model", "backend"]

CERT_STATUSES = {
    "confirmed_active", "active_expiry_unknown", "confirmed_expired",
    "company_claim_only", "parent_only", "affiliate_only", "historical_only",
    "unclear", "conflicting", "not_found_after_search", "search_failed",
    "source_unavailable",
}
FACILITY_STATUSES = {
    "facility_confirmed", "facility_not_confirmed", "parent_only",
    "affiliate_only", "unclear", "not_applicable",
}
SOURCE_TYPES = {
    "registrar_database", "official_certificate_pdf", "company_certificate_pdf",
    "company_page", "government_database", "news_directory", "none",
}
CONFIDENCE_BANDS = {"high", "medium", "low"}

TABLE_PROMPT = """You are a certification-compliance analyst. You are given web search results \
and text extracted from source pages about ONE company/facility. Extract EVERY distinct \
certification or standard the evidence connects to this company — quality, environmental, \
safety, energy, security, automotive, product, or regulatory (ISO 9001, IATF 16949, ISO 14001, \
ISO 45001, ISO/TS 16949, AS9100, ISO 50001, ISO 17025, ISO 27001, TISAX, UL, CE, RoHS, REACH, \
EPA, CARB, and anything else present).

Respond with ONLY a JSON object, no prose:
{{"rows": [
  {{"certification": "<standard name incl. revision year if visible, e.g. ISO 14001:2015>",
    "cert_status": "<one of: confirmed_active | active_expiry_unknown | confirmed_expired | \
company_claim_only | parent_only | affiliate_only | historical_only | unclear | conflicting | \
not_found_after_search>",
    "facility_status": "<one of: facility_confirmed | facility_not_confirmed | parent_only | \
affiliate_only | unclear | not_applicable>",
    "certification_body": "<registrar/body name verbatim, e.g. DQS, DNV, TUV, SGS, BSI, or \"\">",
    "reference_no": "<certificate/registration number verbatim, or \"\">",
    "issue_date": "<issue date if visible, or \"\">",
    "expiry_date": "<expiry/valid-until date if visible, or \"\">",
    "scope": "<certificate scope text verbatim (trim to one line), or \"\">",
    "source_type": "<one of: registrar_database | official_certificate_pdf | \
company_certificate_pdf | company_page | government_database | news_directory>",
    "source_url": "<the single URL best supporting this row>",
    "evidence_quote": "<a short verbatim quote from the source supporting this row>",
    "confidence": "<high | medium | low>",
    "notes": "<brief caveat, e.g. 'parent org only', 'expiry not shown', or \"\">"}}
]}}

Evidence & status rules:
- Prefer the strongest source, in this order: registrar/certification-body database >
  official certificate PDF > company-hosted certificate PDF > company quality/ESG page >
  government/accreditation database > news/article/directory. Set source_type accordingly.
- cert_status: "confirmed_active" only with a certificate/registry entry showing it current WITH
  an expiry date. If a valid certificate is shown but NO expiry is visible, use
  "active_expiry_unknown". "company_claim_only" when only the company asserts it with no
  certificate/registry proof. "parent_only"/"affiliate_only" when only the parent org or a
  different affiliate is certified. "historical_only" for past/withdrawn. "confirmed_expired" when
  a shown expiry is in the past. "conflicting" when sources disagree. "unclear" when ambiguous.
- facility_status: mark "facility_confirmed" ONLY if a source names this Georgia facility, its
  Georgia city, its Georgia address, or a certified scope that clearly includes it. If only the
  parent/global org or an out-of-state/foreign site is certified, use "parent_only",
  "affiliate_only", or "facility_not_confirmed". Use "unclear" when the site is unstated.
- The company location/address provided is an UNVERIFIED hint; do not treat it as proof.
- Copy certificate numbers, dates, scope, registrar names, and quotes VERBATIM. NEVER fabricate
  any field — use "" when not visible.
- Company names collide; ignore evidence clearly about an unrelated company.
- If NO certification evidence is found for this company, return exactly one row with
  certification "none identified", cert_status "not_found_after_search",
  facility_status "not_applicable", confidence "low", and all other fields "".
"""


def _norm_row(raw: dict) -> dict:
    """Coerce one model-produced row into the table schema, clamping enums to the allowed sets."""
    def s(v: str) -> str:
        return str(v or "").strip()

    cert_status = s(raw.get("cert_status")).lower()
    if cert_status not in CERT_STATUSES:
        cert_status = "unclear"
    fac = s(raw.get("facility_status")).lower()
    if fac not in FACILITY_STATUSES:
        fac = "unclear"
    src = s(raw.get("source_type")).lower()
    if src not in SOURCE_TYPES:
        src = "none"
    conf = s(raw.get("confidence")).lower()
    if conf not in CONFIDENCE_BANDS:
        conf = "low"
    return {
        "certification": s(raw.get("certification")) or "none identified",
        "cert_status": cert_status,
        "facility_status": fac,
        "certification_body": s(raw.get("certification_body")),
        "reference_no": s(raw.get("reference_no")),
        "issue_date": s(raw.get("issue_date")),
        "expiry_date": s(raw.get("expiry_date")),
        "scope": s(raw.get("scope"))[:500],
        "source_type": src,
        "source_url": s(raw.get("source_url")),
        "evidence_quote": s(raw.get("evidence_quote"))[:500],
        "confidence": conf,
        "notes": s(raw.get("notes"))[:300],
    }


# ---------------------------------------------------------------- browsing backends

def _load_env():
    env = PKG_ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, val = line.split("=", 1)
                os.environ.setdefault(k.strip(), val.strip().strip('"').strip("'"))


def _strip_html(page: str, limit: int = 4000) -> str:
    page = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", page, flags=re.DOTALL | re.IGNORECASE)
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", page))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _pace_ddg() -> None:
    """Sleep so consecutive DDG requests stay at least DDG_MIN_INTERVAL apart (plus jitter)."""
    global _last_ddg_ts
    wait = DDG_MIN_INTERVAL + random.uniform(0, 3) - (time.monotonic() - _last_ddg_ts)
    if wait > 0:
        time.sleep(wait)
    _last_ddg_ts = time.monotonic()


def _ddg_post(query: str) -> tuple[int, str]:
    """POST the query to DDG with browser-like headers. Returns (http_status, body)."""
    data = urllib.parse.urlencode({"q": query, "kl": "us-en"}).encode()
    req = urllib.request.Request(DDG_HTML, data=data, headers={
        "User-Agent": BROWSER_UA,
        "Referer": "https://html.duckduckgo.com/",
        "Origin": "https://html.duckduckgo.com",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with _opener.open(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _is_anomaly(status: int, page: str, n_results: int) -> bool:
    """DDG throttle/anti-bot page: HTTP 202, or a result-less 200 carrying anomaly markers."""
    if status == 202:
        return True
    return n_results == 0 and bool(re.search(r"anomaly|challenge", page, re.IGNORECASE))


class HttpBackend:
    """DuckDuckGo HTML endpoint + plain page fetches. Headless-friendly."""
    name = "http"

    def search(self, query: str) -> tuple[str, list[str]]:
        for attempt in range(DDG_MAX_RETRIES + 1):
            _pace_ddg()
            status, page = _ddg_post(query)
            text, links = self._parse(page)
            if not _is_anomaly(status, page, len(links)):
                return text, links
            if attempt < DDG_MAX_RETRIES:
                wait = _DDG_BACKOFFS[min(attempt, len(_DDG_BACKOFFS) - 1)]
                print(f"[ddg] throttled (HTTP {status}) on {query!r}; backing off {wait}s "
                      f"(retry {attempt + 1}/{DDG_MAX_RETRIES})", file=sys.stderr)
                time.sleep(wait)
        print(f"[ddg] still throttled after {DDG_MAX_RETRIES} retries; giving up on {query!r}",
              file=sys.stderr)
        return "(search throttled)", []

    def fetch_page(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
        with _opener.open(req, timeout=30) as resp:
            return _strip_html(resp.read().decode("utf-8", errors="replace"))

    @staticmethod
    def _parse(page: str, max_results: int = 8) -> tuple[str, list[str]]:
        def clean(s: str) -> str:
            return html_lib.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()

        results, links = [], []
        # Each organic result sits in its own <div class="result ..."> block.
        for block in re.split(r'<div[^>]+class="[^"]*\bresult\b', page)[1:]:
            a = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                          block, flags=re.DOTALL)
            if not a:
                continue
            href, title = a.groups()
            snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, flags=re.DOTALL)
            # DDG wraps URLs as /l/?uddg=<encoded>
            m = re.search(r"uddg=([^&]+)", href)
            real = urllib.parse.unquote(m.group(1)) if m else href
            links.append(real)
            results.append(f"URL: {real}\nTITLE: {clean(title)}\n"
                           f"SNIPPET: {clean(snip.group(1)) if snip else ''}")
            if len(results) >= max_results:
                break
        return ("\n\n".join(results) if results else "(no search results)"), links


class BrowserBackend:
    """browser-use/browser-harness: drives your real Chrome over CDP."""
    name = "browser"

    def __init__(self):
        from browser_harness.admin import ensure_daemon
        from browser_harness import helpers
        ensure_daemon()
        self.bh = helpers
        self._tab_open = False

    def _goto(self, url: str) -> None:
        if not self._tab_open:
            self.bh.new_tab(url)
            self._tab_open = True
        else:
            self.bh.goto_url(url)
        self.bh.wait_for_load(timeout=20.0)

    def search(self, query: str) -> tuple[str, list[str]]:
        self._goto("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query))
        text = str(self.bh.js("document.body.innerText"))[:6000]
        raw = self.bh.js(
            "JSON.stringify([...document.querySelectorAll('a.result__a')]"
            ".slice(0,8).map(a=>a.href))")
        try:
            links = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:
            links = []
        return text, links

    def fetch_page(self, url: str) -> str:
        self._goto(url)
        text = str(self.bh.js("document.body.innerText"))
        return re.sub(r"\s+", " ", text).strip()[:4000]


TAVILY_URL = "https://api.tavily.com/search"


# Tavily HTTP statuses that mean "this key is spent / rejected" — rotate to the next key.
_TAVILY_ROTATE_CODES = {401, 402, 403, 429, 432, 433}


class TavilyBackend:
    """Tavily search API — built for programmatic/LLM use, so no per-IP anti-bot blocking
    like DuckDuckGo's. Reads one or more keys from TAVILY_API_KEYS (comma-separated) or a
    single TAVILY_API_KEY in .env, and rotates to the next key when one hits its usage limit.
    Result pages are still fetched directly (those sites don't block bare clients like DDG)."""
    name = "tavily"

    def __init__(self):
        raw = os.environ.get("TAVILY_API_KEYS") or os.environ.get("TAVILY_API_KEY") or ""
        self.keys = [k.strip() for k in raw.split(",") if k.strip()]
        if not self.keys:
            raise RuntimeError(
                "no Tavily key — set TAVILY_API_KEYS (comma-separated) or TAVILY_API_KEY in .env")
        self.ki = 0  # index of the key currently in use

    def _post(self, query: str, key: str) -> tuple[int, dict]:
        payload = json.dumps({
            "query": query,
            "max_results": 8,
            "search_depth": "basic",
        }).encode()
        req = urllib.request.Request(TAVILY_URL, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        })
        try:
            with _opener.open(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            return e.code, {"_error": body}
        except Exception as e:
            return 0, {"_error": f"{e.__class__.__name__}: {e}"}

    def search(self, query: str) -> tuple[str, list[str]]:
        # Try each key at most once per query; rotate past any that are exhausted/rejected.
        for _ in range(len(self.keys)):
            status, data = self._post(query, self.keys[self.ki])
            if status == 200:
                return self._parse(data)
            if status in _TAVILY_ROTATE_CODES:
                print(f"[tavily] key #{self.ki + 1}/{len(self.keys)} returned HTTP {status} "
                      f"({data.get('_error', '')[:80]}); rotating to next key", file=sys.stderr)
                self.ki = (self.ki + 1) % len(self.keys)
                continue
            print(f"[tavily] HTTP {status} on {query!r}: {data.get('_error', '')[:120]}",
                  file=sys.stderr)
            return "(search failed)", []
        print(f"[tavily] all {len(self.keys)} keys exhausted on {query!r}", file=sys.stderr)
        return "(search failed)", []

    @staticmethod
    def _parse(data: dict) -> tuple[str, list[str]]:
        results, links = [], []
        for r in data.get("results", []):
            url = r.get("url", "")
            if not url:
                continue
            links.append(url)
            results.append(f"URL: {url}\nTITLE: {r.get('title', '')}\n"
                           f"SNIPPET: {r.get('content', '')}")
        return ("\n\n".join(results) if results else "(no search results)"), links

    def fetch_page(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
        with _opener.open(req, timeout=30) as resp:
            return _strip_html(resp.read().decode("utf-8", errors="replace"))


def make_backend(kind: str):
    if kind == "http":
        return HttpBackend()
    if kind == "tavily":
        return TavilyBackend()
    if kind == "browser":
        return BrowserBackend()
    # auto: prefer Tavily if a key is configured (most reliable), else browser, else plain HTTP.
    if (os.environ.get("TAVILY_API_KEYS") or os.environ.get("TAVILY_API_KEY") or "").strip():
        try:
            b = TavilyBackend()
            print("[backend] using Tavily search API")
            return b
        except Exception as e:
            print(f"[backend] Tavily unavailable ({e}); trying browser/http")
    try:
        b = BrowserBackend()
        print("[backend] using browser-harness (real Chrome via CDP)")
        return b
    except Exception as e:
        print(f"[backend] browser-harness unavailable ({e.__class__.__name__}: {e}); "
              f"falling back to plain HTTP search")
        return HttpBackend()


# ---------------------------------------------------------------- evidence gathering

# Prefer registrar/registry pages when deciding which result links to open.
REGISTRY_HINTS = ("dqs", "tuv", "sgs", "bsi", "bureauveritas", "intertek", "certcheck",
                  "iatfglobaloversight", "iaf", "certificate", "certification", "cert")


# ---------------------------------------------------------------- pipeline

def build_queries(company: dict, max_queries: int) -> list[str]:
    """A small, budget-conscious set of broad searches covering the main cert families."""
    name = company["company"]
    city = (company.get("location", "") or "").split(",")[0].strip()
    qs = [
        f'"{name}" certifications ISO IATF certificate quality management',
        f'"{name}" "ISO 9001" OR "IATF 16949" OR "ISO 14001" certificate registrar',
        f'"{name}" "ISO 45001" OR "ISO 27001" OR "AS9100" OR "TISAX" certificate',
        f'"{name}" {city} Georgia certificate certification body'.replace("  ", " "),
    ]
    return qs[: max(1, max_queries)]


def research_company(backend, company: dict, model: str | None, fetch_pages: int,
                     max_queries: int) -> tuple[list[dict], str, bool]:
    """Gather evidence from a few searches (+ direct page fetches), then extract the full
    certification table in ONE model call. Returns (normalized_rows, evidence_text, search_ok)."""
    parts, all_links, search_ok = [], [], False
    for q in build_queries(company, max_queries):
        text, links = backend.search(q)
        if links:
            search_ok = True
        parts.append(f"SEARCH {q!r}:\n{text}")
        all_links.extend(links)

    # Open a few strongest pages (registrar/certificate/PDF links first), deduped and capped.
    seen, ranked = set(), []
    for u in sorted(all_links, key=lambda u: 0 if any(h in u.lower() for h in REGISTRY_HINTS) else 1):
        if u not in seen:
            seen.add(u)
            ranked.append(u)
    for url in ranked[: fetch_pages]:
        try:
            parts.append(f"PAGE {url}:\n{backend.fetch_page(url)}")
        except Exception as e:
            parts.append(f"PAGE {url}: (fetch failed: {e})")
    evidence = "\n\n".join(parts)

    def _fallback(status: str, note: str) -> list[dict]:
        row = _norm_row({})
        row.update(certification="none identified", cert_status=status,
                   facility_status="not_applicable", confidence="low", notes=note)
        return [row]

    if not search_ok and not ranked:
        return _fallback("search_failed", "search returned no results / all keys exhausted"), evidence, False

    hint = ", ".join(filter(None, [company.get("location", ""), company.get("address", ""),
                                   company.get("industry_group", "")]))
    user = (f"Company: {company['company']}\n"
            f"Unverified Georgia location/address hint (may be wrong): {hint or 'none'}\n\n"
            f"Evidence:\n{evidence[:14000]}")
    raw = llm_client.chat(
        [{"role": "system", "content": TABLE_PROMPT},
         {"role": "user", "content": user}],
        model=model,
    )
    try:
        rows = llm_client.extract_json(raw).get("rows", [])
    except ValueError:
        rows = []
    norm = [_norm_row(r) for r in rows if isinstance(r, dict) and str(r.get("certification", "")).strip()]
    if not norm:
        return _fallback("not_found_after_search", "no certifications identified in evidence"), evidence, search_ok
    return norm, evidence, search_ok


def _md_cell(s: str) -> str:
    return str(s or "").replace("|", "\\|").replace("\n", " ").strip() or "—"


def write_table(out_md: Path, rows: list[dict]) -> Path:
    """Render every row into the single 16-column markdown research table."""
    header = "| " + " | ".join(label for _, label in TABLE_COLS) + " |"
    sep = "| " + " | ".join("---" for _ in TABLE_COLS) + " |"
    lines = [header, sep]
    for r in rows:
        lines.append("| " + " | ".join(_md_cell(r.get(k, "")) for k, _ in TABLE_COLS) + " |")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_md


def load_done(out_path: Path) -> dict[str, list[dict]]:
    """record_no -> its already-written rows, so a re-run resumes instead of repeating."""
    if not out_path.exists():
        return {}
    done: dict[str, list[dict]] = {}
    with out_path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            done.setdefault(str(r.get("record_no", "")), []).append(r)
    return done


def main() -> None:
    global DDG_MIN_INTERVAL, DDG_MAX_RETRIES
    _load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="rich CSV (one row per cert)")
    ap.add_argument("--table", type=Path, default=DEFAULT_TABLE, help="16-column markdown table")
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--backend", choices=["auto", "tavily", "browser", "http"], default="auto")
    ap.add_argument("--model", default=None, help="override LLM_MODEL env var")
    ap.add_argument("--limit", type=int, default=0, help="only process first N records (0 = all)")
    ap.add_argument("--max-queries", type=int, default=4,
                    help="broad searches per company (default 4; each is ~1 Tavily credit)")
    ap.add_argument("--fetch-pages", type=int, default=3,
                    help="how many top result pages to open per company (default 3; 0 = snippets only)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between companies (be polite)")
    ap.add_argument("--ddg-min-interval", type=float, default=DDG_MIN_INTERVAL,
                    help=f"min seconds between DuckDuckGo requests (default {DDG_MIN_INTERVAL})")
    ap.add_argument("--ddg-max-retries", type=int, default=DDG_MAX_RETRIES,
                    help=f"backoff retries when DDG throttles a query (default {DDG_MAX_RETRIES})")
    ap.add_argument("--fresh", action="store_true", help="ignore existing results and start over")
    args = ap.parse_args()

    DDG_MIN_INTERVAL = args.ddg_min_interval
    DDG_MAX_RETRIES = args.ddg_max_retries

    if not llm_client.ping():
        raise SystemExit(
            f"Local LLM server not reachable at {llm_client.DEFAULT_BASE_URL}.\n"
            f"Start it first, e.g.:  ollama serve")

    if not args.companies.exists():
        raise SystemExit(f"{args.companies} not found — run scripts/extract_companies.py first.")
    with args.companies.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))
    if args.limit:
        companies = companies[: args.limit]

    backend = make_backend(args.backend)
    model = args.model or os.environ.get("LLM_MODEL") or llm_client.DEFAULT_MODEL

    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = {} if args.fresh else load_done(args.out)
    mode = "w" if (args.fresh or not args.out.exists()) else "a"
    out_f = args.out.open(mode, newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=OUT_FIELDS)
    if mode == "w":
        writer.writeheader()
    log_f = args.log.open("w" if args.fresh else "a", encoding="utf-8")

    all_rows: list[dict] = []
    try:
        for ci, comp in enumerate(companies, 1):
            rec = str(comp.get("record_no", ci))
            label = f"[{ci}/{len(companies)}] #{rec} {comp['company']}"
            if rec in done:
                all_rows.extend(done[rec])
                print(f"{label}: already done ({len(done[rec])} rows), skipping")
                continue
            try:
                rows, evidence, _ = research_company(
                    backend, comp, model, args.fetch_pages, args.max_queries)
            except Exception as e:
                fb = _norm_row({})
                fb.update(certification="none identified", cert_status="search_failed",
                          facility_status="not_applicable", notes=f"pipeline error: {e}")
                rows, evidence = [fb], f"(error: {e})"
                print(f"{label}: ERROR {e}")
            checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            for r in rows:
                r.update(record_no=rec, company=comp["company"],
                         location=comp.get("location", "") or comp.get("address", ""),
                         checked_at=checked_at, model=model, backend=backend.name)
                writer.writerow({k: r.get(k, "") for k in OUT_FIELDS})
                all_rows.append(r)
            out_f.flush()
            log_f.write(json.dumps({"record_no": rec, "company": comp["company"],
                                    "n_rows": len(rows), "evidence": evidence[:6000]}) + "\n")
            log_f.flush()
            summary = ", ".join(f"{r['certification']}={r['cert_status']}" for r in rows[:6])
            print(f"{label}: {len(rows)} cert row(s) -> {summary}")
            time.sleep(args.delay)
    finally:
        out_f.close()
        log_f.close()

    write_table(args.table, all_rows)
    try:
        import render_pages
        pages_dir = args.out.parent / "companies"
        n_pages = render_pages.render(args.out, args.companies, pages_dir)
        print(f"Per-company pages: {n_pages} in {pages_dir}/")
    except Exception as e:
        print(f"(page rendering skipped: {e})")
    print(f"\nDone. Table: {args.table}\nRich CSV: {args.out}\nEvidence log: {args.log}")


if __name__ == "__main__":
    main()
