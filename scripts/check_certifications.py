"""Check certification status for each company using web evidence judged by a LOCAL LLM,
and write ONE PAGE PER COMPANY covering all certifications found.

Flow per company (discover-then-verify, so we catch as many certifications as possible):
  1. DISCOVERY: one search asking which certifications this company appears to hold at all
     (ISO 14001, ISO 45001, ISO 50001, ISO 27001, AS9100, VDA 6.3, C-TPAT, MBE, ... —
     open-ended, not limited to a fixed list). Skip with --no-discover.
  2. VERIFY: each discovered certification, plus the always-checked core list
     (--cert, default ISO 9001:2015 + IATF 16949:2016), gets its own evidence search
     and a structured verdict. Capped at --max-certs per company.

Per company+certification the model extracts:
    org_status          confirmed_active | likely_active | confirmed_inactive | not_found
    facility_status     confirmed_facility | different_facility | unknown_facility
    certification_body  e.g. DQS, TUV, SGS ("" if unknown)
    reference_no        certificate/registration number ("" if unknown)
    scope               certificate scope text ("" if unknown)
    expiry_date         ISO date if visible, else ""
and the script derives final_label (e.g. "confirmed_active_facility / active_expiry_unknown").

Outputs:
    outputs/certification_status.csv     flat summary (one row per company+cert, resumable)
    outputs/evidence_log.jsonl           raw search/page text per verdict (audit trail)
    outputs/companies/<company>.md       one page per company, all certs, in the agreed format

Browsing backends:
    --backend browser  browser-use/browser-harness driving your real Chrome via CDP
    --backend http     plain HTTPS (DuckDuckGo HTML endpoint + page fetches), headless-friendly
    --backend auto     try browser, fall back to http   [default]

The sheet's location/address are UNVERIFIED hints: never added to search queries unless
you pass --use-location, and flagged as unverified in the LLM prompt.

Usage:
    python scripts/check_certifications.py --limit 3 --backend http     # smoke test
    python scripts/check_certifications.py --backend browser            # full run
    python scripts/check_certifications.py --cert "ISO 14001" --cert "ISO 9001:2015"
"""
from __future__ import annotations

import argparse
import csv
import html as html_lib
import json
import re
import os
import sys
import time
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
DEFAULT_PAGES_DIR = PKG_ROOT / "outputs" / "companies"
DEFAULT_CERTS = ["ISO 9001:2015", "IATF 16949:2016"]

# Certifications commonly held by automotive/manufacturing companies — used as hints in
# the discovery prompt so the model recognizes them, NOT as a hard limit: the model is
# told to report ANY certification it finds evidence of, listed here or not.
KNOWN_CERTS = [
    "ISO 9001", "IATF 16949", "ISO 14001", "ISO 45001", "ISO 50001", "ISO/IEC 27001",
    "ISO 13485", "ISO/IEC 17025", "AS9100", "VDA 6.3", "FSSC 22000", "ISO 22000",
    "C-TPAT", "AEO", "MMOG/LE", "UL certification", "CE marking", "ITAR registration",
    "MBE/WBE/DBE (minority/women/disadvantaged business)", "OSHA VPP",
]

OUT_FIELDS = [
    "company", "certification",
    # Research outcome first: whether we were able to look at all, and how well.
    "certification_status", "research_status", "evidence_sufficiency",
    "org_status", "facility_status", "final_label",
    "certification_body", "reference_no", "scope", "expiry_date",
    "confidence", "evidence", "source_url", "evidence_chars", "usable_sources",
    "checked_at", "model", "backend",
]

ORG_STATUSES = {"confirmed_active", "likely_active", "confirmed_inactive", "not_found"}
FACILITY_STATUSES = {"confirmed_facility", "different_facility", "unknown_facility"}

# What we claim about the certification itself. Kept strictly separate from
# research_status: a failed search says nothing about whether the cert exists.
#   certified              - valid evidence confirms certification
#   not_certified          - authoritative evidence explicitly says not certified (rare)
#   not_found_after_search - search worked, sources examined, no reliable evidence
#   unknown                - research could not be completed; NOT a claim about the company
CERTIFICATION_STATUSES = {"certified", "not_certified", "not_found_after_search", "unknown"}

# Why research ended the way it did.
RESEARCH_OK = "completed"
RESEARCH_FAILURES = {
    "search_failed",          # discovery/verification backend returned no usable results
    "no_usable_sources",      # search returned, but nothing openable/relevant
    "insufficient_evidence",  # sources retrieved but too thin to judge
    "verification_failed",    # candidate evidence existed, retrieval failed
    "model_unparseable",      # LLM did not return usable JSON
}

# Minimum real evidence characters before the extraction LLM is called at all.
MIN_EVIDENCE_CHARS = 400

# Text that looks like content but carries no evidence. Excluded from the
# evidence-character count so error pages can never satisfy the gate.
NOISE_PATTERNS = (
    r"\(?search failed[^)\n]*\)?", r"\(?fetch failed[^)\n]*\)?",
    r"\(no search results\)", r"search results failed to load",
    r"urlopen error[^\n]*", r"timed out", r"HTTP Error \d+[^\n]*",
    r"\b\d{3} (?:Forbidden|Not Found|Bad Gateway|Service Unavailable)\b",
    r"captcha", r"verify (?:you are|that you are) (?:a )?human",
    r"unusual traffic", r"enable javascript", r"javascript is required",
    r"loading\.{0,3}", r"please wait while", r"access denied",
    r"your request has been blocked", r"robot check",
)

SYSTEM_PROMPT = """You are a compliance analyst. You are given web search results (and text \
from certificate-registry pages) about ONE company, and must extract its status for ONE \
specific certification.

Respond with ONLY a JSON object, no prose, exactly this shape:
{"org_status": "confirmed_active" | "likely_active" | "confirmed_inactive" | "not_found",
 "facility_status": "confirmed_facility" | "different_facility" | "unknown_facility",
 "certification_body": "<registrar name, e.g. DQS, TUV, SGS, BSI, or empty string>",
 "reference_no": "<certificate or registration number, or empty string>",
 "scope": "<certificate scope text, or empty string>",
 "expiry_date": "<expiry/valid-until date if visible, or empty string>",
 "confidence": <float 0.0-1.0>,
 "evidence": "<one sentence citing the strongest evidence>",
 "source_url": "<the single URL best supporting the verdict, or empty string>"}

Rules:
- org_status "confirmed_active": a registrar, certificate directory, or the company's own site
  explicitly shows a current certificate for this certification.
- "likely_active": credible secondary mentions (press releases, supplier directories) without
  direct certificate evidence.
- "confirmed_inactive": explicit evidence the certificate is withdrawn/expired/never held.
- "not_found": no relevant evidence, or results are about a different company.
- facility_status "confirmed_facility": evidence ties the certificate to the specific facility/
  address given. "different_facility": the certificate is clearly for another site of the same
  organization. "unknown_facility": evidence does not say which site.
- The location/address given for the company is an UNVERIFIED hint and may be wrong — never
  downgrade org_status because a result shows a different city.
- Company names collide; ignore results clearly about unrelated companies.
- Copy reference numbers, scope, dates, and registrar names VERBATIM from the evidence. Never
  invent them; use empty strings when not visible.
"""


DISCOVER_PROMPT = """You are a compliance analyst. You are given web search results about ONE \
company. List EVERY certification, standard registration, or accreditation the evidence \
suggests this company holds or has held — quality, environmental, safety, energy, security, \
supply-chain, industry-specific, diversity, anything.

Common examples (do NOT limit yourself to these): {known}

Respond with ONLY a JSON object, no prose:
{{"certifications": ["<name 1>", "<name 2>", ...]}}

Rules:
- Include a certification only if the results actually mention it in connection with THIS
  company (ignore results about unrelated companies with similar names).
- Use the standard name, with the revision year if visible (e.g. "ISO 14001:2015").
- Empty list if nothing is found.
"""


def _cert_key(cert: str) -> str:
    """Canonical key for dedup: 'ISO 9001:2015' == 'iso 9001' == 'ISO9001'."""
    return re.sub(r"[^a-z0-9]+", "", cert.split(":")[0].lower())


def discover_certs(backend, company: dict, model: str | None, fetch_pages: int) -> list[str]:
    """One discovery search per company: which certifications is there any evidence for?"""
    query = f'"{company["company"]}" certifications ISO certificate quality'
    ev = gather_evidence(backend, query, fetch_pages)
    # Discovery only needs search text, not opened pages, so no source requirement.
    failure = gate_evidence(ev, require_sources=False)
    if failure:
        return [], failure
    raw = llm_client.chat(
        [{"role": "system", "content": DISCOVER_PROMPT.format(known=", ".join(KNOWN_CERTS))},
         {"role": "user", "content": f"Company: {company['company']}\n\nSearch results:\n{ev['text'][:12000]}"}],
        model=model,
    )
    try:
        found = llm_client.extract_json(raw).get("certifications", [])
    except ValueError:
        found = []
    return [str(c).strip() for c in found if str(c).strip()], None


def derive_final_label(v: dict) -> str:
    org = v.get("org_status", "not_found")
    fac = v.get("facility_status", "unknown_facility")
    if org == "not_found":
        return "not_found"
    if org == "confirmed_inactive":
        return "confirmed_inactive"
    base = {
        ("confirmed_active", "confirmed_facility"): "confirmed_active_facility",
        ("confirmed_active", "different_facility"): "confirmed_active_other_facility",
        ("confirmed_active", "unknown_facility"): "confirmed_active_org",
        ("likely_active", "confirmed_facility"): "likely_active_facility",
        ("likely_active", "different_facility"): "likely_active_other_facility",
        ("likely_active", "unknown_facility"): "likely_active_org",
    }[(org, fac)]
    expiry = (v.get("expiry_date") or "").strip()
    suffix = f"active_until_{expiry}" if expiry else "active_expiry_unknown"
    return f"{base} / {suffix}"


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


UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")


class SearchBackend:
    """Base: every backend returns the same normalized response shape.

        {"query": str, "backend": str, "success": bool,
         "results": [{"title": str, "url": str, "snippet": str, "rank": int}],
         "error": str | None}

    Keeping this uniform is what lets the pipeline treat provider choice as
    configuration rather than as a branch in the research logic.
    """
    name = "base"

    def search(self, query: str) -> dict:
        raise NotImplementedError

    def _ok(self, query, results):
        return {"query": query, "backend": self.name, "success": True,
                "results": results, "error": None}

    def _fail(self, query, error):
        return {"query": query, "backend": self.name, "success": False,
                "results": [], "error": str(error)}

    def fetch_page(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return _strip_html(resp.read().decode("utf-8", errors="replace"))


class BraveBackend(SearchBackend):
    """Brave Search API. Free tier covers this dataset; key via BRAVE_API_KEY."""
    name = "brave"
    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self):
        self.key = os.environ.get("BRAVE_API_KEY", "").strip()
        if not self.key:
            raise RuntimeError("BRAVE_API_KEY not set (add it to .env)")

    def search(self, query: str) -> dict:
        url = f"{self.ENDPOINT}?q={urllib.parse.quote(query)}&count=8"
        req = urllib.request.Request(url, headers={
            "Accept": "application/json", "X-Subscription-Token": self.key})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as e:
            return self._fail(query, f"{e.__class__.__name__}: {e}")
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""),
             "snippet": r.get("description", ""), "rank": i}
            for i, r in enumerate(data.get("web", {}).get("results", []), 1)
            if r.get("url")
        ]
        return self._ok(query, results)


class SerperBackend(SearchBackend):
    """Serper.dev — Google results via API. Key via SERPER_API_KEY."""
    name = "serper"
    ENDPOINT = "https://google.serper.dev/search"

    def __init__(self):
        self.key = os.environ.get("SERPER_API_KEY", "").strip()
        if not self.key:
            raise RuntimeError("SERPER_API_KEY not set (add it to .env)")

    def search(self, query: str) -> dict:
        req = urllib.request.Request(
            self.ENDPOINT,
            data=json.dumps({"q": query, "num": 8}).encode("utf-8"),
            headers={"X-API-KEY": self.key, "Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as e:
            return self._fail(query, f"{e.__class__.__name__}: {e}")
        results = [
            {"title": r.get("title", ""), "url": r.get("link", ""),
             "snippet": r.get("snippet", ""), "rank": i}
            for i, r in enumerate(data.get("organic", []), 1)
            if r.get("link")
        ]
        return self._ok(query, results)


class HttpBackend(SearchBackend):
    """DuckDuckGo HTML scraping. Fallback only — vulnerable to blocking and
    markup changes, and currently unreachable from some networks."""
    name = "duckduckgo"

    def search(self, query: str) -> dict:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                page = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            return self._fail(query, f"{e.__class__.__name__}: {e}")
        return self._ok(query, self._parse(page))

    @staticmethod
    def _parse(page: str, max_results: int = 8) -> list[dict]:
        def clean(s: str) -> str:
            return html_lib.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()

        results = []
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
            results.append({"title": clean(title), "url": real,
                            "snippet": clean(snip.group(1)) if snip else "",
                            "rank": len(results) + 1})
            if len(results) >= max_results:
                break
        return results


class BrowserBackend(SearchBackend):
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

    def search(self, query: str) -> dict:
        try:
            self._goto("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query))
            raw = self.bh.js(
                "JSON.stringify([...document.querySelectorAll('div.result')].slice(0,8)"
                ".map(d=>({title:(d.querySelector('a.result__a')||{}).innerText||'',"
                "url:(d.querySelector('a.result__a')||{}).href||'',"
                "snippet:(d.querySelector('.result__snippet')||{}).innerText||''})))")
            items = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception as e:
            return self._fail(query, f"{e.__class__.__name__}: {e}")
        results = [{**r, "rank": i} for i, r in enumerate(items, 1) if r.get("url")]
        return self._ok(query, results)

    def fetch_page(self, url: str) -> str:
        self._goto(url)
        text = str(self.bh.js("document.body.innerText"))
        return re.sub(r"\s+", " ", text).strip()[:4000]


BACKENDS = {"brave": BraveBackend, "serper": SerperBackend,
            "duckduckgo": HttpBackend, "http": HttpBackend, "browser": BrowserBackend}

# Preference order for --backend auto: API providers first, scraping last.
AUTO_ORDER = ["brave", "serper", "browser", "duckduckgo"]


def make_backend(kind: str):
    if kind != "auto":
        return BACKENDS[kind]()
    for name in AUTO_ORDER:
        try:
            b = BACKENDS[name]()
            print(f"[backend] using {name}")
            return b
        except Exception as e:
            print(f"[backend] {name} unavailable ({e})")
    raise SystemExit(
        "No search backend available. Set BRAVE_API_KEY or SERPER_API_KEY in .env "
        "(DuckDuckGo scraping is unreachable from this network).")


# ---------------------------------------------------------------- evidence gathering

# Prefer registrar/registry pages when deciding which result links to open.
REGISTRY_HINTS = ("dqs", "tuv", "sgs", "bsi", "bureauveritas", "intertek", "certcheck",
                  "iatfglobaloversight", "iaf", "certificate", "certification", "cert")


_NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)


def evidence_chars(text: str) -> int:
    """Count evidence characters, excluding error/boilerplate noise.

    A timeout message is not evidence. Neither is a CAPTCHA page or a
    "JavaScript required" notice — stripping them here is what stops an
    error string from satisfying the sufficiency gate downstream.
    """
    stripped = _NOISE_RE.sub(" ", text or "")
    # Drop our own scaffolding labels so they don't pad the count.
    stripped = re.sub(r"(SEARCH RESULTS for query .*?:|PAGE TEXT from \S+:)", " ", stripped)
    return len(re.sub(r"\s+", " ", stripped).strip())


def gather_evidence(backend, query: str, fetch_pages: int) -> dict:
    """Run one query and report what was actually obtained.

    Returns a structured result so callers can distinguish "we looked and found
    nothing" from "we were never able to look". Never raises for network faults.
    """
    ev = {"query": query, "search_ok": False, "usable_sources": 0,
          "text": "", "evidence_chars": 0, "error": None, "urls": []}
    try:
        resp = backend.search(query)
    except Exception as e:
        resp = {"success": False, "results": [], "error": f"{e.__class__.__name__}: {e}"}

    if not resp["success"]:
        ev["error"] = resp["error"]
        ev["text"] = f"(search failed: {ev['error']})"
        return ev

    # A search that returns but yields no organic results is a failed search,
    # not an empty world — challenge pages and blocked responses land here too.
    if not resp["results"]:
        ev["error"] = "search returned no parseable results"
        ev["text"] = f"(search failed: {ev['error']})"
        return ev

    links = [r["url"] for r in resp["results"]]
    search_text = "\n\n".join(
        f"URL: {r['url']}\nTITLE: {r['title']}\nSNIPPET: {r['snippet']}"
        for r in resp["results"])
    ev["search_ok"] = True
    parts = [f"SEARCH RESULTS for query {query!r}:\n{search_text}"]
    if fetch_pages and links:
        ranked = sorted(links, key=lambda u: 0 if any(h in u.lower() for h in REGISTRY_HINTS) else 1)
        for url in ranked[:fetch_pages]:
            try:
                page_text = backend.fetch_page(url)
            except Exception as e:
                parts.append(f"PAGE TEXT from {url}: (fetch failed: {e})")
                continue
            # Only count a source as usable if it carries real text.
            if evidence_chars(page_text) >= 200:
                ev["usable_sources"] += 1
                ev["urls"].append(url)
            parts.append(f"PAGE TEXT from {url}:\n{page_text}")
    ev["text"] = "\n\n".join(parts)
    ev["evidence_chars"] = evidence_chars(ev["text"])
    return ev


def gate_evidence(ev: dict, require_sources: bool) -> str | None:
    """Return a research-failure reason, or None if evidence is good enough to judge."""
    if not ev["search_ok"]:
        return "search_failed"
    if require_sources and ev["usable_sources"] == 0:
        return "no_usable_sources"
    if ev["evidence_chars"] < MIN_EVIDENCE_CHARS:
        return "insufficient_evidence"
    return None


def research_failure(company: str, cert: str, reason: str, ev: dict) -> dict:
    """A row recording that research did not complete — no claim about the company."""
    return {
        "company": company, "certification": cert,
        "certification_status": "unknown",
        "research_status": reason,
        "evidence_sufficiency": "insufficient",
        "org_status": "", "facility_status": "", "final_label": "",
        "certification_body": "", "reference_no": "", "scope": "", "expiry_date": "",
        "confidence": "", "evidence": f"research incomplete: {reason}"
                                      + (f" ({ev['error']})" if ev.get("error") else ""),
        "source_url": "", "evidence_chars": ev.get("evidence_chars", 0),
        "usable_sources": ev.get("usable_sources", 0),
    }


# ---------------------------------------------------------------- pipeline

def classify(company: dict, cert: str, evidence_text: str, model: str | None) -> dict:
    hint = ", ".join(filter(None, [company.get("location", ""), company.get("address", ""),
                                   company.get("industry_group", "")]))
    user = (
        f"Company: {company['company']}\n"
        f"Unverified location/address hints (may be wrong): {hint or 'none'}\n"
        f"Certification to assess: {cert}\n\n"
        f"Evidence:\n{evidence_text[:12000]}"
    )
    raw = llm_client.chat(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": user}],
        model=model,
    )
    try:
        verdict = llm_client.extract_json(raw)
    except ValueError:
        # The model failing to answer is a research failure, not a finding of
        # "no certification" — surface it as such rather than as not_found.
        return {"research_status": "model_unparseable",
                "certification_status": "unknown",
                "evidence": f"unparseable model output: {raw[:150]}"}
    if verdict.get("org_status") not in ORG_STATUSES:
        verdict["org_status"] = "not_found"
    if verdict.get("facility_status") not in FACILITY_STATUSES:
        verdict["facility_status"] = "unknown_facility"
    verdict["final_label"] = derive_final_label(verdict)
    verdict["research_status"] = RESEARCH_OK
    verdict["certification_status"] = derive_certification_status(verdict)
    return verdict


def derive_certification_status(v: dict) -> str:
    """Map the model's org_status onto a claim about the certification.

    Reached only when research completed, so 'not_found' here legitimately means
    'searched and found nothing' — distinct from the 'unknown' of a failed search.
    """
    org = v.get("org_status")
    if org in ("confirmed_active", "likely_active"):
        return "certified"
    if org == "confirmed_inactive":
        return "not_certified"
    return "not_found_after_search"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "company"


def write_company_page(pages_dir: Path, company: dict, rows: list[dict]) -> Path:
    """One page per company, in the agreed format, covering all certifications."""
    lines = [
        f"company: {company['company']}",
        f"facility: {company.get('location', '') or 'unknown (sheet hint missing)'}",
        f"address: {company.get('address', '') or 'unknown'}",
        "",
        "NOTE: facility/address above come from the source sheet and are unverified hints.",
        "",
    ]
    for r in rows:
        lines.append(f"{r['certification']}:")
        lines.append(f"  certification_status: {r['certification_status']}")
        lines.append(f"  research_status: {r['research_status']}")
        lines.append(f"  evidence_sufficiency: {r['evidence_sufficiency']}")
        if r["research_status"] != RESEARCH_OK:
            # Research did not complete: say so and claim nothing about the company.
            lines.append(f"  note: NO CONCLUSION — research did not complete. "
                         f"This is not evidence that the company lacks this certification.")
            lines.append(f"  detail: {r['evidence']}")
            lines.append("")
            continue
        lines.append(f"  org_status: {r['org_status']}")
        lines.append(f"  facility_status: {r['facility_status']}")
        lines.append(f"  final_label: {r['final_label']}")
        lines.append(f"  certification_body: {r['certification_body'] or 'not identified'}")
        lines.append(f"  reference_no: {r['reference_no'] or 'not visible in sources checked'}")
        lines.append(f"  scope: {r['scope'] or 'not visible in sources checked'}")
        lines.append(f"  expiry_date: {r['expiry_date'] or 'not visible in sources checked'}")
        lines.append(f"  confidence: {r['confidence']}")
        lines.append(f"  evidence: {r['evidence']}")
        lines.append(f"  source: {r['source_url'] or 'n/a'}")
        lines.append(f"  evidence_chars: {r['evidence_chars']}  "
                     f"usable_sources: {r['usable_sources']}")
        lines.append("")
    lines.append(f"checked_at: {rows[-1]['checked_at']}  model: {rows[-1]['model']}  "
                 f"backend: {rows[-1]['backend']}")
    pages_dir.mkdir(parents=True, exist_ok=True)
    path = pages_dir / f"{slugify(company['company'])}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def load_done(out_path: Path) -> dict[tuple[str, str], dict]:
    if not out_path.exists():
        return {}
    with out_path.open(newline="", encoding="utf-8") as f:
        return {(r["company"], r["certification"]): r for r in csv.DictReader(f)}


def search_cert_name(cert: str) -> str:
    """'ISO 9001:2015' -> 'ISO 9001' for the search query."""
    return cert.split(":")[0].strip()


def main() -> None:
    _load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--pages-dir", type=Path, default=DEFAULT_PAGES_DIR)
    ap.add_argument("--cert", action="append",
                    help=f"core certification(s) always checked (repeatable); default: {DEFAULT_CERTS}")
    ap.add_argument("--no-discover", action="store_true",
                    help="skip per-company discovery; check only the core --cert list")
    ap.add_argument("--max-certs", type=int, default=12,
                    help="cap on certifications verified per company (default 12)")
    ap.add_argument("--backend", choices=["auto", "brave", "serper", "browser", "duckduckgo", "http"],
                    default="auto", help="search provider (default auto: brave, serper, browser, duckduckgo)")
    ap.add_argument("--model", default=None, help="override LLM_MODEL env var")
    ap.add_argument("--limit", type=int, default=0, help="only process first N companies (0 = all)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between web requests (be polite)")
    ap.add_argument("--fetch-pages", type=int, default=2,
                    help="how many top result pages to open per query (default 2; 0 = snippets only)")
    ap.add_argument("--use-location", action="store_true",
                    help="include the sheet's location in the search query "
                         "(off by default: sheet locations may be wrong)")
    ap.add_argument("--fresh", action="store_true", help="ignore existing results and start over")
    ap.add_argument("--max-failure-rate", type=float, default=0.20,
                    help="abort if research failure rate exceeds this (default 0.20)")
    ap.add_argument("--min-source-rate", type=float, default=0.50,
                    help="abort if fewer than this fraction of checks yield a usable source "
                         "(default 0.50)")
    ap.add_argument("--health-after", type=int, default=10,
                    help="companies to process before health thresholds apply (default 10)")
    args = ap.parse_args()

    certs = args.cert or DEFAULT_CERTS

    if not llm_client.ping():
        raise SystemExit(
            f"Local LLM server not reachable at {llm_client.DEFAULT_BASE_URL}.\n"
            f"Start it first, e.g.:  ollama serve   (then: ollama pull qwen3:14b)")

    if not args.companies.exists():
        raise SystemExit(f"{args.companies} not found — run scripts/extract_companies.py first.")
    with args.companies.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))
    if args.limit:
        companies = companies[: args.limit]

    backend = make_backend(args.backend)
    # DEFAULT_MODEL is an import-time snapshot taken before _load_env() ran,
    # so read LLM_MODEL from the environment .env just populated.
    model = args.model or os.environ.get("LLM_MODEL") or llm_client.DEFAULT_MODEL

    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = {} if args.fresh else load_done(args.out)
    mode = "w" if (args.fresh or not args.out.exists()) else "a"
    out_f = args.out.open(mode, newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=OUT_FIELDS)
    if mode == "w":
        writer.writeheader()
    log_f = args.log.open("w" if args.fresh else "a", encoding="utf-8")

    n = 0
    attempted = failed = sourced = 0  # batch-health counters
    try:
        for ci, comp in enumerate(companies, 1):
            # Build this company's certification list: core certs + anything discovered.
            comp_certs = list(certs)
            if not args.no_discover:
                discovered, disc_failure = discover_certs(backend, comp, model, args.fetch_pages)
                if disc_failure:
                    print(f"[{ci}/{len(companies)}] {comp['company']}: "
                          f"discovery incomplete ({disc_failure}) — core certs only")
                seen_keys = {_cert_key(c) for c in comp_certs}
                extras = []
                for c in discovered:
                    k = _cert_key(c)
                    if k and k not in seen_keys:
                        seen_keys.add(k)
                        extras.append(c)
                comp_certs.extend(extras)
                if extras:
                    print(f"[{ci}/{len(companies)}] {comp['company']}: discovered "
                          f"{len(extras)} extra cert(s): {', '.join(extras)}")
                log_f.write(json.dumps({"company": comp["company"], "discovery": discovered}) + "\n")
                log_f.flush()
                time.sleep(args.delay)
            comp_certs = comp_certs[: args.max_certs]

            comp_rows = []
            for cert in comp_certs:
                n += 1
                key = (comp["company"], cert)
                if key in done:
                    comp_rows.append(done[key])
                    continue
                query = f'"{comp["company"]}" {search_cert_name(cert)} certificate'
                if args.use_location and comp.get("location"):
                    query += f' {comp["location"]}'
                ev = gather_evidence(backend, query, args.fetch_pages)
                # HARD GATE: the extraction model is never called on evidence that
                # cannot support a verdict. Failures propagate as 'unknown'.
                failure = gate_evidence(ev, require_sources=args.fetch_pages > 0)
                if failure:
                    row = research_failure(comp["company"], cert, failure, ev)
                    attempted += 1
                    failed += 1
                else:
                    verdict = classify(comp, cert, ev["text"], model)
                    attempted += 1
                    if verdict.get("research_status") != RESEARCH_OK:
                        row = research_failure(comp["company"], cert,
                                               verdict["research_status"], ev)
                        row["evidence"] = str(verdict.get("evidence") or "")[:500]
                        failed += 1
                    else:
                        row = {
                            "company": comp["company"],
                            "certification": cert,
                            "certification_status": verdict["certification_status"],
                            "research_status": RESEARCH_OK,
                            "evidence_sufficiency": "sufficient",
                            "org_status": verdict["org_status"],
                            "facility_status": verdict["facility_status"],
                            "final_label": verdict["final_label"],
                            "certification_body": str(verdict.get("certification_body") or ""),
                            "reference_no": str(verdict.get("reference_no") or ""),
                            "scope": str(verdict.get("scope") or "")[:500],
                            "expiry_date": str(verdict.get("expiry_date") or ""),
                            "confidence": verdict.get("confidence", ""),
                            "evidence": str(verdict.get("evidence") or "")[:500],
                            "source_url": str(verdict.get("source_url") or ""),
                            "evidence_chars": ev["evidence_chars"],
                            "usable_sources": ev["usable_sources"],
                        }
                        if ev["usable_sources"] > 0:
                            sourced += 1
                row.update({
                    "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "model": model,
                    "backend": backend.name,
                })
                writer.writerow(row)
                out_f.flush()
                log_f.write(json.dumps({"query": query, "evidence_text": ev["text"][:6000],
                                        "search_ok": ev["search_ok"], "urls": ev["urls"],
                                        **row}) + "\n")
                log_f.flush()
                comp_rows.append(row)
                label = row["final_label"] or row["research_status"]
                print(f"[company {ci}/{len(companies)} | check {n}] {comp['company']} | {cert} "
                      f"-> {row['certification_status']} / {label} ({row['confidence'] or '-'})")
                time.sleep(args.delay)
            if comp_rows:
                page = write_company_page(args.pages_dir, comp, comp_rows)
                print(f"    page: {page}")

            # Health check: stop early if the research backend is clearly unhealthy,
            # rather than emitting hundreds of well-formed but meaningless records.
            if ci >= args.health_after and attempted:
                fail_rate = failed / attempted
                source_rate = sourced / attempted
                if fail_rate > args.max_failure_rate:
                    raise SystemExit(
                        f"\nABORTED after {ci} companies: research failure rate "
                        f"{fail_rate:.0%} exceeds limit {args.max_failure_rate:.0%} "
                        f"({failed}/{attempted} checks failed).\n"
                        f"The search backend is unhealthy — fix it and re-run "
                        f"(completed rows are saved; resume picks up where this stopped).")
                if source_rate < args.min_source_rate:
                    raise SystemExit(
                        f"\nABORTED after {ci} companies: usable-source rate "
                        f"{source_rate:.0%} below minimum {args.min_source_rate:.0%} "
                        f"({sourced}/{attempted} checks had a retrievable source).\n"
                        f"Verdicts would rest on snippets alone — not reliable enough to continue.")
    finally:
        out_f.close()
        log_f.close()

    print(f"\nDone. Summary CSV: {args.out}\nPer-company pages: {args.pages_dir}/\n"
          f"Evidence log: {args.log}")


if __name__ == "__main__":
    main()
