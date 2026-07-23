"""Research verified Georgia location details for every GNEM company record from the web.

CLEAN-ROOM RESEARCH: the only inputs to the searches and to the model are the
company name and the state "Georgia". The source sheet's location/address are
NEVER shown to the model — they are treated as possibly-wrong hints and are only
compared against the verified result afterwards, in code. Where the hint
disagrees with the evidence, the row's Notes say so.

Flow per record (gather-then-extract, same shape as check_certifications.py):
  1. GATHER: several targeted searches (--max-queries, default 6) covering facility
     address, plant/county, economic-development announcements and lifecycle status,
     then open the strongest result pages (ranked by the source-priority ladder).
  2. EXTRACT: ONE model call turns that evidence into a JSON array of FACILITIES —
     a company with several Georgia sites yields one row per verified facility.

Table schema (15 columns, one row per verified facility):
    Record No. | Company | Verified facility name | Street address | City | County |
    State | ZIP code | Facility type | Operational status | Georgia facility? |
    Source URL | Evidence quote | Confidence | Notes

Outputs:
    outputs/locations_table.md          the 15-column table (primary deliverable)
    outputs/locations.csv               same rows + provenance (resumable, keyed on record_no)
    outputs/locations/<rec>_<slug>.md   ONE PAGE PER COMPANY, all its facilities
    outputs/location_evidence.jsonl     raw evidence text per record (audit trail)

Usage:
    python scripts/collect_locations.py --limit 3      # smoke test
    python scripts/collect_locations.py                # full 205-record run
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import check_certifications as cc  # noqa: E402  (backends, env loading, helpers)
import llm_client  # noqa: E402

DEFAULT_COMPANIES = PKG_ROOT / "data" / "companies.csv"
DEFAULT_OUT = PKG_ROOT / "outputs" / "locations.csv"
DEFAULT_TABLE = PKG_ROOT / "outputs" / "locations_table.md"
DEFAULT_LOG = PKG_ROOT / "outputs" / "location_evidence.jsonl"
DEFAULT_PAGES = PKG_ROOT / "outputs" / "locations"

# How much gathered evidence is handed to the model. The local model runs with a
# 262k-token context, so this is a cost/latency choice, not a model limit — it needs
# to be large enough that the later searches aren't simply truncated away.
# Sized so nothing is ever dropped: 3 pages x PAGE_CHARS + 6 searches x SEARCH_CHARS
# = 45,000 worst case, comfortably inside this. The model's context is 262k tokens, so
# the real cost of a bigger budget is latency, not capacity.
EVIDENCE_CHARS = 60000

# Per-query cap on raw search-snippet text. Without it six searches of eight results
# each fill the whole evidence budget and push the fetched pages — the strongest
# sources — out of the prompt entirely.
SEARCH_CHARS = 2500

# Per-page text kept. The shared helper defaults to 4,000 chars, which silently cuts
# a company "our locations" page off after the first plant or two — the exact page
# that must survive intact for multi-facility companies.
PAGE_CHARS = 10000

# How much evidence is written to the audit log per record.
LOG_CHARS = 60000

# --- output schema ------------------------------------------------------------
# TABLE_COLS is the exact 15-column deliverable; OUT_FIELDS adds provenance and the
# sheet-hint comparison, which live in the CSV only.
TABLE_COLS = [
    ("record_no", "Record No."),
    ("company", "Company"),
    ("facility_name", "Verified facility name"),
    ("street_address", "Street address"),
    ("city", "City"),
    ("county", "County"),
    ("state", "State"),
    ("zip", "ZIP code"),
    ("facility_type", "Facility type"),
    ("operational_status", "Operational status"),
    ("is_georgia", "Georgia facility?"),
    ("source_url", "Source URL"),
    ("evidence_quote", "Evidence quote"),
    ("confidence", "Confidence"),
    ("notes", "Notes"),
]
OUT_FIELDS = [c[0] for c in TABLE_COLS] + [
    "source_type", "sheet_location", "sheet_address", "hint_check",
    "category", "industry_group", "checked_at", "model", "backend"]

FACILITY_TYPES = {
    "manufacturing plant", "headquarters", "sales office", "distribution center",
    "warehouse", "r&d center", "cancelled project", "planned facility",
    "closed facility", "dealer/service location only", "unclear",
}
OPERATIONAL_STATUSES = {
    "operating", "planned", "under construction", "cancelled", "closed",
    "unclear", "no georgia facility found",
    # Evidence-collection failures. Kept distinct from "no georgia facility found",
    # which is a positive finding and must never be produced by a failed search.
    "search_failed", "source_unavailable",
}
# Statuses that mean "we could not look", not "we looked and found nothing".
FAILURE_STATUSES = {"search_failed", "source_unavailable"}

# A row only counts as a facility if a source verifies what the site actually DOES.
# "unclear" is not a function — a directory blurb saying a company is "based in
# Atlanta" describes no facility at all.
VERIFIED_FUNCTIONS = FACILITY_TYPES - {"unclear"}

# Sources strong enough to establish a facility on their own (the top of the ladder).
STRONG_SOURCES = {"company_website", "company_press_release",
                  "state_economic_development", "county_city_economic_development",
                  "sec_filing", "government_database"}
IS_GEORGIA = {"yes", "no", "unclear"}

# Source-priority ladder from the research spec (1 = strongest). Used both to rank
# which result pages get opened and to record what kind of source a row rests on.
SOURCE_TYPES = [
    "company_website", "company_press_release", "state_economic_development",
    "county_city_economic_development", "sec_filing", "government_database",
    "business_directory", "news_or_trade", "job_posting", "none",
]

# URL substrings mapped to their rung on that ladder, for link ranking.
_SOURCE_PATTERNS = [
    (2, ("georgia.org", "gov.georgia.gov", "georgia.gov")),
    (3, ("eda", "chamber", "developauthority", "economicdevelopment", "countyga", ".ga.us")),
    (4, ("sec.gov",)),
    (5, ("epa.gov", "osha.gov", "echo.epa.gov", "opencorporates", "sos.ga.gov",
         "ecorp.sos.ga.gov")),
    (6, ("thomasnet", "manta", "dnb.com", "industrynet", "bbb.org", "zoominfo",
         "buzzfile", "mapquest")),
    (7, ("news", "ajc.com", "bizjournals", "reuters", "prnewswire", "businesswire")),
    (8, ("indeed", "ziprecruiter", "glassdoor", "linkedin.com/jobs", "jobs.")),
]

LOCATION_PROMPT = """You verify the GEORGIA (U.S. state) facilities of ONE company from supplied \
web evidence. You never invent, infer, complete or correct an address.

Work in TWO STEPS inside one JSON object:

STEP 1 — "georgia_site_candidates": list EVERY distinct Georgia place the evidence associates \
with THIS company, before deciding anything. Include sites named only by city or plant name \
with no street address (e.g. "Dahlonega plant", a chamber-of-commerce listing, "<City> Plant" \
in a page title). List the city name for each. Be exhaustive — this is a recall step.

STEP 2 — "facilities": emit ONE ELEMENT PER CANDIDATE from step 1 that the evidence supports \
as a real site of this company. A candidate with no street address STILL becomes an element \
(street_address ""). Only leave a candidate out if the evidence shows it is not this \
company's site, and say so in the notes of another element.

Return EXACTLY ONE JSON object:

{
  "georgia_site_candidates": ["<city or site name>", ...],
  "facilities": [ ... ]
}

where each element of "facilities" is:

{
  "facility_name": "<verified facility/site name if the evidence gives one different from the \
company name, else \\"\\">",
  "street_address": "<street address verbatim from the evidence; \\"\\" if not stated>",
  "city": "<city>",
  "county": "<county, ONLY if the evidence states it; else \\"\\">",
  "state": "<GA for Georgia facilities; the actual state/country for non-Georgia ones>",
  "zip": "<ZIP code if stated; else \\"\\">",
  "facility_type": "<one of: manufacturing plant | headquarters | sales office | \
distribution center | warehouse | r&d center | cancelled project | planned facility | \
closed facility | dealer/service location only | unclear>",
  "operational_status": "<one of: operating | planned | under construction | cancelled | \
closed | unclear | no georgia facility found | source_unavailable>",
  "is_georgia": "<yes | no | unclear>",
  "source_type": "<one of: company_website | company_press_release | \
state_economic_development | county_city_economic_development | sec_filing | \
government_database | business_directory | news_or_trade | job_posting | none>",
  "source_url": "<URL of the source this row rests on>",
  "evidence_quote": "<verbatim span of the evidence supporting this facility>",
  "confidence": "<high | medium | low>",
  "notes": "<caveats: name collision, parent-only evidence, conflicting sources, etc.>"
}

RULES — follow exactly:
1. Do NOT hallucinate addresses. Report an address ONLY if it literally appears in the \
Evidence text. "evidence_quote" MUST be an exact substring of the Evidence.
2. Do NOT infer a Georgia facility merely because the company sells or ships products in \
Georgia.
3. Do NOT treat a dealership, distributor or sales office as a manufacturing plant unless the \
source clearly says so. Use "dealer/service location only" for those.
3b. A FACILITY MUST HAVE A VERIFIED FUNCTION. Only emit an element when a source shows what \
the site actually does — manufacturing plant, headquarters, warehouse, distribution center, \
r&d center, planned facility, closed facility, cancelled project, sales office or \
dealer/service location. A vague business-directory blurb such as "Acme Corp is a leading \
industrial company based in Atlanta, GA" verifies NO function and is NOT a facility: leave it \
out and mention it in another element's notes as an unverified lead. Reserve \
"facility_type": "unclear" for a site whose existence is well sourced but whose function \
genuinely is not stated — never as a way to include a weak directory mention.
4. ONE ELEMENT PER FACILITY — never merge or summarise. If the evidence shows several \
Georgia sites (a "our locations" page, several plant addresses, a plant plus a separate \
office or warehouse), emit a SEPARATE element for EVERY one of them. Never pick a single \
"main" or "best" site and drop the others. Two sites in the same city are still two \
elements. Listing fewer facilities than the evidence supports is an ERROR.
4b. PARTIAL LOCATIONS ARE STILL FACILITIES. If the evidence establishes a Georgia site but \
gives no street address (only a city, or only a county), STILL emit that element: set \
"street_address" to "", fill in whatever city/county IS supported, and state the limitation \
in notes (e.g. "city confirmed by <source>; no street address stated in any source checked"). \
Do not drop a real facility merely because its street address is missing.
5. Use "no georgia facility found" ONLY as a POSITIVE finding — the evidence affirmatively \
shows this company's sites are elsewhere. If the evidence is merely missing, thin, unusable \
or about a different company, use "unclear" (or "source_unavailable" when the sources could \
not be read) and say so in notes. NEVER report "no georgia facility found" just because the \
search returned little.
6. A facility announced but later cancelled -> "operational_status": "cancelled" and \
"facility_type": "cancelled project".
7. A facility planned or being built is NOT operating -> use "planned" or "under construction".
8. If only the PARENT company's location is found, do NOT assign it to a Georgia facility \
unless the source clearly connects the two; say so in notes.
9. "Georgia" means the U.S. STATE of Georgia (GA, USA), NEVER the country Georgia (Tbilisi, \
Kutaisi, +995 phone numbers). Ignore country-Georgia evidence entirely and note it.
10. Prefer the strongest source available, in this order: company official site > company \
press release > georgia.org / Governor's office / state economic development > county or city \
economic development > SEC filings > government databases (EPA TRI, OSHA, ECHO, \
OpenCorporates, GA Secretary of State) > business directories (D&B, ThomasNet, Manta, \
IndustryNet, chambers) > news/trade press > job postings (only if nothing stronger exists).
11. Report "county" when the evidence states it, including when it is stated indirectly — \
"Dahlonega-Lumpkin County Chamber of Commerce" establishes Lumpkin County, "X County \
Development Authority announced" establishes X County. Do NOT guess a county from a city name \
alone when no source mentions it; leave it "" in that case.
12. Company names collide. Use only evidence clearly about THIS company; if you cannot tell, \
say so in notes and lower the confidence.

Output the JSON object only. No commentary, no markdown fences."""

# Query patterns from the research spec. --max-queries takes the first N (default 6);
# each search costs roughly one Tavily credit per company.
QUERY_PATTERNS = [
    '"{name}" Georgia facility address',
    '"{name}" Georgia manufacturing plant county',
    '"{name}" Georgia location contact address',
    '"{name}" Georgia economic development plant announcement',
    '"{name}" Georgia plant closed OR cancelled OR planned OR "under construction"',
    '"{name}" Georgia address county ZIP',
    '"{name}" georgia.org project Georgia',
    '"{name}" OpenCorporates OR "Georgia Secretary of State"',
    '"{name}" "EPA TRI" OR OSHA OR ECHO Georgia',
    '"{name}" Georgia jobs facility hiring',
    '"{name}" "facility"',
    '"{name}" "plant"',
    '"{name}" "county"',
]


# --- address normalization / hint comparison ----------------------------------

_ABBREV = {
    "dr": "drive", "st": "street", "rd": "road", "hwy": "highway",
    "pkwy": "parkway", "pky": "parkway", "ste": "suite", "ave": "avenue",
    "av": "avenue", "blvd": "boulevard", "ln": "lane", "ct": "court",
    "cir": "circle", "pl": "place", "tpke": "turnpike", "trl": "trail",
    "n": "north", "s": "south", "e": "east", "w": "west",
    "ne": "northeast", "nw": "northwest", "se": "southeast", "sw": "southwest",
    "ga": "georgia",
}

# Legal suffixes stripped when deciding whether two GNEM records name the same company.
_LEGAL_SUFFIXES = {"inc", "llc", "corp", "corporation", "co", "company", "ltd",
                   "limited", "gmbh", "plc", "lp", "llp", "na", "usa", "america",
                   "north", "of"}


def _norm(s: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace, expand abbreviations."""
    toks = re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).split()
    return " ".join(_ABBREV.get(t, t) for t in toks)


def _norm_company(name: str) -> str:
    """Company name reduced to its distinctive tokens, for duplicate detection."""
    toks = [t for t in re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).split()
            if t not in _LEGAL_SUFFIXES]
    return " ".join(toks)


def _street_no(address: str) -> str:
    """Leading street number of an address ('100 Kautex Dr' -> '100'), else ''."""
    m = re.match(r"\s*(\d+)\b", str(address or ""))
    return m.group(1) if m else ""


def _sheet_city(address: str, location: str) -> str:
    """City from the sheet's '..., <city>, GA 30553' address, else from 'City, County'."""
    m = re.search(r",\s*([A-Za-z][A-Za-z .'\-]*?)\s*,\s*(?:GA|Georgia)\b",
                  str(address or ""), re.IGNORECASE)
    if m:
        return _norm(m.group(1))
    return _norm(str(location or "").split(",")[0])


def _sheet_county(location: str) -> str:
    """County from a 'City, Xxx County' sheet location, else ''."""
    m = re.search(r",\s*([A-Za-z][A-Za-z .'\-]*?)\s*County", str(location or ""),
                  re.IGNORECASE)
    return _norm(m.group(1)) if m else ""


def check_sheet_hint(rows: list[dict], sheet_addr: str, sheet_loc: str) -> str:
    """Compare the unverified sheet hint against every verified facility found.

    The model never sees the sheet, so this is the only place the two are related.
    Returns a short verdict used for the `hint_check` column and, when the hint looks
    wrong, folded into the row Notes (spec rule 4)."""
    if not (sheet_addr.strip() or sheet_loc.strip()):
        return "no_sheet_value: sheet had no location to check"

    # Evidence collection failed — say nothing about the hint either way.
    if all(r["operational_status"] in FAILURE_STATUSES for r in rows):
        return "unchecked: evidence collection failed, hint neither confirmed nor refuted"

    ga_rows = [r for r in rows if r["is_georgia"] == "yes" and (r["city"] or r["street_address"])]
    if not ga_rows:
        return "not_found: no Georgia facility verified on the web"

    s_city, s_no, s_county = (_sheet_city(sheet_addr, sheet_loc),
                              _street_no(sheet_addr), _sheet_county(sheet_loc))

    # The sheet's own city/county pairing is checkable on its own, independent of what
    # the web research found — e.g. it lists Pendergrass in Hall County, but Pendergrass
    # is in Jackson County. This is reported ALONGSIDE the city verdict, not instead of
    # it: a sheet row can have both a wrong county and a wrong city.
    ref = county_for(s_city)
    county_flag = ""
    if s_county and ref and not county_agrees(s_county, ref):
        county_flag = (f"sheet_county_wrong: sheet says {s_city.title()} is in "
                       f"{s_county.title()} County, but it is in {ref} County")

    def _verdict(v: str) -> str:
        return f"{county_flag}; {v}" if county_flag else v
    cities = [(_norm(r["city"]), _street_no(r["street_address"]), _norm(r["county"]))
              for r in ga_rows]

    for city, no, county in cities:
        if s_city and city and s_city == city:
            if s_no and no and s_no != no:
                return _verdict(f"partial_match: same city ({s_city}), different street "
                                f"number ({s_no} vs {no})")
            return _verdict(f"match: sheet city {s_city} confirmed")

    found = ", ".join(sorted({c for c, _, _ in cities if c})) or "unnamed sites"
    if s_city:
        return _verdict(f"mismatch: sheet says {s_city} but verified Georgia site(s) "
                        f"are in {found}")
    return _verdict(f"unclear: sheet city unparseable; verified site(s) in {found}")


# Words that precede a city in an address ("... Friendship Road Sylvania, GA") and must
# be trimmed off a captured place name.
_STREET_WORDS = {"road", "street", "drive", "avenue", "highway", "boulevard", "lane",
                 "parkway", "way", "court", "circle", "place", "trail", "suite", "rd",
                 "st", "dr", "ave", "hwy", "blvd", "ln", "pkwy", "ste", "north", "south",
                 "east", "west", "plant", "facility", "office", "inc", "llc", "corp"}


COUNTY_LOOKUP_PATH = PKG_ROOT / "data" / "ga_city_county.json"
_county_lookup: dict[str, str] | None = None


def county_for(city: str) -> str:
    """County for a Georgia city, from the cached authoritative city/county reference
    (see scripts/build_county_lookup.py). Returns '' for unknown/CDP place names."""
    global _county_lookup
    if _county_lookup is None:
        try:
            _county_lookup = json.loads(COUNTY_LOOKUP_PATH.read_text(encoding="utf-8"))
        except Exception:
            _county_lookup = {}
    return _county_lookup.get(str(city or "").strip().lower(), "")


def county_agrees(stated: str, reference: str) -> bool:
    """Whether a stated county is consistent with the reference value. A city can span
    several counties (Lavonia is 'Franklin/Hart'), so naming any one of them agrees."""
    if not stated or not reference:
        return True
    return _norm(stated) in {_norm(c) for c in reference.split("/")}


def _georgia_cities(evidence: str, company: str = "") -> set[str]:
    """Every 'City, GA'-style place name appearing in the evidence. Used only to warn
    that a multi-site company may have been collapsed — never to assert a facility."""
    drop = _STREET_WORDS | set(_norm_company(company).split())
    found = set()
    for m in re.finditer(r"([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+)?)\s*,\s*"
                         r"(?:GA|Georgia)\b", evidence):
        words = m.group(1).split()
        while words and words[0].lower().strip(".") in drop:
            words.pop(0)
        city = " ".join(words).strip()
        if len(city) > 2 and city.lower() not in drop:
            found.add(city)
    return found


def _grounded(address: str, evidence: str) -> bool:
    """True if the address actually appears in the gathered evidence. Guards against
    a model that produces a plausible-looking address no source ever stated."""
    if not address.strip():
        return True
    na, ne = _norm(address), _norm(evidence)
    if not na or na in ne:
        return True
    toks = na.split()
    return len(toks) >= 3 and " ".join(toks[:3]) in ne


# --- extraction ---------------------------------------------------------------

def _s(v) -> str:
    return str(v if v is not None else "").strip()


def _pick(value: str, allowed: set[str], default: str) -> str:
    v = _s(value).lower()
    return v if v in allowed else default


def _norm_row(raw: dict) -> dict:
    """Coerce one model facility object into the flat output schema."""
    row = {k: "" for k, _ in TABLE_COLS}
    row.update({f: "" for f in OUT_FIELDS if f not in row})
    state = _s(raw.get("state")) or ""
    if _norm(state) in ("georgia", "ga"):
        state = "GA"
    row.update(
        facility_name=_s(raw.get("facility_name")),
        street_address=_s(raw.get("street_address")),
        city=_s(raw.get("city")),
        county=re.sub(r"\s*county\s*$", "", _s(raw.get("county")), flags=re.IGNORECASE),
        state=state,
        zip=_s(raw.get("zip")),
        facility_type=_pick(raw.get("facility_type"), FACILITY_TYPES, "unclear"),
        operational_status=_pick(raw.get("operational_status"), OPERATIONAL_STATUSES, "unclear"),
        is_georgia=_pick(raw.get("is_georgia"), IS_GEORGIA, "unclear"),
        source_type=_pick(raw.get("source_type"), set(SOURCE_TYPES), "none"),
        source_url=_s(raw.get("source_url")),
        evidence_quote=_s(raw.get("evidence_quote"))[:600],
        confidence=_pick(raw.get("confidence"), cc.CONFIDENCE_BANDS, "low"),
        notes=_s(raw.get("notes"))[:400],
    )
    return row


def _source_rank(url: str, company: str) -> int:
    """Rung on the source-priority ladder (lower = stronger), for link ranking."""
    u = url.lower()
    # A domain carrying the company's distinctive tokens is treated as its own site,
    # the strongest source on the ladder.
    parts = u.split("/")
    domain = parts[2] if len(parts) > 2 else ""
    if domain and any(len(t) >= 5 and t in domain for t in _norm_company(company).split()):
        return 0
    for rank, pats in _SOURCE_PATTERNS:
        if any(p in u for p in pats):
            return rank
    return 6


def _fetch_text(backend, url: str) -> str:
    """Fetch a page as text, keeping PAGE_CHARS of it rather than the shared 4,000-char
    default. A company's "our locations" page listing every plant is precisely what must
    not be cut short. Falls back to the backend's own fetch (e.g. the browser backend)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": cc.BROWSER_UA})
        with cc._opener.open(req, timeout=30) as resp:
            return cc._strip_html(resp.read().decode("utf-8", errors="replace"),
                                  limit=PAGE_CHARS)
    except Exception:
        return backend.fetch_page(url)


def build_queries(company: dict, max_queries: int) -> list[str]:
    """Company name + the state only — deliberately no sheet city, so the search
    cannot be steered toward confirming whatever the spreadsheet already says."""
    name = company["company"]
    return [q.format(name=name) for q in QUERY_PATTERNS[: max(1, max_queries)]]


def _facility_key(row: dict) -> str:
    """Identity of a facility for merging passes: street number + city where both are
    known, else city + name, else whatever is left. Deliberately coarse — two passes
    describing the same plant must land on the same key."""
    city = _norm(row["city"])
    no = _street_no(row["street_address"])
    if city and no:
        return f"{city}|{no}"
    if city and row["facility_name"]:
        return f"{city}|{_norm(row['facility_name'])}"
    if city:
        return f"{city}|"
    return _norm(row["facility_name"] or row["street_address"] or row["notes"][:40])


def _completeness(row: dict) -> tuple[int, int]:
    """Rank a row for merging: how many fields it fills, then how confident it is."""
    filled = sum(1 for k in ("street_address", "city", "county", "zip", "facility_name",
                             "source_url", "evidence_quote") if row.get(k))
    conf = {"high": 2, "medium": 1, "low": 0}.get(row.get("confidence", "low"), 0)
    return filled, conf


def _merge_pass_rows(passes: list[list[dict]]) -> list[dict]:
    """Union the facilities found by each extraction pass.

    Recall, not consensus, is the goal: a plant that only one pass noticed is still a
    real plant, so it is kept — but marked, because a single-pass find is weaker
    evidence than one both passes agreed on. Where passes describe the same facility,
    the more complete/confident row wins field by field.
    """
    merged: dict[str, dict] = {}
    seen_in: dict[str, int] = {}
    for rows in passes:
        for row in rows:
            key = _facility_key(row)
            if not key:
                continue
            seen_in[key] = seen_in.get(key, 0) + 1
            if key not in merged:
                merged[key] = dict(row)
                continue
            best, other = merged[key], row
            if _completeness(other) > _completeness(best):
                best, other = other, best
            combined = dict(best)
            for field in ("street_address", "city", "county", "zip", "facility_name",
                          "source_url", "evidence_quote", "state"):
                if not combined.get(field) and other.get(field):
                    combined[field] = other[field]
            # Keep whichever pass made the more specific classification.
            for field in ("facility_type", "operational_status"):
                if combined.get(field) == "unclear" and other.get(field) not in ("", "unclear"):
                    combined[field] = other[field]
            if other.get("notes") and other["notes"] not in combined.get("notes", ""):
                combined["notes"] = "; ".join(filter(None, [combined.get("notes"),
                                                           other["notes"]]))[:600]
            merged[key] = combined

    n_passes = len(passes)
    out = []
    for key, row in merged.items():
        if n_passes > 1 and seen_in.get(key, 0) < n_passes:
            row["notes"] = "; ".join(filter(None, [
                row.get("notes"),
                f"found in only {seen_in[key]} of {n_passes} extraction passes — "
                f"weaker signal, worth a manual look"]))[:600]
        out.append(row)
    return out


def _reject_unverified_leads(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split rows into verified facilities and rejected leads.

    A facility row must rest on a source that verifies what the site DOES. A weak
    directory hit with no stated function ("based in Atlanta") is a lead, not a
    facility — but it is only demoted when a stronger, official source has actually
    established a facility for this company. When the weak hit is all there is, it is
    kept and flagged, so a thinly-documented company does not silently vanish."""
    has_strong = any(r["facility_type"] in VERIFIED_FUNCTIONS
                     and r["source_type"] in STRONG_SOURCES for r in rows)
    if not has_strong:
        for r in rows:
            if r["facility_type"] not in VERIFIED_FUNCTIONS:
                r["notes"] = "; ".join(filter(None, [
                    r["notes"],
                    # Deliberately avoids the wording _LEAD_CLAUSE strips: this row IS the
                    # company's only evidence, so the caveat has to survive on it.
                    "FUNCTION NOT STATED: no source describes what this site does; kept "
                    "because no stronger official source was found"]))[:600]
        return rows, []

    kept, rejected = [], []
    for r in rows:
        if r["facility_type"] in VERIFIED_FUNCTIONS or r["source_type"] in STRONG_SOURCES:
            kept.append(r)
        else:
            rejected.append(r)
    return (kept or rows), rejected


_SOURCE_WORDS = {
    "business_directory": "business-directory",
    "news_or_trade": "news/trade-press",
    "job_posting": "job-posting",
    "none": "unattributed",
}

# Note clauses that talk about a rejected lead. Leads are consolidated onto the first
# facility row, so any such clause elsewhere is a duplicate and gets stripped. The model
# writes these as multi-clause sentences ("Unverified lead for X...; no function
# verified."), so every fragment has to be matched or an orphan tail is left behind.
_LEAD_CLAUSE = re.compile(
    r"(?i)\blead\b|no function (was )?verified|function not verified"
    r"|directory blurb|only in a weak|no official source verified")


def _describe_lead(r: dict) -> str:
    """One consolidated sentence for a rejected lead, in the reviewer-facing wording."""
    where = f"{r['city']}, GA" if r["city"] else (r["street_address"] or "unnamed location")
    if r["city"] and r["street_address"]:
        where = f"{r['city']}, GA / {r['street_address']}"
    src = _SOURCE_WORDS.get(r["source_type"], r["source_type"] or "weak")
    return (f"Rejected/unverified lead: {where} appeared only in a weak {src} result; "
            f"no official source verified a facility function.")


def _describe_mentioned(city: str) -> str:
    """A place the evidence names but no row claims — a weaker signal than a rejected
    row, since nothing about it was ever extracted as a facility."""
    return (f"Rejected/unverified lead: {city}, GA is mentioned in the evidence but no "
            f"official source verified a facility function there.")


def _strip_lead_clauses(notes: str) -> str:
    """Remove lead mentions from a note so the consolidated version is the only one."""
    kept = [c for c in str(notes or "").split("; ") if c and not _LEAD_CLAUSE.search(c)]
    return "; ".join(kept)


def _extract_pass(evidence: str, company: dict, model: str | None
                  ) -> tuple[list[dict], list[str]] | None:
    """One extraction over the gathered evidence. Returns (rows, candidates), or None
    if the model produced nothing parseable."""
    user = (f"Company: {company['company']}\n"
            f"State to verify: Georgia, USA\n\n"
            f"Evidence:\n{evidence[:EVIDENCE_CHARS]}")
    raw = llm_client.chat(
        [{"role": "system", "content": LOCATION_PROMPT},
         {"role": "user", "content": user}],
        model=model,
    )
    try:
        parsed = llm_client.extract_json(raw)
    except ValueError:
        return None
    rows = [_norm_row(f) for f in parsed.get("facilities", []) if isinstance(f, dict)]
    rows = [r for r in rows if any(r[k] for k in
                                   ("street_address", "city", "facility_name", "notes"))]
    candidates = [_s(c) for c in (parsed.get("georgia_site_candidates") or []) if _s(c)]
    return rows, candidates


def research_location(backend, company: dict, model: str | None, fetch_pages: int,
                      max_queries: int, passes: int = 2) -> tuple[list[dict], str]:
    """Gather evidence, then extract every verified facility. The extraction runs
    `passes` times over the same evidence (no extra search cost) and the results are
    unioned, because a single pass intermittently misses a site it found last time.
    Returns (rows, evidence_text)."""
    search_parts, all_links, search_ok = [], [], False
    for q in build_queries(company, max_queries):
        text, links = backend.search(q)
        if links:
            search_ok = True
        search_parts.append(f"SEARCH {q!r}:\n{text[:SEARCH_CHARS]}")
        all_links.extend(links)

    # Open the strongest pages first, per the source-priority ladder.
    seen, ranked = set(), []
    for u in sorted(all_links, key=lambda u: _source_rank(u, company["company"])):
        if u not in seen:
            seen.add(u)
            ranked.append(u)
    page_parts = []
    for url in ranked[: fetch_pages]:
        try:
            page_parts.append(f"PAGE {url}:\n{_fetch_text(backend, url)}")
        except Exception as e:
            page_parts.append(f"PAGE {url}: (fetch failed: {e})")

    # Pages before snippets: if anything gets truncated it must be the weak sources,
    # never the company/registry pages that were deliberately opened.
    evidence = "\n\n".join(page_parts + search_parts)

    def _fallback(status: str, note: str) -> list[dict]:
        row = _norm_row({})
        row.update(operational_status=status, is_georgia="unclear", notes=note)
        return [row]

    if not search_ok and not ranked:
        # A failed search is not evidence of absence — never let it read as
        # "no georgia facility found".
        return _fallback("search_failed",
                         "search returned no results / all keys exhausted"), evidence

    pass_rows, candidates = [], []
    for _ in range(max(1, passes)):
        result = _extract_pass(evidence, company, model)
        if result is None:
            continue
        rows_i, cands_i = result
        if rows_i:
            pass_rows.append(rows_i)
        candidates.extend(cands_i)

    if not pass_rows:
        return _fallback("source_unavailable",
                         "no extraction pass returned usable facilities"), evidence

    rows = _merge_pass_rows(pass_rows)
    if not rows:
        return _fallback("unclear", "no facility identified in evidence"), evidence

    # Only sites with a verified function survive as facility rows; weak unclear hits
    # become recorded leads instead.
    rows, rejected = _reject_unverified_leads(rows)

    for r in rows:
        # Drop any address the evidence does not actually support, but KEEP the
        # facility row — a missing street address is a limitation, not a deletion.
        if not _grounded(r["street_address"], evidence):
            r["notes"] = (r["notes"] + "; " if r["notes"] else "") + \
                (f"street address {r['street_address']!r} was not supported by any source "
                 f"checked and has been removed; remaining location fields stand")
            r["street_address"] = ""
            r["confidence"] = "low"
        elif not r["street_address"] and r["is_georgia"] == "yes" and r["city"]:
            r["notes"] = (r["notes"] + "; " if r["notes"] else "") + \
                "city/county verified but no street address stated in any source checked"

    # A search that produced nothing usable must not read as a positive absence.
    if not search_ok:
        for r in rows:
            if r["operational_status"] == "no georgia facility found":
                r["operational_status"] = "search_failed"
                r["notes"] = (r["notes"] + "; " if r["notes"] else "") + \
                    "search failed — absence of a Georgia facility was NOT established"

    # Consolidate every unverified lead — rows the code rejected, plus Georgia places
    # the evidence or the model's own step-1 enumeration named that no row claims.
    # These all belong in ONE place: the first facility row. Any lead wording the model
    # scattered across other rows is stripped so a lead is stated exactly once.
    covered = {_norm(r["city"]) for r in rows if r["city"]}
    covered |= {_norm(r["facility_name"]) for r in rows if r["facility_name"]}
    covered |= {_norm(r["city"]) for r in rejected if r["city"]}

    def _uncovered(name: str) -> bool:
        n = _norm(name)
        return bool(n) and not any(n in c or c in n for c in covered if c)

    mentioned = {c for c in _georgia_cities(evidence, company["company"]) if _uncovered(c)}
    mentioned |= {c for c in candidates if _uncovered(c)}

    lead_notes = [_describe_lead(r) for r in rejected[:4]]
    lead_notes += [_describe_mentioned(c) for c in sorted(mentioned)[:4]]

    for r in rows:
        r["notes"] = _strip_lead_clauses(r["notes"])
    if lead_notes:
        rows[0]["notes"] = " ".join(filter(None, [rows[0]["notes"]] + lead_notes))[:900]
    return rows, evidence


# --- rendering ----------------------------------------------------------------

def write_table(out_md: Path, rows: list[dict]) -> Path:
    """Render every row into the single 15-column locations table."""
    header = "| " + " | ".join(label for _, label in TABLE_COLS) + " |"
    sep = "| " + " | ".join("---" for _ in TABLE_COLS) + " |"
    lines = [header, sep]
    for r in rows:
        lines.append("| " + " | ".join(cc._md_cell(r.get(k, "")) for k, _ in TABLE_COLS) + " |")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_md


PAGE_FIELDS = [
    ("street_address", "street_address"),
    ("city", "city"),
    ("county", "county"),
    ("state", "state"),
    ("zip", "zip"),
    ("facility_type", "facility_type"),
    ("operational_status", "operational_status"),
    ("is_georgia", "georgia_facility"),
    ("source_type", "source_type"),
    ("source_url", "source_url"),
    ("evidence_quote", "evidence_quote"),
    ("confidence", "confidence"),
    ("notes", "notes"),
]


def render_pages(rows: list[dict], pages_dir: Path) -> int:
    """One readable markdown page per GNEM record, listing every verified facility —
    the location counterpart of render_pages.py for certifications."""
    by_rec: dict[str, list[dict]] = {}
    for r in rows:
        by_rec.setdefault(str(r.get("record_no", "")), []).append(r)

    pages_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for rec, facs in by_rec.items():
        head = facs[0]
        lines = [
            f"company: {head.get('company', '')}",
            f"record_no: {rec}",
            f"sheet_hint_location: {head.get('sheet_location', '') or 'none'}",
            f"sheet_hint_address: {head.get('sheet_address', '') or 'none'}",
            "",
            "NOTE: the sheet hint above is UNVERIFIED and was never shown to the researcher.",
            f"hint_check: {head.get('hint_check', '')}",
            "",
        ]
        for i, f in enumerate(facs, 1):
            name = f.get("facility_name") or f.get("company", "")
            lines.append(f"facility {i}: {name}")
            for key, label in PAGE_FIELDS:
                v = str(f.get(key, "") or "").strip()
                lines.append(f"  {label}: {v or 'not visible in sources checked'}")
            lines.append("")
        lines.append(f"checked_at: {head.get('checked_at', '')}  "
                     f"model: {head.get('model', '')}  backend: {head.get('backend', '')}")
        slug = re.sub(r"[^a-z0-9]+", "_", str(head.get("company", "")).lower()).strip("_")
        fname = f"{int(rec):03d}_{slug or 'company'}.md" if rec.isdigit() else f"{rec}_{slug}.md"
        (pages_dir / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1
    return written


def main() -> None:
    cc._load_env()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="CSV (one row per facility)")
    ap.add_argument("--table", type=Path, default=DEFAULT_TABLE, help="15-column markdown table")
    ap.add_argument("--pages-dir", type=Path, default=DEFAULT_PAGES)
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--backend", choices=["auto", "tavily", "browser", "http"], default="auto")
    ap.add_argument("--model", default=None, help="override LLM_MODEL env var")
    ap.add_argument("--limit", type=int, default=0, help="only process first N records (0 = all)")
    ap.add_argument("--max-queries", type=int, default=6,
                    help=f"searches per company (default 6, max {len(QUERY_PATTERNS)}; "
                         f"each is ~1 Tavily credit)")
    ap.add_argument("--fetch-pages", type=int, default=3,
                    help="how many top result pages to open per company (default 3; 0 = snippets only)")
    ap.add_argument("--passes", type=int, default=2,
                    help="extraction passes over the same evidence, unioned (default 2). "
                         "Costs no extra search credits, only local model time.")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between companies (be polite)")
    ap.add_argument("--fresh", action="store_true", help="ignore existing results and start over")
    args = ap.parse_args()

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

    # Duplicate GNEM records for the same company (spec rule 6): keep the record
    # numbers separate, but say so in Notes.
    dupes: dict[str, list[str]] = {}
    with args.companies.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dupes.setdefault(_norm_company(r["company"]), []).append(str(r.get("record_no", "")))

    backend = cc.make_backend(args.backend)
    model = args.model or os.environ.get("LLM_MODEL") or llm_client.DEFAULT_MODEL

    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = {} if args.fresh else cc.load_done(args.out)
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
                rows, evidence = research_location(
                    backend, comp, model, args.fetch_pages, args.max_queries,
                    passes=args.passes)
            except Exception as e:
                fb = _norm_row({})
                fb.update(operational_status="search_failed", is_georgia="unclear",
                          notes=f"pipeline error: {e}")
                rows, evidence = [fb], f"(error: {e})"
                print(f"{label}: ERROR {e}")

            sheet_loc = comp.get("location", "") or ""
            sheet_addr = comp.get("address", "") or ""
            hint = check_sheet_hint(rows, sheet_addr, sheet_loc)
            siblings = [d for d in dupes.get(_norm_company(comp["company"]), []) if d != rec]
            checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

            for r in rows:
                # County: prefer what a source actually stated; otherwise resolve it
                # deterministically from the city, and say where it came from.
                ref_county = county_for(r["city"]) if r["is_georgia"] == "yes" else ""
                county_note = ""
                if ref_county and not r["county"]:
                    r["county"] = ref_county
                    county_note = ("county resolved from the Georgia city/county reference, "
                                   "not stated in this facility's source")
                elif ref_county and not county_agrees(r["county"], ref_county):
                    county_note = (f"source says {r['county']} County but the Georgia "
                                   f"city/county reference puts {r['city']} in "
                                   f"{ref_county} County")
                extra = [county_note] if county_note else []
                # Spec rule 4: flag a source-sheet hint the evidence contradicts.
                if hint.startswith(("mismatch", "county_mismatch", "partial_match",
                                    "sheet_county_wrong")):
                    extra.append(f"SOURCE-SHEET HINT LOOKS WRONG — {hint}")
                if siblings:
                    extra.append("duplicate GNEM record(s) for this company: #"
                                 + ", #".join(siblings))
                if extra:
                    r["notes"] = "; ".join(filter(None, [r["notes"]] + extra))[:600]
                r.update(record_no=rec, company=comp["company"],
                         sheet_location=sheet_loc, sheet_address=sheet_addr,
                         hint_check=hint,
                         category=comp.get("category", ""),
                         industry_group=comp.get("industry_group", ""),
                         checked_at=checked_at, model=model, backend=backend.name)
                writer.writerow({k: r.get(k, "") for k in OUT_FIELDS})
                all_rows.append(r)
            out_f.flush()
            log_f.write(json.dumps({"record_no": rec, "company": comp["company"],
                                    "n_rows": len(rows),
                                    "evidence": evidence[:LOG_CHARS]}) + "\n")
            log_f.flush()
            summary = "; ".join(
                f"{r['city'] or '?'}/{r['operational_status']}" for r in rows[:4])
            print(f"{label}: {len(rows)} facility row(s) -> {summary} [{hint.split(':')[0]}]")
            time.sleep(args.delay)
    finally:
        out_f.close()
        log_f.close()

    write_table(args.table, all_rows)
    n_pages = render_pages(all_rows, args.pages_dir)
    print(f"\nDone. Table: {args.table}\nCSV: {args.out}\n"
          f"Per-company pages: {n_pages} in {args.pages_dir}/\nEvidence log: {args.log}")


if __name__ == "__main__":
    main()
