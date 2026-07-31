"""Deliverable tables: CSV, XLSX and Markdown.

Outputs land in `research/1-mcp/` (committed) rather than `outputs/` (gitignored),
because the tables are the deliverable while the JSONL artifacts are workings.

Each table ships with its evidence sheet — one row per cell with the quote and
evidence level that back it. A reader can check any number in the report against
the sentence it came from without re-running anything.
"""
from __future__ import annotations

import os

from . import patents, schema, stages, store

LEVEL_MARK = {
    "full_text_verified": "",     # unmarked: the strongest evidence
    "abstract_only": " ᵃ",
    "metadata_only": "",
    "not_stated": "",
    "unverifiable": "",
}
LEVEL_NOTE = """
Evidence markers: values with **ᵃ** were verified against the paper's abstract only —
full text was not openly available, so process detail could not be checked.
Empty cells are one of two different things, distinguished in the evidence sheet:
*not stated* (we hold the full text and it does not report this) or *unverifiable*
(we could not obtain enough of the paper to know). They are never merged.
"""


def out_paths(out_dir: str) -> tuple[str, str]:
    repo = os.path.dirname(os.path.dirname(os.path.abspath(out_dir)))
    base = os.path.join(repo, "research", "1-mcp")
    return base, os.path.join(base, "tables")


def _display(row: dict, cells_by_field: dict[str, dict], key: str) -> str:
    val = row.get(key, "")
    if not val:
        return ""
    cell = cells_by_field.get(key)
    if not cell:
        return str(val)
    return str(val) + LEVEL_MARK.get(cell.get("evidence_level", ""), "")


def stage_emit(out_dir: str) -> dict:
    base, tables = out_paths(out_dir)
    store.ensure_dir(tables)

    rows = store.read_jsonl(stages.p(out_dir, stages.A_ROWS))
    cells = store.read_jsonl(stages.p(out_dir, stages.A_CELLS))
    pat_rows = store.read_jsonl(stages.p(out_dir, patents.A_PAT_ROWS))
    pat_cells = store.read_jsonl(stages.p(out_dir, patents.A_PAT_CELLS))
    coverage = store.read_csv(stages.p(out_dir, "20_coverage.csv"))

    # Literature ------------------------------------------------------------
    lit_cols = schema.LIT_KEYS + schema.LIT_PROVENANCE
    store.write_csv(os.path.join(tables, "literature.csv"), rows, lit_cols)
    store.write_csv(os.path.join(tables, "literature_evidence.csv"), cells,
                    ["work_id", "doi", "field", "value", "unit", "raw", "evidence_level",
                     "status", "quote", "locator", "checks"])

    by_work: dict[str, dict[str, dict]] = {}
    for c in cells:
        by_work.setdefault(c["work_id"], {})[c["field"]] = c

    originals = [r for r in rows if r.get("pub_type") == "original_research"]
    reviews = [r for r in rows if r.get("pub_type") in verify_review_types()]
    others = [r for r in rows if r not in originals and r not in reviews]

    md = ["# Literature table", "",
          f"{len(originals)} original research papers, {len(reviews)} reviews, "
          f"{len(others)} other publication types.", LEVEL_NOTE]
    for label, group in (("Original research", originals), ("Reviews", reviews),
                         ("Other", others)):
        if not group:
            continue
        md += [f"\n## {label} ({len(group)})", ""]
        display = [{k: _display(r, by_work.get(r["work_id"], {}), k) for k in schema.LIT_KEYS}
                   for r in group]
        md.append(store.md_table(display, schema.LIT_LABELS))
    with open(os.path.join(tables, "literature.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    # Patents ---------------------------------------------------------------
    pat_cols = schema.PAT_KEYS + schema.PAT_PROVENANCE
    store.write_csv(os.path.join(tables, "patents.csv"), pat_rows, pat_cols)
    store.write_csv(os.path.join(tables, "patents_evidence.csv"), pat_cells,
                    ["family_id", "pub_number", "field", "value", "evidence_level",
                     "status", "quote", "checks"])
    pmd = ["# Patent-family table", "",
           f"{len(pat_rows)} families. Families are clustered heuristically from title, "
           "assignee and priority date — INPADOC family data was not available. "
           "No freedom-to-operate or patentability opinion is expressed or implied.", ""]
    pmd.append(store.md_table(pat_rows, schema.PAT_LABELS))
    with open(os.path.join(tables, "patents.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(pmd) + "\n")

    # Workbook --------------------------------------------------------------
    sheets = {
        "Literature": (lit_cols, rows),
        "Literature evidence": (["work_id", "doi", "field", "value", "evidence_level",
                                 "status", "quote", "checks"], cells),
        "Patents": (pat_cols, pat_rows),
        "Patent evidence": (["family_id", "pub_number", "field", "value",
                             "evidence_level", "status", "quote"], pat_cells),
    }
    if coverage:
        sheets["Coverage"] = (list(coverage[0].keys()), coverage)
    store.write_xlsx(os.path.join(tables, "1mcp_evidence.xlsx"), sheets)

    print(f"  wrote tables to {tables}")
    print(f"    literature.csv     {len(rows)} rows x {len(lit_cols)} cols")
    print(f"    literature_evidence.csv {len(cells)} cells")
    print(f"    patents.csv        {len(pat_rows)} families x {len(pat_cols)} cols")
    return {"rows": len(rows), "cells": len(cells), "patents": len(pat_rows)}


def verify_review_types() -> set[str]:
    return {"review", "systematic_review", "meta_analysis"}
