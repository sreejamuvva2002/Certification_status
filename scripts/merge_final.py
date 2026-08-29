"""Merge every result set into one deduplicated record per (company, standard).

Inputs: the two LLM result sets in notes.md plus the pipeline's own rows (run 1 and gap-fill
passes A/B/C) — 2,200-odd rows in total — together with link_status.json and the page text
cached by verify_links.py.

Merge rules, all of them consequential:

  UNIT          one record per (record_no, canonical standard). "IATF 16949:2016",
                "IATF-16949" and "ISO/TS 16949" are the same certification and become one
                record, not three.

  SUPPORT       every contributing row is checked twice: is its URL reachable, and does its
                evidence_quote actually appear on that page? A live link that no longer says
                what was claimed is not support, so both results are carried per source.

  FIELD VALUES  strongest evidence wins. Rows are ranked by source type (registrar database >
                official certificate PDF > company certificate PDF > government database >
                company page > news/directory), and a row whose quote verified outranks one
                whose quote could not be found. Each detail field takes the value from the
                best-ranked row that actually has it, so a registrar's certificate number and
                a company page's scope text can both survive into one record.

  FACILITY      facility_scope is the STRONGEST facility evidence across all contributors, not
                the scope of whichever row won the detail fields. Those are different
                questions: a complete parent-only certificate should not erase another
                source's evidence that the Georgia site is covered.

  DISAGREEMENT  kept, never averaged away. `agreement.conflict` marks fields where sources
                disagree, `agreement.conflicts` lists the competing values, and `sources[]`
                preserves every original row so any merge decision can be re-litigated.

Absence records ("none identified", "no EV/battery standard identified") are real findings
about the evidence, not certifications, so they go to their own file.

Usage:
    python scripts/merge_final.py              # merge + LLM gap-fill from verified pages
    python scripts/merge_final.py --no-fill    # merge only, no model calls
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import llm_client  # noqa: E402
from collect_locations import _norm  # noqa: E402
from gapfill_run import (_LOW_VALUE_HOSTS, _field_grounded, _iso_dates,  # noqa: E402
                         _norm_ref)
from merge_sources import load_all  # noqa: E402
from normalize_certs import NONE_IDS  # noqa: E402

OUT_DIR = PKG_ROOT / "outputs" / "run2_gapfill"
CACHE = OUT_DIR / "verify_cache"
STATUS = OUT_DIR / "link_status.json"
CERTS_OUT = OUT_DIR / "certifications_merged.jsonl"
ABSENCE_OUT = OUT_DIR / "absences_merged.jsonl"

# How much a source type is worth when deciding which row supplies a value.
SOURCE_RANK = {
    "registrar_database": 6, "official_certificate_pdf": 5, "company_certificate_pdf": 4,
    "government_database": 3, "company_page": 2, "news_directory": 1, "none": 0, "": 0,
}
CERT_RANK = ["confirmed_active", "active_expiry_unknown", "confirmed_expired",
             "company_claim_only", "parent_only", "affiliate_only", "historical_only",
             "conflicting", "unclear", "not_found_after_search", "search_failed",
             "source_unavailable"]
FACILITY_RANK = ["facility_confirmed", "parent_only", "affiliate_only", "unclear",
                 "facility_not_confirmed", "not_applicable", ""]
DETAIL_FIELDS = ("certification_body", "reference_no", "issue_date", "expiry_date", "scope")


def _key(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()


def _page_text(url: str) -> str:
    p = CACHE / f"{_key(url)}.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def quote_supported(quote: str, page: str) -> str:
    """'yes' | 'no' | 'no_quote' | 'no_page' — does the page actually say this?

    Three shapes have to pass, because all three are honest quotes:
      * the whole quote, verbatim;
      * a solid prefix, since quotes get truncated mid-sentence at 500-600 chars;
      * any substantial fragment of an ellipsis-joined search snippet. Snippets arrive as
        "Title ... middle of a sentence", which can never match verbatim — treating those as
        contradicted would condemn evidence the page plainly carries.
    """
    if not quote.strip():
        return "no_quote"
    if not page.strip():
        return "no_page"
    nq, np_ = _norm(quote), _norm(page)
    if nq in np_:
        return "yes"
    toks = nq.split()
    for n in (12, 8, 6):
        if len(toks) >= n and " ".join(toks[:n]) in np_:
            return "yes"
    for frag in re.split(r"\.{3}|…", quote):
        ftoks = _norm(frag).split()
        if len(ftoks) >= 6 and " ".join(ftoks) in np_:
            return "yes"
        for n in (10, 6):                  # fragments are themselves often clipped
            if len(ftoks) >= n and " ".join(ftoks[:n]) in np_:
                return "yes"
    return "no"


def link_verdict(ls: dict, has_url: bool) -> str:
    """What a failed fetch actually means. 403 from indeed.com or sec.gov is an anti-bot
    block, not a dead link — reporting those as 'broken' would condemn evidence that is
    perfectly fine in a browser. Only 404/410 assert the page is gone."""
    if not has_url:
        return "no_url"
    if not ls:
        return "unchecked"
    if ls.get("ok"):
        return "reachable"
    st = ls.get("status")
    if st in (403, 406, 202):
        return "blocked_by_site"
    if st in (404, 410):
        return "gone"
    if st == 200:
        return "no_text_extracted"
    return "unreachable"


def _rank(seq: list[str], v: str) -> int:
    try:
        return seq.index(v)
    except ValueError:
        return len(seq)


def strength(src: dict) -> tuple:
    """Sort key for 'best evidence'. Verified support outranks source type: a company page
    whose quote checks out beats a registrar URL that 404s."""
    return (
        0 if src.get("low_value_source") else 1,   # job boards/aggregators never win a field
        2 if src["quote_supported"] == "yes" else (1 if src["quote_supported"] in
                                                   ("no_quote", "no_page") else 0),
        1 if src["link_ok"] else 0,
        SOURCE_RANK.get(src["source_type"], 0),
        -_rank(CERT_RANK, src["cert_status"]),
        sum(1 for f in DETAIL_FIELDS if src.get(f)),
    )


def build_records(rows: list[dict], links: dict) -> tuple[list[dict], list[dict]]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["record_no"], r["canonical_id"])].append(r)

    certs, absences = [], []
    for (rec, cid), grp in sorted(groups.items(), key=lambda kv: (int(kv[0][0] or 0), kv[0][1])):
        sources, seen = [], set()
        for r in grp:
            url = r["source_url"]
            ls = links.get(url, {})
            sig = (r["origin"], url, r["evidence_quote"][:200], r["cert_status"])
            if sig in seen:
                continue                    # exact duplicate row from the same origin
            seen.add(sig)
            sources.append({
                "origin": r["origin"],
                "certification_as_written": r["certification"],
                "cert_status": r["cert_status"],
                "facility_status": r["facility_status"],
                "source_type": r["source_type"],
                "source_url": url,
                "link_status": ls.get("status") if url else None,
                "link_ok": bool(ls.get("ok")) if url else False,
                "link_verdict": link_verdict(ls, bool(url)),
                "low_value_source": bool(url) and any(h in url.lower()
                                                      for h in _LOW_VALUE_HOSTS),
                "link_redirected": bool(ls.get("redirected")) if url else False,
                "quote_supported": quote_supported(r["evidence_quote"], _page_text(url))
                if url else ("no_quote" if not r["evidence_quote"].strip() else "no_page"),
                "evidence_quote": r["evidence_quote"][:600],
                "confidence": r["confidence"],
                "notes": r["notes"][:400],
                **{f: r[f] for f in DETAIL_FIELDS},
            })
        sources.sort(key=strength, reverse=True)
        best = sources[0]

        company = next((r["company"] for r in grp if r["company"]), "")
        location = next((r["georgia_location"] for r in grp if r["georgia_location"]), "")

        base = {
            "record_no": int(rec) if str(rec).isdigit() else rec,
            "company": company,
            "georgia_location": location,
            "family": grp[0]["family"],
            "domain": grp[0]["domain"],
        }

        if cid in NONE_IDS:
            absences.append({**base, "absence_type": cid.strip("_"),
                             "meaning": grp[0]["family"],
                             "reported_by": sorted({s["origin"] for s in sources}),
                             "n_sources": len(sources),
                             "notes": best["notes"],
                             "queries_recorded": any("quer" in (s["notes"] or "").lower()
                                                     for s in sources)})
            continue

        # Facility scope: strongest evidence anywhere in the group, independent of which row
        # supplied the detail fields — but only among sources good enough to carry the claim.
        # Without the quality bar the weakest source wins by construction: a LinkedIn page
        # saying "Aurubis Richmond" would mark the record facility_confirmed while the actual
        # certificate PDF covers a plant in Bulgaria.
        qualified = [s for s in sources
                     if s["facility_status"]
                     and s["quote_supported"] == "yes"
                     and s["link_verdict"] in ("reachable", "blocked_by_site")
                     and not s["low_value_source"]]
        pool = qualified or [s for s in sources if s["facility_status"]]
        fac = min((s["facility_status"] for s in pool),
                  key=lambda v: _rank(FACILITY_RANK, v), default="")
        fac_src = next((s["origin"] for s in pool if s["facility_status"] == fac), "")
        fac_basis = "verified_source" if qualified else (
            "unverified_source" if pool else "none")

        rec_out = {
            **base,
            "certification": cid,
            "cert_status": best["cert_status"],
            "facility_scope": fac,
            "facility_scope_from": fac_src,
            "facility_scope_basis": fac_basis,
        }
        provenance = {}
        for f in DETAIL_FIELDS:
            pick = next((s for s in sources if str(s.get(f) or "").strip()), None)
            rec_out[f] = (pick[f].strip() if pick else None)
            if pick:
                provenance[f] = pick["origin"]

        # conflicts
        conflicts = {}
        for f in ("cert_status", "facility_status"):
            vals = sorted({s[f] for s in sources if s[f]})
            if len(vals) > 1:
                conflicts[f] = vals
        for f in DETAIL_FIELDS:
            vals = sorted({re.sub(r"\s+", " ", str(s[f]).strip()) for s in sources
                           if str(s.get(f) or "").strip()})
            if len(vals) > 1:
                conflicts[f] = vals

        rec_out["evidence"] = {
            "best_source_url": best["source_url"] or None,
            "best_source_type": best["source_type"] or None,
            "evidence_quote": best["evidence_quote"] or None,
            "quote_supported_by_page": best["quote_supported"],
            "link_status": best["link_status"],
            "link_verdict": best["link_verdict"],
        }
        rec_out["verification"] = {
            "sources_total": len(sources),
            "links_reachable": sum(1 for s in sources if s["link_ok"]),
            "quotes_confirmed": sum(1 for s in sources if s["quote_supported"] == "yes"),
            "quotes_contradicted": sum(1 for s in sources if s["quote_supported"] == "no"),
            "links_blocked_by_site": sum(1 for s in sources
                                         if s["link_verdict"] == "blocked_by_site"),
            "links_gone": sum(1 for s in sources if s["link_verdict"] == "gone"),
        }
        rec_out["agreement"] = {
            "origins": sorted({s["origin"] for s in sources}),
            "n_origins": len({s["origin"] for s in sources}),
            "conflict": bool(conflicts),
            "conflicts": conflicts or None,
        }
        rec_out["field_provenance"] = provenance
        rec_out["sources"] = sources
        certs.append(rec_out)
    return certs, absences


# ------------------------------------------------------------------ LLM gap fill

FILL_PROMPT = """You are reading the text of ONE web page. Extract ONLY the certificate \
details for the certification named below, for the company named below.

Respond with ONLY a JSON object:
{"certification_body": "<registrar/body verbatim, or \\"\\">",
 "reference_no": "<certificate/registration number verbatim, or \\"\\">",
 "issue_date": "<issue date exactly as written, or \\"\\">",
 "expiry_date": "<expiry/valid-until date exactly as written, or \\"\\">",
 "scope": "<certificate scope text verbatim, one line, or \\"\\">"}

Rules: copy VERBATIM from the page. Never infer or reformat. Use "" for anything not present.
If the page is about a different company or a different standard, return all "".
"""


def _resume_fill(records: list[dict]) -> int:
    """Carry forward fill results from a previous run of this script.

    The merge itself is cheap and deterministic, but each fill is a model call over a page —
    a few hours' work in total. Without this, any interruption throws all of it away."""
    if not CERTS_OUT.exists():
        return 0
    prev = {}
    for line in CERTS_OUT.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("fill"):
            prev[(o["record_no"], o["certification"])] = o
    n = 0
    for r in records:
        old = prev.get((r["record_no"], r["certification"]))
        if not old:
            continue
        for f in DETAIL_FIELDS:
            if not r.get(f) and old.get(f):
                r[f] = old[f]
        r["fill"] = old["fill"]
        r.setdefault("field_provenance", {}).update(
            {k: v for k, v in (old.get("field_provenance") or {}).items()
             if str(v).startswith("llm_fill")})
        n += 1
    return n


def _write(certs: list[dict], absences: list[dict]) -> None:
    # Uniform key set on every line: a consumer reading this JSONL should never have to
    # test for a key's existence, only for its value.
    for r in certs:
        r.setdefault("fill", None)
        r.setdefault("field_provenance", {})
    with CERTS_OUT.open("w", encoding="utf-8") as f:
        for r in certs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with ABSENCE_OUT.open("w", encoding="utf-8") as f:
        for r in absences:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def fill_gaps(records: list[dict], model: str | None, limit: int = 0,
              checkpoint=None) -> int:
    """For records still missing certificate identity, re-read their verified pages.

    Every extracted value is grounded against that page's text before it is accepted — the
    same check pass C used — so this can only copy what is demonstrably on the page."""
    filled = 0
    targets = [r for r in records
               if not (r["certification_body"] and r["reference_no"] and r["expiry_date"])
               and not r.get("fill")
               and any(s["link_ok"] and _page_text(s["source_url"]) for s in r["sources"])]
    if limit:
        targets = targets[:limit]
    print(f"[fill] {len(targets)} record(s) missing certificate identity with a readable page")

    for i, r in enumerate(targets, 1):
        pages = [(s["source_url"], _page_text(s["source_url"])) for s in r["sources"]
                 if s["link_ok"] and _page_text(s["source_url"])]
        pages.sort(key=lambda p: -len(p[1]))
        url, text = pages[0]
        user = (f"Company: {r['company']}\nCertification: {r['certification']}\n\n"
                f"Page ({url}):\n{text[:14000]}")
        try:
            raw = llm_client.chat([{"role": "system", "content": FILL_PROMPT},
                                   {"role": "user", "content": user}], model=model)
            got = llm_client.extract_json(raw)
        except Exception as e:
            print(f"  [{i}/{len(targets)}] #{r['record_no']} {r['certification']}: {e}")
            continue
        if not isinstance(got, dict):
            continue
        ev_refs, ev_dates = _norm_ref(text), _iso_dates(text)
        added = []
        for f, kind in (("certification_body", "text"), ("reference_no", "ref"),
                        ("issue_date", "date"), ("expiry_date", "date"), ("scope", "text")):
            if r.get(f):
                continue
            v = str(got.get(f, "") or "").strip()
            if v and _field_grounded(kind, v, text, ev_refs, ev_dates):
                r[f] = v
                if not r.get("field_provenance"):
                    r["field_provenance"] = {}
                r["field_provenance"][f] = f"llm_fill:{url}"
                added.append(f)
        if not added:
            # Record the attempt even when nothing was extractable, so a re-run does not
            # repeat ninety minutes of model calls that already came back empty.
            # NB: _write() writes an explicit `fill: null`, so setdefault() is not enough.
            r["fill"] = {"fields_added": [], "from_url": url, "found_nothing": True}
        if added:
            filled += 1
            r["fill"] = {"fields_added": added, "from_url": url}
            print(f"  [{i}/{len(targets)}] #{r['record_no']} {r['certification']}: "
                  f"+{', '.join(added)}", flush=True)
            if checkpoint:
                checkpoint()
        elif i % 25 == 0:
            print(f"  [{i}/{len(targets)}] ...", flush=True)
    return filled


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fill", action="store_true")
    ap.add_argument("--fill-limit", type=int, default=0)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    import check_certifications as cc
    cc._load_env()          # LLM_MODEL lives in .env; without this the client 404s on the default

    rows = load_all()
    links = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    print(f"{len(rows)} source rows, {len(links)} URLs with a recorded status")

    certs, absences = build_records(rows, links)
    print(f"merged into {len(certs)} certification records and {len(absences)} absence records")

    resumed = _resume_fill(certs)
    if resumed:
        print(f"[fill] carried forward {resumed} record(s) from a previous run")
    if not args.no_fill:
        import os
        model = args.model or os.environ.get("LLM_MODEL")
        if llm_client.ping():
            n = fill_gaps(certs, model, args.fill_limit,
                          checkpoint=lambda: _write(certs, absences))
            print(f"[fill] added grounded details to {n} record(s)")
        else:
            print("[fill] local LLM not reachable — skipping gap fill")

    _write(certs, absences)
    print(f"\nwrote {CERTS_OUT} ({len(certs)} lines)")
    print(f"wrote {ABSENCE_OUT} ({len(absences)} lines)")


if __name__ == "__main__":
    main()
