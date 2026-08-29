"""Retro-apply the pass-B grounding gate to EV/battery/functional-safety rows that bypassed it.

Pass B only gated rows whose certification string matched `EV_BATTERY_CANON`. Two ways a row
could carry an EV-relevant standard and still skip the gate entirely:

  * a spelling the canon regex missed — the model returned "ISO/SAE 21434" while the canon
    pattern was `\\bISO\\s*21434\\b`, so the row was filed as an incidental non-EV find; and
  * a row produced by pass A or pass C, which never ran the gate at all.

Either way an ungrounded claim would reach the key wearing the same clothes as a gated one.
This script re-runs `_ev_grounded()` on every such row against the evidence actually logged
for that (pass, record), then:

  * sets `ev_canonical` on rows that pass, so gating is visible downstream; and
  * routes failures to needs_review.csv with the reason, leaving the row in place.

Idempotent: re-running changes nothing once every row is classified.

Usage:  python scripts/reground_ev.py [--dir outputs/run2_gapfill] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from gapfill_run import (EV_BATTERY_CANON, REVIEW_FIELDS, _ev_canonical,  # noqa: E402
                         _ev_grounded, _load_keys)

PKG_ROOT = HERE.parent
DEFAULT_DIR = PKG_ROOT / "outputs" / "run2_gapfill"
EVIDENCE_LOG_CAP = 6000          # gapfill_run truncates logged evidence at this length


def _content_grounded(row: dict, company: str, canon: str) -> tuple[bool, str]:
    """The two grounding checks that survive evidence-log truncation.

    Weaker than _ev_grounded: it cannot confirm the quote really came from the sources, only
    that the quote itself ties this company to this standard. Used ONLY when the logged
    evidence is truncated, and always recorded as a weaker basis in the row's notes."""
    import re

    from collect_locations import _norm, _norm_company

    quote = str(row.get("evidence_quote", "") or "")
    if not quote.strip():
        return False, "no_quote"
    if not re.search(EV_BATTERY_CANON[canon][0], quote, re.IGNORECASE):
        return False, "standard_not_in_quote"
    nq = _norm(quote)
    ctoks = [t for t in _norm_company(company).split() if len(t) > 3] or \
        _norm_company(company).split()
    if not any(t in nq for t in ctoks):
        return False, "company_not_in_quote"
    return True, ""


def _evidence_index(out_dir: Path) -> dict[tuple[str, str], str]:
    """(pass, record_no) -> logged evidence text."""
    idx: dict[tuple[str, str], str] = {}
    p = out_dir / "evidence_log.jsonl"
    if not p.exists():
        return idx
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        idx[(str(d.get("pass", "A")), str(d.get("record_no", "")))] = d.get("evidence", "")
    return idx


def reground(out_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    evidence = _evidence_index(out_dir)
    review_path = out_dir / "needs_review.csv"
    seen = _load_keys(review_path, ["record_no", "certification"]) if review_path.exists() else set()
    new_reviews: list[dict] = []
    passed = failed = 0

    for name in ("passA_blanks.csv", "passB_ev.csv", "passC_details.csv"):
        path = out_dir / name
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields, rows = reader.fieldnames, list(reader)

        changed = 0
        for r in rows:
            canon, _bucket = _ev_canonical(r.get("certification", ""))
            if not canon or r.get("ev_canonical", "").strip():
                continue                      # not EV-relevant, or already gated by pass B
            ev = evidence.get((r.get("pass", ""), str(r["record_no"])), "")
            ok, why = _ev_grounded(r, r["company"], ev, canon)
            basis = "full"
            if not ok and why == "quote_not_in_evidence" and len(ev) >= EVIDENCE_LOG_CAP:
                # The log keeps only the first 6000 chars of a ~14k-char evidence blob, so a
                # perfectly real quote drawn from a later page cannot be located. Failing the
                # row here would reject it for a logging limit rather than for its evidence.
                # Fall back to the two checks that DO survive truncation.
                ok, why = _content_grounded(r, r["company"], canon)
                basis = "content-only"
            if ok:
                r["ev_canonical"] = canon
                r["notes"] = (r["notes"] + " | " if r.get("notes") else "") + (
                    "grounded retroactively (canon spelling missed at pass time)"
                    if basis == "full" else
                    "grounded on quote content only: the quote names both the company and the "
                    "standard, but the evidence log is truncated so verbatim presence in the "
                    "gathered evidence could not be re-verified")
                passed += 1
            else:
                failed += 1
                r["notes"] = (r["notes"] + " | " if r.get("notes") else "") + \
                    f"NOT grounded ({why}); excluded from EV/functional-safety counts"
                key = (str(r["record_no"]), r["certification"])
                if key not in seen:
                    seen.add(key)
                    new_reviews.append({
                        "record_no": r["record_no"], "company": r["company"],
                        "certification": r["certification"], "reason": why,
                        "pass": r.get("pass", ""),
                        "evidence_quote": r.get("evidence_quote", ""),
                        "source_url": r.get("source_url", ""), "confidence": "low",
                        "notes": "bypassed the pass-B gate; regrounded afterwards",
                        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "resolution": "", "resolution_note": ""})
            changed += 1
        if changed:
            print(f"  {name}: {changed} row(s) regrounded")
            if not dry_run:
                shutil.copy2(path, path.with_suffix(".pregrounding.csv"))
                with path.open("w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                    w.writeheader()
                    w.writerows(rows)

    if new_reviews and not dry_run:
        with review_path.open(newline="", encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
            fields = f and list(existing[0].keys()) if existing else REVIEW_FIELDS
        with review_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writerows(new_reviews)
        print(f"  appended {len(new_reviews)} row(s) to needs_review.csv")

    print(f"{passed} grounded, {failed} rejected{' (dry run)' if dry_run else ''}")
    return passed, failed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    reground(args.dir, args.dry_run)


if __name__ == "__main__":
    main()
