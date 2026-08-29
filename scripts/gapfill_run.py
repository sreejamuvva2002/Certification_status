"""Gap-fill run over the frozen run-1 certification results.

Run 1 (`outputs/certification_status.csv`, 418 rows / 205 companies) left four gaps. This
driver closes three of them in separate passes, writing everything to a NEW directory so
run 1 is never modified:

  Pass A  re-search the 78 companies whose only run-1 row is "none identified" (those rows
          carry a blank source_url AND a blank evidence_quote, so a "no" was unauditable).
          Six queries instead of four, 4 pages fetched, and every row — including the
          not-founds — records the queries issued and the URLs opened.

  Pass B  EV/battery standard sweep across all 205. Run 1's queries never named UN 38.3,
          IEC 62660/62619, UL 2580/1973/2271, ISO 6469, ISO 15118, SAE J1772, IEC 61851,
          ISO 21434 or IEC 61508, so their absence from the file was untested rather than
          proven. Three gates run in code afterwards, because the output of this pass is a
          defensible "N% hold an EV/battery standard" and a false positive costs as much as
          the false negative being fixed:
            1. _ev_grounded()  — a hit needs ONE verbatim quote, present in the gathered
               evidence, containing both a distinctive company token and the standard token.
               Page co-occurrence (registrar marketing, standards resellers) fails.
            2. _catchall()     — battery/EV-shaped tokens we did not anticipate go to
               needs_review.csv instead of falling through to a zero. Scoped to the model's
               returned certification string, never to free evidence text.
            3. explicit negative — only when 1 and 2 both come up empty does the pass write
               "no EV/battery standard identified" with the queries and URLs behind it.
          NOTE: grounding proves co-location, not polarity. "not certified to UN 38.3" and
          "we help clients achieve IEC 62619" pass the gate by design; the hand-check of
          surviving hits is what catches those, and it must happen before any EV number is
          published.

  Pass C  certificate-detail fill (registrar / number / issue / expiry / scope) for the rows
          run 1 left blank. Grouped per company. Every filled field must appear in the
          evidence after normalisation (dates -> ISO on both sides, reference numbers
          collapsed to alphanumerics); a field that fails is dropped and named in
          dropped_fields, but the row survives.

  Pass E  delta EV/battery sweep, same machinery as pass B, for the targets pass B's canon
          did not name: UNECE R100, ISO 12405, GB 38031, SAE J2929/J2380, UL 2231 and the
          IEC 62660 parts. The first three were missed by _CATCHALL_NUM as well, so a
          company holding one would have been recorded as an explicit negative. Runs over
          all 205 rather than a "plausible battery company" subset, because the value of
          this pass is an absence claim and a subset would make the absence conditional on
          our own judgement of who was worth asking about.

Usage:
    python scripts/gapfill_run.py --pass A
    python scripts/gapfill_run.py --pass B --limit 2 --out-dir outputs/run2_gapfill/_smoke
    python scripts/gapfill_run.py --pass C
    python scripts/gapfill_run.py --pass E
    python scripts/gapfill_run.py --self-test        # gate unit tests, no network
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import check_certifications as cc  # noqa: E402
import llm_client  # noqa: E402
from collect_locations import _norm, _norm_company  # noqa: E402  (same grounding discipline)

RUN1_CSV = PKG_ROOT / "outputs" / "certification_status.csv"
DEFAULT_OUT_DIR = PKG_ROOT / "outputs" / "run2_gapfill"
COMPANIES = PKG_ROOT / "data" / "companies.csv"

OUT_FIELDS = cc.OUT_FIELDS + ["pass", "queries_tried", "urls_fetched",
                              "ev_canonical", "run1_cert_status", "dropped_fields"]
REVIEW_FIELDS = ["record_no", "company", "certification", "reason", "pass",
                 "evidence_quote", "source_url", "confidence", "notes", "checked_at"]

# --------------------------------------------------------------------- EV/battery canon

# canonical id -> (regex, bucket). Buckets are reported separately in the key: a functional
# safety standard is not a battery standard, and conflating them is how "EV supplier" claims
# get manufactured.
EV_BATTERY_CANON: dict[str, tuple[str, str]] = {
    "UN 38.3":    (r"\bUN\s*38[.\s]*3\b", "battery"),
    "IEC 62660":  (r"\bIEC\s*62660\b", "battery"),
    "IEC 62619":  (r"\bIEC\s*62619\b", "battery"),
    "IEC 62133":  (r"\bIEC\s*62133\b", "battery"),
    "UL 2580":    (r"\bUL\s*2580\b", "battery"),
    "UL 1973":    (r"\bUL\s*1973\b", "battery"),
    "UL 2271":    (r"\bUL\s*2271\b", "battery"),
    "UL 1642":    (r"\bUL\s*1642\b", "battery"),
    "ISO 6469":   (r"\bISO\s*6469\b", "ev_electrical"),
    "ISO 15118":  (r"\bISO\s*15118\b", "ev_electrical"),
    "SAE J1772":  (r"\bSAE\s*J\s*1772\b", "ev_electrical"),
    "IEC 61851":  (r"\bIEC\s*61851\b", "ev_electrical"),
    "IEC 62196":  (r"\bIEC\s*62196\b", "ev_electrical"),
    "UL 2594":    (r"\bUL\s*2594\b", "ev_electrical"),
    "UL 2202":    (r"\bUL\s*2202\b", "ev_electrical"),
    "ISO 17409":  (r"\bISO\s*17409\b", "ev_electrical"),
    "ISO 26262":  (r"\bISO\s*26262\b", "functional_safety"),
    "IEC 61508":  (r"\bIEC\s*61508\b", "functional_safety"),
    "ISO 21434":  (r"\bISO[/\s]*(?:SAE\s*)?21434\b", "functional_safety"),
    # --- pass E delta targets. Absent from the pass B canon AND from _CATCHALL_NUM, so a
    # company holding one of the first three was written down as an explicit negative.
    "UNECE R100": (r"\b(?:UN)?ECE\s*R\.?\s*100\b|\bUN\s*Regulation\s*No\.?\s*100\b",
                   "ev_electrical"),
    "ISO 12405":  (r"\bISO\s*12405\b", "battery"),
    "GB 38031":   (r"\bGB\s*38031\b", "battery"),
    "SAE J2929":  (r"\bSAE\s*J\s*2929\b", "battery"),
    "SAE J2380":  (r"\bSAE\s*J\s*2380\b", "battery"),
    "UL 2231":    (r"\bUL\s*2231\b", "ev_electrical"),
}

# Standard-number shapes that look like an EV/battery standard we did not enumerate.
_CATCHALL_NUM = [
    r"\bIEC\s*6[12]\d{3}\b",
    r"\bUL\s*[12]\d{3}\b",
    r"\bSAE\s*J\s*\d+\b",
    r"\bUN\s*38[.\s]*\d\b",
    r"\bISO\s*6469\b",
    r"\bGB[/\s]*T\s*\d+\b",
    r"\bGB\s*\d{4,5}\b",          # GB 38031 and friends: the GB/T pattern needs the T
    r"\b(?:UN)?ECE\s*R\.?\s*\d+\b",   # UNECE regulations other than R100
]
# Bare English tokens only count when they sit next to a standard number — "cell" alone
# means fuel cell, load cell, cellular, or a plant's work cell far more often than it means
# a battery cell, and an unscoped match would bury the real near-misses in the queue.
_CATCHALL_WORDS = r"(?:battery pack|traction|charging|charger|lithium|\bcell\b)"
_STD_NUM = r"\b(?:IEC|UL|ISO|SAE|UN|EN|DIN)\s?\d"


def _ev_canonical(cert: str) -> tuple[str, str] | tuple[None, None]:
    """Canonical EV/battery id + bucket for a certification string, or (None, None)."""
    for canon, (pat, bucket) in EV_BATTERY_CANON.items():
        if re.search(pat, cert, re.IGNORECASE):
            return canon, bucket
    return None, None


def _catchall(cert: str) -> bool:
    """True if `cert` looks battery/EV-shaped but is not in the canon — route to review.

    Operates on the model's returned certification string ONLY. Never call this on free
    evidence text: every automotive page in the corpus mentions "charging" or "cell"
    somewhere, and the review queue is only useful while it is short enough to read."""
    if not cert.strip():
        return False
    if _ev_canonical(cert)[0]:
        return False
    for pat in _CATCHALL_NUM:
        if re.search(pat, cert, re.IGNORECASE):
            return True
    for m in re.finditer(_CATCHALL_WORDS, cert, re.IGNORECASE):
        window = cert[max(0, m.start() - 20): m.end() + 20]
        if re.search(_STD_NUM, window, re.IGNORECASE):
            return True
    return False


def _ev_grounded(row: dict, company: str, evidence: str, canon: str) -> tuple[bool, str]:
    """Does one verbatim quote tie THIS company to THIS standard?

    Same normalise-and-substring discipline as _grounded() in collect_locations.py: the
    quote must really occur in the gathered evidence, and it must carry both the standard
    token and a distinctive company token. A page that lists IEC 62660 in one place and the
    company name in another is co-occurrence, not evidence."""
    quote = str(row.get("evidence_quote", "") or "")
    if not quote.strip():
        return False, "no_quote"
    nq, ne = _norm(quote), _norm(evidence)
    if nq not in ne:
        toks = nq.split()  # quotes are truncated at 500 chars, so accept a solid prefix
        if not (len(toks) >= 8 and " ".join(toks[:8]) in ne):
            return False, "quote_not_in_evidence"
    pat = EV_BATTERY_CANON[canon][0]
    if not re.search(pat, quote, re.IGNORECASE):
        return False, "standard_not_in_quote"
    ctoks = [t for t in _norm_company(company).split() if len(t) > 3] or _norm_company(company).split()
    if not any(t in nq for t in ctoks):
        return False, "company_not_in_quote"
    return True, ""


# Industry words that appear in a company's name AND in almost any prose describing a
# battery/EV standard. When one of these is the only company token the quote carries, the
# gate's "this quote is about this company" conclusion rests on a coincidence.
_GENERIC_NAME_TOKENS = frozenset({
    "battery", "batteries", "electric", "electrical", "energy", "power", "motor", "motors",
    "auto", "automotive", "vehicle", "vehicles", "charging", "charger", "cell", "cells",
    "lithium", "traction", "mobility", "drive", "solution", "solutions", "systems",
})


def _generic_token_only(company: str, quote: str) -> bool:
    """True if the only company tokens present in `quote` are generic industry words.

    18 of the 205 records are affected (FREYR Battery, SK Battery America, LG Energy
    Solution, Stryten Energy, Rivian/Panasonic/Continental Automotive …) — i.e. exactly the
    companies a battery-standard page is most likely to discuss in general terms. Such a
    hit is not rejected, because it may well be genuine; it is routed to the review queue
    so the hand-check that must precede publishing any EV number knows where to look.
    """
    nq = _norm(quote)
    ctoks = [t for t in _norm_company(company).split() if len(t) > 3] or _norm_company(company).split()
    present = [t for t in ctoks if t in nq]
    return bool(present) and all(t in _GENERIC_NAME_TOKENS for t in present)


# --------------------------------------------------------------------- field grounding

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _iso_dates(text: str) -> set[str]:
    """Every date in `text` as ISO yyyy-mm-dd. Ambiguous d/m vs m/d slash dates yield BOTH
    readings — the point is to compare model output against evidence without dropping a
    correct value over notation, so an over-generous set is the safe direction."""
    out: set[str] = set()
    t = str(text or "")

    for y, m, d in re.findall(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", t):
        out.add(f"{int(y):04d}-{int(m):02d}-{int(d):02d}")

    for a, b, y in re.findall(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", t):
        a, b, y = int(a), int(b), int(y)
        if 1 <= b <= 12 and 1 <= a <= 31:
            out.add(f"{y:04d}-{b:02d}-{a:02d}")          # d/m/y
        if 1 <= a <= 12 and 1 <= b <= 31:
            out.add(f"{y:04d}-{a:02d}-{b:02d}")          # m/d/y

    # 10 March 2021 / 10-Mar-2021
    for d, mon, y in re.findall(r"\b(\d{1,2})[\s\-]+([A-Za-z]{3,9})[\s\-,]+(\d{4})\b", t):
        mi = _MONTHS.get(mon[:3].lower())
        if mi:
            out.add(f"{int(y):04d}-{mi:02d}-{int(d):02d}")
    # March 10, 2021 / Mar 10 2021
    for mon, d, y in re.findall(r"\b([A-Za-z]{3,9})[\s\-]+(\d{1,2})(?:st|nd|rd|th)?[\s\-,]+(\d{4})\b", t):
        mi = _MONTHS.get(mon[:3].lower())
        if mi:
            out.add(f"{int(y):04d}-{mi:02d}-{int(d):02d}")
    return out


def _norm_ref(s: str) -> str:
    """Text reduced to bare alphanumerics, so spacing and punctuation stop mattering:
    'Certificate No. 10 000 091' -> 'certificateno10000091'."""
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _ref_tokens(s: str) -> set[str]:
    """Candidate forms of a certificate number to look for in the evidence.

    A model may return '10000091', 'Cert. No. 10000091' or '#10 000 091' for a page that
    says 'Certificate No. 10 000 091'. Matching the whole normalised string would fail on
    the prefix wording alone, so the number itself is extracted as well. Pure-digit tokens
    must be 5+ long: a bare 4-digit token is usually a year and would ground on anything."""
    txt = str(s or "")
    toks = set()
    for t in re.sub(r"[^A-Za-z0-9]+", " ", txt).split():
        t = t.lower()
        if any(c.isdigit() for c in t) and len(t) >= (5 if t.isdigit() else 4):
            toks.add(t)
    collapsed = _norm_ref(txt)
    # Same digit rule as above: a bare 4-digit collapsed form is a year far more often than a
    # certificate number, and would ground against any date on the page.
    if len(collapsed) >= (5 if collapsed.isdigit() else 4):
        toks.add(collapsed)
    digits = re.sub(r"\D", "", txt)
    if len(digits) >= 5:
        toks.add(digits)
    return toks


def _field_grounded(kind: str, value: str, evidence: str, ev_refs: str,
                    ev_dates: set[str]) -> bool:
    """Is `value` actually supported by the evidence, compared on normalised forms?"""
    v = str(value or "").strip()
    if not v:
        return True                       # nothing claimed, nothing to ground
    if kind == "date":
        got = _iso_dates(v)
        return bool(got & ev_dates) if got else _norm(v) in _norm(evidence)
    if kind == "ref":
        if any(t in ev_refs for t in _ref_tokens(v)):
            return True
        # Short numbers ("Certificate Number: 389") are excluded from _ref_tokens because a
        # bare 3-4 digit token would ground against any year on the page. They are still real
        # certificate numbers, so accept them when the evidence puts a certificate-number cue
        # immediately in front of the value.
        short = re.sub(r"[^A-Za-z0-9]", "", v)
        if 1 <= len(short) <= 6:
            cue = (r"(?:certificate|cert\.?|registration|reg\.?|licen[cs]e)\s*"
                   r"(?:number|no\.?|num\.?|#)?\s*[:#\-]?\s*0*" + re.escape(short))
            return bool(re.search(cue, evidence, re.IGNORECASE))
        return False
    nv, ne = _norm(v), _norm(evidence)
    if not nv or nv in ne:
        return True
    toks = nv.split()
    return len(toks) >= 3 and " ".join(toks[:3]) in ne


# --------------------------------------------------------------------- shared plumbing

# Hosts that surface for company-name queries but never carry certificate evidence. They
# are still visible to the model as search snippets; they just do not deserve a page fetch.
_LOW_VALUE_HOSTS = (
    "bebee.com", "indeed.com", "linkedin.com", "ziprecruiter.com", "glassdoor.",
    "talents.vaia.com", "jobs.", "careers.", "mapquest.com", "yelp.com", "facebook.com",
    "x.com/", "twitter.com", "youtube.com", "crunchbase.com", "zoominfo.com",
    "dnb.com", "bizapedia.com", "buzzfile.com", "manta.com",
)


def _rank_urls(links: list[str], company: str) -> list[str]:
    """Company-owned pages first, then registrar/registry pages, then everything else.

    check_certifications.py ranks purely on REGISTRY_HINTS, which contains "cert" — so for a
    company with a thin web presence every fetch lands on registrar marketing (tuv.com,
    dekra.us, intertek.com) that cannot possibly mention it. Those pages are exactly the
    co-occurrence traps the pass-B gate then has to reject. Preferring URLs carrying a
    distinctive company token spends the fetch budget where the answer can actually be."""
    ctoks = [t for t in _norm_company(company).split() if len(t) > 3]

    def score(u: str) -> int:
        ul = u.lower()
        if any(h in ul for h in _LOW_VALUE_HOSTS):
            return 3            # job boards and map/directory aggregators never hold certificates
        flat = re.sub(r"[^a-z0-9]", "", ul)
        if ctoks and any(t in flat for t in ctoks):
            return 0
        if any(h in ul for h in cc.REGISTRY_HINTS):
            return 1
        return 2

    seen, ranked = set(), []
    for u in sorted(links, key=score):
        if u not in seen:
            seen.add(u)
            ranked.append(u)
    return ranked


def _gather(backend, queries: list[str], fetch_pages: int,
            company: str = "") -> tuple[str, list[str], bool]:
    """Search, then open the strongest few pages, newest evidence shape shared by all passes."""
    parts, all_links, search_ok = [], [], False
    for q in queries:
        text, links = backend.search(q)
        if links:
            search_ok = True
        parts.append(f"SEARCH {q!r}:\n{text}")
        all_links.extend(links)
    fetched = []
    for url in _rank_urls(all_links, company)[:fetch_pages]:
        try:
            parts.append(f"PAGE {url}:\n{backend.fetch_page(url)}")
            fetched.append(url)
        except Exception as e:
            parts.append(f"PAGE {url}: (fetch failed: {e})")
    return "\n\n".join(parts), fetched, search_ok


def _extract(company: dict, evidence: str, model: str, search_ok: bool) -> list[dict]:
    """One model call turning gathered evidence into certification rows (cc.TABLE_PROMPT)."""
    if not search_ok and "PAGE " not in evidence:
        row = cc._norm_row({})
        row.update(certification="none identified", cert_status="search_failed",
                   facility_status="not_applicable", confidence="low",
                   notes="search returned no results / all keys exhausted")
        return [row]
    hint = ", ".join(filter(None, [company.get("location", ""), company.get("address", ""),
                                   company.get("industry_group", "")]))
    user = (f"Company: {company['company']}\n"
            f"Unverified Georgia location/address hint (may be wrong): {hint or 'none'}\n\n"
            f"Evidence:\n{evidence[:14000]}")
    try:
        raw = llm_client.chat([{"role": "system", "content": cc.TABLE_PROMPT},
                               {"role": "user", "content": user}], model=model)
        got = llm_client.extract_json(raw).get("rows", [])
    except Exception as e:
        got = []
        print(f"    model call failed: {e}")
    rows = [cc._norm_row(r) for r in got
            if isinstance(r, dict) and str(r.get("certification", "")).strip()]
    if not rows:
        row = cc._norm_row({})
        row.update(certification="none identified", cert_status="not_found_after_search",
                   facility_status="not_applicable", confidence="low",
                   notes="no certifications identified in evidence")
        rows = [row]
    return rows


def _blank_row(pass_name: str) -> dict:
    row = cc._norm_row({})
    row.update({f: "" for f in OUT_FIELDS if f not in row})
    row["pass"] = pass_name
    return row


def _load_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        return {str(r.get("record_no", "")) for r in csv.DictReader(f)}


def _load_keys(path: Path, cols: list[str]) -> set[tuple]:
    """Existing composite keys in a side-output file, so a resumed pass never re-appends.
    load_done() only marks a record done after its main rows are written, so a pass killed
    mid-record would otherwise duplicate its near-misses."""
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        return {tuple(str(r.get(c, "")) for c in cols) for r in csv.DictReader(f)}


def _open_writer(path: Path, fields: list[str], fresh: bool):
    mode = "w" if (fresh or not path.exists()) else "a"
    f = path.open(mode, newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    if mode == "w":
        w.writeheader()
    return f, w


def _read_run1() -> list[dict]:
    with RUN1_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_companies() -> list[dict]:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# --------------------------------------------------------------------- pass A

EXTRA_A = [
    '"{name}" "certificate of registration" OR "certificate number" OR registrar quality',
    '"{name}" quality certifications pdf certificate',
    '"{name}" Georgia plant supplier quality approvals',
]


def blank_record_nos(run1: list[dict]) -> list[str]:
    """Records whose every run-1 row is 'none identified' — the 78 unaudited blanks."""
    by_rec: dict[str, list[dict]] = {}
    for r in run1:
        by_rec.setdefault(str(r["record_no"]), []).append(r)
    return [rec for rec, rows in by_rec.items()
            if all(r["certification"].strip() == "none identified" for r in rows)]


def run_pass_a(backend, companies, model, out_dir, args) -> None:
    run1 = _read_run1()
    wanted = set(blank_record_nos(run1))
    subset = [c for c in companies if str(c["record_no"]) in wanted]
    (out_dir / "companies_blanks.csv").write_text(
        _csv_text(subset, list(companies[0].keys())), encoding="utf-8")
    print(f"[A] {len(subset)} blank records to re-search")
    if args.limit:
        subset = subset[: args.limit]

    out = out_dir / "passA_blanks.csv"
    done = set() if args.fresh else _load_done(out)
    f, w = _open_writer(out, OUT_FIELDS, args.fresh)
    log = _evidence_logger(out_dir, args.fresh, "A")
    try:
        for i, comp in enumerate(subset, 1):
            rec = str(comp["record_no"])
            if rec in done:
                print(f"[A {i}/{len(subset)}] #{rec} {comp['company']}: already done, skipping")
                continue
            queries = cc.build_queries(comp, 4) + [q.format(name=comp["company"]) for q in EXTRA_A]
            evidence, urls, ok = _gather(backend, queries, args.fetch_pages, comp["company"])
            rows = _extract(comp, evidence, model, ok)
            audit = ("queries: " + " | ".join(queries) + "  ||  urls opened: "
                     + (", ".join(urls) if urls else "none"))
            for r in rows:
                r.update({k: r.get(k, "") for k in OUT_FIELDS})
                r["pass"] = "A"
                r["queries_tried"] = " | ".join(queries)
                r["urls_fetched"] = " ".join(urls)
                # The run-1 defect being fixed: a "no" with nothing behind it. Every row,
                # found or not, now carries what was tried.
                if not r["notes"].strip():
                    r["notes"] = f"searched {len(queries)} queries, opened {len(urls)} pages"
                if not r["evidence_quote"].strip():
                    r["evidence_quote"] = audit[:500]
            _emit(w, f, rows, comp, model, backend, log, evidence)
            summary = ", ".join(f"{r['certification']}={r['cert_status']}" for r in rows[:5])
            print(f"[A {i}/{len(subset)}] #{rec} {comp['company']}: {len(rows)} row(s) -> {summary}")
            time.sleep(args.delay)
    finally:
        f.close()
        log.close()


# --------------------------------------------------------------------- passes B and E

EV_QUERIES = [
    '"{name}" "UN 38.3" OR "IEC 62660" OR "IEC 62619" OR "UL 2580" OR "UL 1973" OR "UL 2271" battery certification',
    '"{name}" "ISO 6469" OR "ISO 15118" OR "SAE J1772" OR "IEC 61851" OR "ISO 21434" OR "ISO 26262" OR "IEC 61508" certification',
    '"{name}" battery OR "electric vehicle" certification standard compliance certificate',
]

# Pass E. Pass B's queries never named these, and the first three were not caught by
# _CATCHALL_NUM either, so their absence from the file was untested rather than proven —
# the same argument that motivated pass B in the first place. Two queries, all 205
# companies: narrowing to "plausible battery companies" would reintroduce exactly the
# selection step that makes an absence claim challengeable.
EV_DELTA_QUERIES = [
    '"{name}" "UNECE R100" OR "ECE R100" OR "ISO 12405" OR "GB 38031" battery certification',
    '"{name}" "SAE J2929" OR "SAE J2380" OR "UL 2231" OR "IEC 62660-1" OR "IEC 62660-2" OR "IEC 62660-3" certification',
]


def _run_ev_sweep(backend, companies, model, out_dir, args, *, pass_name: str,
                  query_templates: list[str], out_name: str, negative_cert: str) -> None:
    """Shared body of the EV/battery sweeps (pass B, pass E).

    Identical gate discipline in both: canon hit -> _ev_grounded, unanticipated
    battery-shaped token -> review queue, and only when both come up empty does the
    company get an explicit, auditable negative carrying its queries and URLs.
    """
    subset = companies[: args.limit] if args.limit else companies
    out = out_dir / out_name
    review = out_dir / "needs_review.csv"
    done = set() if args.fresh else _load_done(out)
    seen_review = set() if args.fresh else _load_keys(review, ["record_no", "certification"])
    f, w = _open_writer(out, OUT_FIELDS, args.fresh)
    rf, rw = _open_writer(review, REVIEW_FIELDS, args.fresh)
    log = _evidence_logger(out_dir, args.fresh, pass_name)
    try:
        for i, comp in enumerate(subset, 1):
            rec = str(comp["record_no"])
            tag = f"[{pass_name} {i}/{len(subset)}] #{rec} {comp['company']}"
            if rec in done:
                print(f"{tag}: already done, skipping")
                continue
            queries = [q.format(name=comp["company"]) for q in query_templates]
            evidence, urls, ok = _gather(backend, queries, args.fetch_pages, comp["company"])
            rows = _extract(comp, evidence, model, ok)

            keep, hits, reviewed = [], 0, 0
            for r in rows:
                cert = r.get("certification", "")
                canon, _bucket = _ev_canonical(cert)
                r.update({k: r.get(k, "") for k in OUT_FIELDS})
                r["pass"] = pass_name
                r["queries_tried"] = " | ".join(queries)
                r["urls_fetched"] = " ".join(urls)
                if canon:
                    ok, why = _ev_grounded(r, comp["company"], evidence, canon)
                    if ok:
                        r["ev_canonical"] = canon
                        hits += 1
                        keep.append(r)
                        if _generic_token_only(comp["company"], r.get("evidence_quote", "")):
                            _review(rw, rf, seen_review, rec, comp["company"], cert,
                                    "generic_company_token_only", pass_name, r)
                            reviewed += 1
                    else:
                        _review(rw, rf, seen_review, rec, comp["company"], cert, why, pass_name, r)
                        reviewed += 1
                elif _catchall(cert):
                    _review(rw, rf, seen_review, rec, comp["company"], cert,
                            "unrecognized_battery_token", pass_name, r)
                    reviewed += 1
                    keep.append(r)          # keep the row too; pass D still sees the evidence
                elif cert.strip() and cert.strip() != "none identified":
                    keep.append(r)          # non-EV certification found along the way
            if hits == 0:
                neg = _blank_row(pass_name)
                neg.update(certification=negative_cert,
                           cert_status="not_found_after_search", facility_status="not_applicable",
                           confidence="low", queries_tried=" | ".join(queries),
                           urls_fetched=" ".join(urls),
                           evidence_quote=("queries: " + " | ".join(queries))[:500],
                           notes=(f"searched {len(queries)} EV/battery queries, opened "
                                  f"{len(urls)} pages; no grounded EV/battery standard"))
                keep.append(neg)
            _emit(w, f, keep, comp, model, backend, log, evidence)
            print(f"{tag}: {hits} EV/battery hit(s), {reviewed} to review, {len(keep)} row(s)")
            time.sleep(args.delay)
    finally:
        f.close()
        rf.close()
        log.close()


def run_pass_b(backend, companies, model, out_dir, args) -> None:
    _run_ev_sweep(backend, companies, model, out_dir, args, pass_name="B",
                  query_templates=EV_QUERIES, out_name="passB_ev.csv",
                  negative_cert="no EV/battery standard identified")


def run_pass_e(backend, companies, model, out_dir, args) -> None:
    """Delta sweep for the targets pass B's canon and catch-all both missed.

    The negative is worded differently from pass B's on purpose: these two negatives are
    about different standards, and collapsing them would let a reader double-count one
    company's absence as two independent findings.
    """
    _run_ev_sweep(backend, companies, model, out_dir, args, pass_name="E",
                  query_templates=EV_DELTA_QUERIES, out_name="passE_ev.csv",
                  negative_cert="no EV/battery standard identified (delta targets)")


def _review(rw, rf, seen: set, rec: str, company: str, cert: str, reason: str,
            pass_name: str, row: dict) -> None:
    key = (str(rec), cert)
    if key in seen:
        return
    seen.add(key)
    rw.writerow({
        "record_no": rec, "company": company, "certification": cert, "reason": reason,
        "pass": pass_name, "evidence_quote": row.get("evidence_quote", ""),
        "source_url": row.get("source_url", ""), "confidence": row.get("confidence", ""),
        "notes": row.get("notes", ""),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    rf.flush()


# --------------------------------------------------------------------- pass C

DETAIL_PROMPT = """You are a certification-compliance analyst. You are given web search results \
and text from source pages about ONE company, plus a list of certifications that company is \
already known to hold. Your ONLY job is to find the missing CERTIFICATE DETAILS for those \
certifications: the registrar, the certificate number, the issue and expiry dates, and the scope.

Do NOT judge whether the company holds the certification, and do NOT add certifications that are \
not in the list.

Respond with ONLY a JSON object, no prose:
{"rows": [
  {"certification": "<copy one entry from the list, exactly>",
   "certification_body": "<registrar/body name verbatim (DQS, DNV, TUV, SGS, BSI, ...), or \"\">",
   "reference_no": "<certificate/registration number verbatim, or \"\">",
   "issue_date": "<issue date exactly as written in the source, or \"\">",
   "expiry_date": "<expiry/valid-until date exactly as written in the source, or \"\">",
   "scope": "<certificate scope text verbatim, one line, or \"\">",
   "facility_status": "<facility_confirmed | facility_not_confirmed | parent_only | \
affiliate_only | unclear>",
   "source_type": "<registrar_database | official_certificate_pdf | company_certificate_pdf | \
company_page | government_database | news_directory>",
   "source_url": "<the single URL these details came from>",
   "evidence_quote": "<short verbatim quote from the source containing the details>",
   "confidence": "<high | medium | low>"}
]}

Rules:
- EVERY value must be copied VERBATIM from the evidence. Never infer, never reformat, never
  fabricate. Use "" for anything not visible — a blank is correct and useful; a guess is not.
- One row per certification you found details for. Omit certifications you found nothing for.
- facility_status: "facility_confirmed" only if the source ties the certificate to the Georgia
  site (names it, its Georgia city, its address, or a scope that clearly covers it).
- Ignore evidence that is clearly about a different company with a similar name.
"""

_LIVE = {"confirmed_active", "active_expiry_unknown", "confirmed_expired"}
_FILLABLE = _LIVE | {"company_claim_only"}
QUERIES_C = [
    '"{name}" "certificate of registration" certificate number expiry registrar',
    '"{name}" ISO IATF certificate pdf valid until',
]


def detail_targets(run1: list[dict]) -> dict[str, list[dict]]:
    """record_no -> run-1 rows that are missing registrar / number / expiry."""
    targets: dict[str, list[dict]] = {}
    for r in run1:
        if r["certification"].strip() in ("", "none identified"):
            continue
        if r["cert_status"] not in _FILLABLE:
            continue
        if r["certification_body"].strip() and r["reference_no"].strip() and r["expiry_date"].strip():
            continue
        targets.setdefault(str(r["record_no"]), []).append(r)
    return targets


def run_pass_c(backend, companies, model, out_dir, args) -> None:
    run1 = _read_run1()
    targets = detail_targets(run1)
    by_rec = {str(c["record_no"]): c for c in companies}
    recs = [r for r in targets if r in by_rec]
    print(f"[C] {sum(len(v) for v in targets.values())} rows across {len(recs)} records to fill")
    if args.limit:
        recs = recs[: args.limit]

    out = out_dir / "passC_details.csv"
    done = set() if args.fresh else _load_done(out)
    f, w = _open_writer(out, OUT_FIELDS, args.fresh)
    log = _evidence_logger(out_dir, args.fresh, "C")
    dropped_total = filled_total = 0
    try:
        for i, rec in enumerate(recs, 1):
            comp = by_rec[rec]
            if rec in done:
                print(f"[C {i}/{len(recs)}] #{rec} {comp['company']}: already done, skipping")
                continue
            want = targets[rec]
            certs = sorted({r["certification"].strip() for r in want})
            queries = [q.format(name=comp["company"]) for q in QUERIES_C]
            evidence, urls, _ok = _gather(backend, queries, args.fetch_pages, comp["company"])

            user = (f"Company: {comp['company']}\n"
                    f"Unverified Georgia location hint (may be wrong): {comp.get('location', '')}\n"
                    f"Certifications to find details for:\n"
                    + "\n".join(f"- {c}" for c in certs)
                    + f"\n\nEvidence:\n{evidence[:14000]}")
            try:
                raw = llm_client.chat([{"role": "system", "content": DETAIL_PROMPT},
                                       {"role": "user", "content": user}], model=model)
                got = llm_client.extract_json(raw).get("rows", [])
            except Exception as e:
                got = []
                print(f"[C {i}/{len(recs)}] #{rec}: model call failed: {e}")

            ev_refs = _norm_ref(evidence)
            ev_dates = _iso_dates(evidence)
            run1_status = {r["certification"].strip(): r["cert_status"] for r in want}
            rows = []
            for g in got:
                if not isinstance(g, dict):
                    continue
                cert = str(g.get("certification", "")).strip()
                if cert not in certs:
                    continue                       # model invented a certification: ignore
                row = _blank_row("C")
                row.update(cc._norm_row({**g, "cert_status": run1_status.get(cert, "unclear")}))
                row["pass"] = "C"
                row["certification"] = cert
                row["run1_cert_status"] = run1_status.get(cert, "")
                row["queries_tried"] = " | ".join(queries)
                row["urls_fetched"] = " ".join(urls)

                dropped = []
                for field, kind in (("certification_body", "text"), ("reference_no", "ref"),
                                    ("issue_date", "date"), ("expiry_date", "date"),
                                    ("scope", "text")):
                    if row[field] and not _field_grounded(kind, row[field], evidence,
                                                          ev_refs, ev_dates):
                        dropped.append(f"{field}={row[field]!r}")
                        row[field] = ""          # drop the field, keep the row
                row["dropped_fields"] = "; ".join(dropped)
                if dropped:
                    row["notes"] = (row["notes"] + " | " if row["notes"] else "") + \
                        f"{len(dropped)} field(s) dropped: not found in evidence"
                # Verbatim capture keeps ranges like "07 December, 2017 - 06 December, 2020"
                # intact; the code, not the model, decides whether that date has passed.
                got_dates = _iso_dates(row["expiry_date"])
                if got_dates and max(got_dates) < datetime.now(timezone.utc).date().isoformat():
                    row["notes"] = (row["notes"] + " | " if row["notes"] else "") + \
                        f"latest expiry date shown ({max(got_dates)}) is in the past"
                dropped_total += len(dropped)
                filled_total += sum(1 for fld in ("certification_body", "reference_no",
                                                  "issue_date", "expiry_date") if row[fld])
                rows.append(row)
            if not rows:
                # Deliberately NOT a joined cert string: pass C only enriches details, so a
                # synthetic "ISO 14001; ISO 45001; ..." row would be exploded by the
                # normaliser into standards nobody ever claimed.
                miss = _blank_row("C")
                miss.update(certification="(no certificate details found)",
                            cert_status="not_found_after_search",
                            facility_status="not_applicable", confidence="low",
                            queries_tried=" | ".join(queries), urls_fetched=" ".join(urls),
                            notes=(f"no certificate details found in {len(urls)} pages opened; "
                                   f"sought: {'; '.join(certs)}")[:300])
                rows = [miss]
            _emit(w, f, rows, comp, model, backend, log, evidence)
            print(f"[C {i}/{len(recs)}] #{rec} {comp['company']}: {len(rows)} row(s), "
                  f"{filled_total} fields filled / {dropped_total} dropped so far")
            time.sleep(args.delay)
    finally:
        f.close()
        log.close()
    total = filled_total + dropped_total
    if total:
        print(f"[C] field drop rate: {dropped_total}/{total} = {100 * dropped_total / total:.0f}%"
              f"  (>30% means the normaliser is at fault, not the evidence)")


# --------------------------------------------------------------------- emit / logging

class _EvidenceLog:
    """Evidence log keyed on (pass, record_no).

    Keying on record_no alone would be wrong across passes as well as merely wasteful: all
    three passes share one log file, so pass B and pass C would silently skip logging every
    record pass A had already covered — losing the audit trail for exactly the 78 companies
    the run exists to make auditable. Within a pass the key still suppresses the re-append a
    resume would otherwise produce."""

    def __init__(self, path: Path, fresh: bool, pass_name: str):
        self.pass_name = pass_name
        self.seen: set[tuple[str, str]] = set()
        if path.exists() and not fresh:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    d = json.loads(line)
                    self.seen.add((str(d.get("pass", "A")), str(d.get("record_no", ""))))
                except Exception:
                    pass
        self.f = path.open("w" if fresh else "a", encoding="utf-8")

    def write(self, rec: str, company: str, n_rows: int, evidence: str) -> None:
        key = (self.pass_name, str(rec))
        if key in self.seen:
            return
        self.seen.add(key)
        self.f.write(json.dumps({"pass": self.pass_name, "record_no": rec, "company": company,
                                 "n_rows": n_rows, "evidence": evidence[:6000]}) + "\n")
        self.f.flush()

    def close(self) -> None:
        self.f.close()


def _evidence_logger(out_dir: Path, fresh: bool, pass_name: str) -> _EvidenceLog:
    return _EvidenceLog(out_dir / "evidence_log.jsonl", fresh, pass_name)


def _emit(writer, fh, rows: list[dict], comp: dict, model: str, backend, log, evidence: str) -> None:
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in rows:
        r.update(record_no=str(comp["record_no"]), company=comp["company"],
                 location=comp.get("location", "") or comp.get("address", ""),
                 checked_at=checked_at, model=model, backend=backend.name)
        writer.writerow({k: r.get(k, "") for k in OUT_FIELDS})
    fh.flush()
    log.write(str(comp["record_no"]), comp["company"], len(rows), evidence)


def _csv_text(rows: list[dict], fields: list[str]) -> str:
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


# --------------------------------------------------------------------- self-test

def self_test() -> int:
    """Gate unit tests. No network, no model — run before any bulk pass."""
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)
        print(f"  {'ok  ' if cond else 'FAIL'} {name}")

    print("_ev_grounded:")
    ev_hit = ("PAGE https://acme.com/quality:\nAcme Battery Systems' traction packs are "
              "certified to UN 38.3 for transport.")
    check("genuine hit passes",
          _ev_grounded({"evidence_quote": "Acme Battery Systems' traction packs are certified to "
                                          "UN 38.3 for transport."},
                       "Acme Battery Systems LLC", ev_hit, "UN 38.3")[0])

    ev_cooc = ("PAGE https://registrar.example/iec-62660:\nIEC 62660 covers secondary lithium-ion "
               "cells for EVs. Clients include Acme Battery Systems, Globex and Initech.")
    ok, why = _ev_grounded({"evidence_quote": "IEC 62660 covers secondary lithium-ion cells for EVs."},
                           "Acme Battery Systems LLC", ev_cooc, "IEC 62660")
    check(f"co-occurrence trap rejected ({why})", not ok)

    ok, why = _ev_grounded({"evidence_quote": "Buy IEC 62619:2022 standard PDF download now."},
                           "Acme Battery Systems LLC",
                           "PAGE https://shop.example:\nBuy IEC 62619:2022 standard PDF download now.",
                           "IEC 62619")
    check(f"standards reseller rejected ({why})", not ok)

    ok, _ = _ev_grounded({"evidence_quote": "Acme Battery Systems is not certified to UN 38.3."},
                         "Acme Battery Systems LLC",
                         "PAGE https://x:\nAcme Battery Systems is not certified to UN 38.3.",
                         "UN 38.3")
    check("negation PASSES the gate (hand-check must catch it)", ok)

    ok, _ = _ev_grounded({"evidence_quote": "Acme Battery Systems helps clients achieve IEC 62619."},
                         "Acme Battery Systems LLC",
                         "PAGE https://x:\nAcme Battery Systems helps clients achieve IEC 62619.",
                         "IEC 62619")
    check("third-party framing PASSES the gate (hand-check must catch it)", ok)

    ok, why = _ev_grounded({"evidence_quote": "We are certified to UN 38.3."},
                           "Acme Battery Systems LLC",
                           "PAGE https://x:\nWe are certified to UN 38.3.", "UN 38.3")
    check(f"quote without company token rejected ({why})", not ok)

    print("_catchall (scoped to the returned certification string):")
    check("IEC 62133 is canon, not review", not _catchall("IEC 62133"))
    check("IEC 62840 (unanticipated, battery swap) routes to review", _catchall("IEC 62840"))
    check("UL 1642 is canon, not review", not _catchall("UL 1642"))
    check("UL 2743 (unanticipated) routes to review", _catchall("UL 2743"))
    check("'fuel cell' alone does not route", not _catchall("fuel cell technology"))
    check("'load cell calibration' does not route", not _catchall("load cell calibration"))
    check("'battery pack' alone does not route", not _catchall("battery pack assembly"))
    check("'ISO 9001 cell' style adjacency routes", _catchall("IEC 63000 cell testing"))
    check("ISO 9001 does not route", not _catchall("ISO 9001:2015"))
    check("SAE J2464 routes", _catchall("SAE J2464"))

    print("pass E delta canon:")
    for text in ("UNECE R100", "ECE R100", "ECE R.100", "UN Regulation No. 100"):
        canon, bucket = _ev_canonical(text)
        check(f"{text!r} -> UNECE R100 / ev_electrical",
              canon == "UNECE R100" and bucket == "ev_electrical")
    check("ISO 12405-4 -> ISO 12405 (battery)", _ev_canonical("ISO 12405-4") == ("ISO 12405", "battery"))
    check("GB 38031 -> GB 38031 (battery)", _ev_canonical("GB 38031") == ("GB 38031", "battery"))
    check("SAE J2929 -> canon, not review", not _catchall("SAE J2929"))
    check("UL 2231 -> canon, not review", not _catchall("UL 2231"))
    check("IEC 62660-3 -> IEC 62660 family", _ev_canonical("IEC 62660-3")[0] == "IEC 62660")
    # the delta targets must not be silently reclassified as battery-product standards
    check("UNECE R100 is not bucketed 'battery'", _ev_canonical("UNECE R100")[1] != "battery")
    # unanticipated neighbours of the new canon entries must reach the review queue
    check("GB 38032 (unanticipated) routes to review", _catchall("GB 38032"))
    check("ECE R136 (unanticipated) routes to review", _catchall("ECE R136"))
    check("'GB 500' (too short to be a standard no.) does not route", not _catchall("GB 500"))

    ok, _ = _ev_grounded({"evidence_quote": "Acme Battery Systems is not certified to UNECE R100."},
                         "Acme Battery Systems LLC",
                         "PAGE https://x:\nAcme Battery Systems is not certified to UNECE R100.",
                         "UNECE R100")
    check("delta target negation PASSES the gate (hand-check must catch it)", ok)

    ok, why = _ev_grounded({"evidence_quote": "GB 38031 is the Chinese EV safety standard."},
                           "Initech Components Inc",
                           "PAGE https://std.example:\nGB 38031 is the Chinese EV safety "
                           "standard. Suppliers include Initech Components.", "GB 38031")
    check(f"delta target co-occurrence rejected ({why})", not ok)

    # A company whose NAME contains a generic industry word satisfies the company-token
    # check on a page that only describes the standard. The gate cannot tell that apart
    # from real evidence, so the hit stands but _generic_token_only routes it to review.
    generic_quote = "GB 38031 is the Chinese EV battery safety standard."
    ok, _ = _ev_grounded({"evidence_quote": generic_quote}, "Acme Battery Systems LLC",
                         "PAGE https://std.example:\n" + generic_quote, "GB 38031")
    check("generic name token PASSES the gate (known weakness)", ok)

    print("_generic_token_only (routes the above to the hand-check):")
    check("generic-only match flagged", _generic_token_only("Acme Battery Systems LLC", generic_quote))
    check("distinctive token present -> not flagged",
          not _generic_token_only("Acme Battery Systems LLC",
                                  "Acme Battery Systems is certified to GB 38031."))
    check("real name: FREYR Battery flagged on standard prose",
          _generic_token_only("FREYR Battery", generic_quote))
    check("real name: FREYR Battery not flagged when 'FREYR' is in the quote",
          not _generic_token_only("FREYR Battery", "FREYR is certified to GB 38031."))
    check("no company token at all -> not flagged (that is _ev_grounded's rejection)",
          not _generic_token_only("Initech Components Inc", generic_quote))

    print("_iso_dates:")
    for text, want in (("10 March 2021", "2021-03-10"), ("March 10, 2021", "2021-03-10"),
                       ("10/03/2021", "2021-03-10"), ("2021-03-10", "2021-03-10"),
                       ("10-Mar-2021", "2021-03-10"), ("valid until 03/10/2021", "2021-03-10")):
        check(f"{text!r} -> {want}", want in _iso_dates(text))

    print("_norm_ref / field grounding:")
    ev = "Certificate No. 10 000 091 issued by DQS, valid until 10 March 2021."
    refs, dates = _norm_ref(ev), _iso_dates(ev)
    check("'10000091' grounded", _field_grounded("ref", "10000091", ev, refs, dates))
    check("'Cert. No. 10000091' grounded", _field_grounded("ref", "Cert. No. 10000091", ev, refs, dates))
    check("'2021-03-10' grounded", _field_grounded("date", "2021-03-10", ev, refs, dates))
    check("'DQS' grounded", _field_grounded("text", "DQS", ev, refs, dates))
    check("invented number rejected", not _field_grounded("ref", "99999999", ev, refs, dates))
    ev2 = "ISO 14001 Certificate of Registration ... Certificate Number: 389 Expiry Date: 13 July 2027"
    r2, d2 = _norm_ref(ev2), _iso_dates(ev2)
    check("short cue-anchored number '389' grounded",
          _field_grounded("ref", "389", ev2, r2, d2))
    check("bare year '2027' NOT grounded as a certificate number",
          not _field_grounded("ref", "2027", ev2, r2, d2))
    check("invented expiry rejected", not _field_grounded("date", "2030-01-01", ev, refs, dates))
    check("empty value is fine", _field_grounded("ref", "", ev, refs, dates))

    print(f"\n{'ALL PASSED' if not fails else str(len(fails)) + ' FAILURES: ' + ', '.join(fails)}")
    return 1 if fails else 0


# --------------------------------------------------------------------- main

def main() -> None:
    cc._load_env()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pass", dest="pass_name", choices=["A", "B", "C", "E"])
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--backend", choices=["auto", "tavily", "browser", "http"], default="auto")
    ap.add_argument("--model", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--fetch-pages", type=int, default=3)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--host-interval", type=float, default=3.0,
                    help="min seconds between fetches of the same host (default 3)")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--self-test", action="store_true", help="run the gate unit tests and exit")
    args = ap.parse_args()

    if args.self_test:
        raise SystemExit(self_test())
    if not args.pass_name:
        ap.error("--pass A|B|C|E is required (or --self-test)")

    if not llm_client.ping():
        raise SystemExit(f"Local LLM not reachable at {llm_client.DEFAULT_BASE_URL} — start ollama.")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    backend = cc.make_backend(args.backend)
    cc.install_polite_fetch(backend, args.out_dir / "page_cache", args.host_interval)
    model = args.model or os.environ.get("LLM_MODEL") or llm_client.DEFAULT_MODEL
    companies = _read_companies()

    if args.pass_name == "A":
        args.fetch_pages = max(args.fetch_pages, 4)
        run_pass_a(backend, companies, model, args.out_dir, args)
    elif args.pass_name == "B":
        run_pass_b(backend, companies, model, args.out_dir, args)
    elif args.pass_name == "E":
        run_pass_e(backend, companies, model, args.out_dir, args)
    else:
        run_pass_c(backend, companies, model, args.out_dir, args)
    print(f"\nPass {args.pass_name} done -> {args.out_dir}")


if __name__ == "__main__":
    main()
