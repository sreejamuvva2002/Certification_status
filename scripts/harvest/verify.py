"""QA gate. Re-checks the pipeline's own output before anything is published.

The checks that matter most are the ones that catch bugs in this pipeline
rather than in the sources: every stored quote is independently re-verified
against its stored evidence, so a regression in grounding.py surfaces here
instead of in the report.

Shortfalls against the brief's minimum counts are reported, never papered over.
The correct response to "too few papers" is to retrieve more — not to relax a
grounding threshold or promote unverifiable cells.
"""
from __future__ import annotations

import json
import os
import re

from . import grounding, patents, stages, store

REQUIRED_ORIGINALS = 40
REQUIRED_REVIEWS = 15
REQUIRED_FAMILIES = 30

A_REPORT = "20_verification.json"
A_ISSUES = "20_issues.csv"
A_COVERAGE = "20_coverage.csv"

REVIEW_TYPES = {"review", "systematic_review", "meta_analysis"}


def p(out_dir: str, name: str) -> str:
    return os.path.join(out_dir, name)


def _datacite(doi: str) -> str:
    """Title if the DOI resolves at DataCite, else ''. Fallback for non-Crossref DOIs."""
    from . import cache
    res = cache.fetch_json(f"https://api.datacite.org/dois/{doi}", source="datacite",
                           ttl_days=None, retries=1)
    if res["code"] != "ok" or not res.get("data"):
        return ""
    titles = (((res["data"].get("data") or {}).get("attributes") or {}).get("titles") or [])
    return (titles[0].get("title") if titles else "") or ""


def stage_verify(out_dir: str, srcs: dict) -> dict:
    rows = store.read_jsonl(p(out_dir, stages.A_ROWS))
    cells = store.read_jsonl(p(out_dir, stages.A_CELLS))
    pat_rows = store.read_jsonl(p(out_dir, patents.A_PAT_ROWS))
    pat_cells = store.read_jsonl(p(out_dir, patents.A_PAT_CELLS))
    issues: list[dict] = []

    def issue(kind: str, ident: str, detail: str, severity: str = "warn") -> None:
        issues.append({"kind": kind, "id": ident, "detail": detail[:300], "severity": severity})

    # 1. DOI existence and title agreement, straight from Crossref.
    crossref = srcs.get("crossref")
    checked = resolved = 0
    if crossref is not None:
        for r in rows:
            doi = r.get("doi") or ""
            if not doi:
                issue("no_doi", r["work_id"], "row has no DOI", "warn")
                continue
            checked += 1
            meta = crossref.by_doi(doi)
            if not meta or not meta.get("title"):
                # Not every valid DOI is registered with Crossref. Theses,
                # datasets and repository deposits are registered with DataCite,
                # so a Crossref miss alone is not evidence the DOI is fake —
                # calling it an error would wrongly discard a real source.
                dc = _datacite(doi)
                if dc:
                    resolved += 1
                    issue("doi_datacite_only", doi,
                          f"resolves via DataCite, not Crossref: {dc[:90]}", "warn")
                else:
                    issue("doi_unresolved", doi,
                          "resolved by neither Crossref nor DataCite", "error")
                continue
            resolved += 1
            a = grounding.norm_loose(meta["title"]).split()
            b = grounding.norm_loose(r.get("reference", "")).split()
            overlap = len(set(a) & set(b)) / max(1, len(set(a)))
            if overlap < 0.5:
                issue("doi_title_mismatch", doi,
                      f"Crossref title overlap {overlap:.0%}: {meta['title'][:90]}", "error")

    # 2. Quote integrity — re-verify every stored quote against stored evidence.
    #    This catches regressions in grounding.py itself.
    works = {w["work_id"]: w for w in store.read_jsonl(p(out_dir, stages.A_WORKS))}
    ev_cache: dict[str, str] = {}
    bad_quotes = 0
    for c in cells:
        quote = c.get("quote") or ""
        if not quote or c.get("evidence_level") in ("metadata_only", "not_stated", "unverifiable"):
            continue
        wid = c["work_id"]
        if wid not in ev_cache:
            w = works.get(wid, {})
            ft = stages.read_fulltext(out_dir, wid)
            ev_cache[wid] = f"{w.get('title','')}\n\n{w.get('abstract','')}\n\n{ft}"
        if grounding.find_span(quote, ev_cache[wid]) is None:
            bad_quotes += 1
            issue("quote_not_in_source", f"{wid}:{c['field']}", quote[:120], "error")

    for c in pat_cells:
        quote = c.get("quote") or ""
        if not quote or c.get("evidence_level") in ("metadata_only", "not_stated", "unverifiable"):
            continue
        doc = patents.read_doc(out_dir, c.get("pub_number", ""))
        if doc and grounding.find_span(quote, doc) is None:
            bad_quotes += 1
            issue("quote_not_in_source", f"{c['family_id']}:{c['field']}", quote[:120], "error")

    # 3. Duplicates.
    seen_doi: dict[str, str] = {}
    for r in rows:
        doi = r.get("doi") or ""
        if doi and doi in seen_doi:
            issue("duplicate_doi", doi, f"also {seen_doi[doi]}", "error")
        elif doi:
            seen_doi[doi] = r["work_id"]
    seen_title: dict[frozenset, str] = {}
    for r in rows:
        key = stages._title_key(r.get("reference", ""))
        if len(key) < 5:
            continue
        for other, wid in seen_title.items():
            inter = len(key & other) / max(1, len(key | other))
            if inter >= 0.9:
                issue("near_duplicate_title", r["work_id"], f"~{wid} ({inter:.0%})", "warn")
                break
        seen_title[key] = r["work_id"]

    # 4. Counts against the brief's minimums.
    n_orig = sum(1 for r in rows if r.get("pub_type") == "original_research")
    n_rev = sum(1 for r in rows if r.get("pub_type") in REVIEW_TYPES)
    n_fam = len(pat_rows)
    if n_orig < REQUIRED_ORIGINALS:
        issue("shortfall_originals", "-", f"{n_orig}/{REQUIRED_ORIGINALS}", "error")
    if n_rev < REQUIRED_REVIEWS:
        issue("shortfall_reviews", "-", f"{n_rev}/{REQUIRED_REVIEWS}", "error")
    if n_fam < REQUIRED_FAMILIES:
        issue("shortfall_families", "-", f"{n_fam}/{REQUIRED_FAMILIES}", "error")

    # 5. Coverage matrix — the honest quality statistic for the methods section.
    coverage: list[dict] = []
    from . import schema
    for key, label, _mode in schema.LIT_COLS:
        rowcells = [c for c in cells if c["field"] == key]
        tally: dict[str, int] = {}
        for c in rowcells:
            tally[c["evidence_level"]] = tally.get(c["evidence_level"], 0) + 1
        coverage.append({
            "column": label, "field": key, "n": len(rowcells),
            "full_text_verified": tally.get("full_text_verified", 0),
            "abstract_only": tally.get("abstract_only", 0),
            "metadata_only": tally.get("metadata_only", 0),
            "not_stated": tally.get("not_stated", 0),
            "unverifiable": tally.get("unverifiable", 0),
            "blanked": sum(1 for c in rowcells if c["status"] == "ungrounded_blanked"),
        })

    # 6. Citation integrity for the authored prose.
    sections_dir = os.path.join(os.path.dirname(os.path.dirname(out_dir)),
                                "research", "1-mcp", "sections")
    known = {r.get("doi", "").lower() for r in rows if r.get("doi")}
    known |= {r["family_id"] for r in pat_rows}
    known |= {r.get("pub_number", "") for r in pat_rows}
    n_cites = 0
    if os.path.isdir(sections_dir):
        for name in sorted(os.listdir(sections_dir)):
            if not name.endswith(".md"):
                continue
            with open(os.path.join(sections_dir, name), encoding="utf-8") as fh:
                text = fh.read()
            for token in re.findall(r"\[@([^\]]+)\]", text):
                n_cites += 1
                ident = token.split(":", 1)[-1].strip().lower()
                if ident not in known and token.strip() not in known:
                    issue("citation_not_in_corpus", f"{name}:{token}",
                          "prose cites a source the pipeline never retrieved", "error")

    errors = [i for i in issues if i["severity"] == "error"]
    report = {
        "rows": len(rows), "cells": len(cells),
        "patent_families": n_fam, "patent_cells": len(pat_cells),
        "originals": n_orig, "reviews": n_rev,
        "required": {"originals": REQUIRED_ORIGINALS, "reviews": REQUIRED_REVIEWS,
                     "families": REQUIRED_FAMILIES},
        "doi_checked": checked, "doi_resolved": resolved,
        "bad_quotes": bad_quotes, "prose_citations": n_cites,
        "issues": len(issues), "errors": len(errors),
        "full_text_works": sum(1 for r in rows if r.get("fulltext_chars")),
    }
    store.write_csv(p(out_dir, A_ISSUES), issues, ["severity", "kind", "id", "detail"])
    store.write_csv(p(out_dir, A_COVERAGE), coverage,
                    ["column", "field", "n", "full_text_verified", "abstract_only",
                     "metadata_only", "not_stated", "unverifiable", "blanked"])
    with open(p(out_dir, A_REPORT), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(f"  rows={len(rows)} originals={n_orig}/{REQUIRED_ORIGINALS} "
          f"reviews={n_rev}/{REQUIRED_REVIEWS} families={n_fam}/{REQUIRED_FAMILIES}")
    print(f"  DOIs resolved {resolved}/{checked} | quote failures {bad_quotes} | "
          f"issues {len(issues)} ({len(errors)} errors)")
    if errors:
        kinds: dict[str, int] = {}
        for i in errors:
            kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
        print(f"  errors by kind: {kinds}")
    return report
