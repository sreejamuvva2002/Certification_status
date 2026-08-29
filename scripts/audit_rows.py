"""Post-run audit of the gap-fill rows: demote evidence that cannot carry a certification claim.

Two failure modes showed up in the pass-A output that no amount of prompt wording prevents,
because both look like ordinary evidence to a model reading search results:

  low_value_source   The cited source is a job posting or a directory/aggregator listing
                     ("Quality Systems Analyst - ISO 9001 / IATF 16949 experience required").
                     A hiring ad mentioning a standard is not evidence the company holds it.
                     These hosts are already de-prioritised for page fetches, but the model
                     can still cite one from a search snippet.

  unusable_source    source_url is not an absolute http(s) URL — typically a search-engine
                     redirect stub like "/goto?url=CAESTw...". Provenance that cannot be
                     opened is not provenance.

Neither is deleted. The row is kept, its status is weakened to `unclear`, its confidence to
`low`, the reason is written into notes, and a copy goes to needs_review.csv so the demotion
is visible rather than silent. Originals are preserved as <file>.raw.csv.

Run AFTER the passes finish (it rewrites the pass CSVs in place).

Usage:  python scripts/audit_rows.py [--dir outputs/run2_gapfill] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from gapfill_run import _LOW_VALUE_HOSTS, REVIEW_FIELDS, _load_keys  # noqa: E402

PKG_ROOT = HERE.parent
DEFAULT_DIR = PKG_ROOT / "outputs" / "run2_gapfill"
ABSENCE = {"none identified", "no EV/battery standard identified",
           "(no certificate details found)"}


def classify(row: dict) -> str:
    """'' if the row's provenance is usable, else the reason it is not."""
    if row.get("certification", "").strip() in ABSENCE:
        return ""                       # absence rows carry queries+URLs by design
    url = (row.get("source_url") or "").strip()
    if not url:
        return ""                       # nothing claimed
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return "unusable_source"
    if any(h in url.lower() for h in _LOW_VALUE_HOSTS):
        return "low_value_source"
    return ""


def audit(out_dir: Path, dry_run: bool = False) -> int:
    review_path = out_dir / "needs_review.csv"
    seen = _load_keys(review_path, ["record_no", "certification"]) if review_path.exists() else set()
    new_reviews: list[dict] = []
    demoted = 0

    for name in ("passA_blanks.csv", "passB_ev.csv", "passC_details.csv"):
        path = out_dir / name
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields, rows = reader.fieldnames, list(reader)

        changed = 0
        for r in rows:
            reason = classify(r)
            if not reason:
                continue
            changed += 1
            note = ("cited source is a job posting or directory listing, not a certificate "
                    "or company statement" if reason == "low_value_source"
                    else "source_url is not an openable http(s) URL")
            r["notes"] = (r["notes"] + " | " if r.get("notes") else "") + f"demoted: {note}"
            r["cert_status"] = "unclear"
            r["confidence"] = "low"
            if reason == "unusable_source":
                r["source_url"] = ""
            key = (str(r["record_no"]), r["certification"])
            if key not in seen:
                seen.add(key)
                new_reviews.append({
                    "record_no": r["record_no"], "company": r["company"],
                    "certification": r["certification"], "reason": reason,
                    "pass": r.get("pass", ""), "evidence_quote": r.get("evidence_quote", ""),
                    "source_url": r.get("source_url", ""), "confidence": "low",
                    "notes": note,
                    "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        demoted += changed
        print(f"  {name}: {changed} row(s) demoted of {len(rows)}")
        if changed and not dry_run:
            shutil.copy2(path, path.with_suffix(".raw.csv"))
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)

    if new_reviews and not dry_run:
        exists = review_path.exists()
        with review_path.open("a" if exists else "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS, extrasaction="ignore")
            if not exists:
                w.writeheader()
            w.writerows(new_reviews)
        print(f"  appended {len(new_reviews)} row(s) to needs_review.csv")
    print(f"{demoted} row(s) demoted{' (dry run, nothing written)' if dry_run else ''}")
    return demoted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    audit(args.dir, args.dry_run)


if __name__ == "__main__":
    main()
