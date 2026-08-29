"""Append pass E's explicit EV/battery negatives to absences_merged.jsonl.

Deliberately NOT a re-merge. `merge_sources.load_notes` falls back to the lossy
reconstruction of the overwritten notes.md (670 rows rebuilt from 1,153 objects, 379 quotes
truncated), and llm_a/llm_b are the sole source for 236 of the 662 merged certifications.
Re-running the merge would trade good rows for lossy ones — and gain nothing, because pass E
produced no new certification: its single grounded hit (#84 ISO 26262) was already grounded
by pass B at the same parent_only scope.

Pass E's negatives get their own `absence_type` — "no_ev_delta", NOT "no_ev". build_key.py
counts `absence_type == "no_ev"` for its "N companies carry an explicit negative" sentence,
and 8 records with a grounded pass-B functional-safety hit (83, 99, 100, 108, 130, 136, 137,
187) legitimately also carry a pass-E negative: holding ISO 26262 and holding no UNECE R100
are both true at once. Folding them into one bucket would make the key contradict itself.

Idempotent: re-running replaces any existing run2_passE absence rows rather than duplicating.

    python3 scripts/append_passE_absences.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PKG_ROOT / "outputs" / "run2_gapfill"
PASS_E = OUT_DIR / "passE_ev.csv"
ABSENCES = OUT_DIR / "absences_merged.jsonl"

NEGATIVE = "no EV/battery standard identified (delta targets)"
ABSENCE_TYPE = "no_ev_delta"
ORIGIN = "run2_passE"

# The standards pass E named in its queries. Recorded on every row so a reader can see what
# the negative actually covers instead of inferring it from the pass name.
DELTA_TARGETS = ("UNECE R100", "ISO 12405", "GB 38031", "SAE J2929", "SAE J2380",
                 "UL 2231", "IEC 62660-1/-2/-3")


def build_rows() -> list[dict]:
    rows = []
    with PASS_E.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["certification"] != NEGATIVE:
                continue
            rows.append({
                "record_no": int(r["record_no"]),
                "company": r["company"],
                "georgia_location": r.get("location", ""),
                "family": "No EV/battery standard identified (delta targets)",
                "domain": "None",
                "absence_type": ABSENCE_TYPE,
                "meaning": ("No EV/battery standard identified among the delta targets "
                            "pass B never queried: " + ", ".join(DELTA_TARGETS)),
                "reported_by": [ORIGIN],
                "n_sources": 1,
                "notes": r.get("notes", ""),
                "queries_recorded": bool(r.get("queries_tried", "").strip()),
                "queries_tried": r.get("queries_tried", ""),
                "urls_fetched": r.get("urls_fetched", ""),
                "targets_tested": list(DELTA_TARGETS),
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    existing = [json.loads(line) for line in ABSENCES.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    kept = [r for r in existing if ORIGIN not in r.get("reported_by", [])]
    new = build_rows()

    print(f"existing absences      : {len(existing)}")
    print(f"  minus prior pass E   : {len(kept)}")
    print(f"pass E negatives to add: {len(new)}")
    print(f"result                 : {len(kept) + len(new)}")
    by_type: dict[str, int] = {}
    for r in kept + new:
        by_type[r["absence_type"]] = by_type.get(r["absence_type"], 0) + 1
    print("absence_type counts    :", by_type)

    if args.dry_run:
        print("\n--dry-run: nothing written. Sample row:")
        print(json.dumps(new[0], indent=2, ensure_ascii=False))
        return

    with ABSENCES.open("w", encoding="utf-8") as f:
        for r in kept + new:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {ABSENCES}")


if __name__ == "__main__":
    main()
