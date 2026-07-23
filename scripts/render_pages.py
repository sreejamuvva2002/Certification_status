"""Render one readable markdown page per GNEM record from certification_status.csv.

Each page lists the company, its unverified facility/address hints, then one block per
certification with the full research schema INCLUDING a source URL per certification.
Duplicate GNEM names are separate records, so pages are named <record_no>_<slug>.md.

Usage:
    python scripts/render_pages.py            # reads outputs/certification_status.csv
    python scripts/render_pages.py --csv ... --companies ... --pages-dir ...
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG_ROOT = HERE.parent
DEFAULT_CSV = PKG_ROOT / "outputs" / "certification_status.csv"
DEFAULT_COMPANIES = PKG_ROOT / "data" / "companies.csv"
DEFAULT_PAGES = PKG_ROOT / "outputs" / "companies"

# CSV field -> label shown on the page, in display order (one block per certification).
FIELDS = [
    ("cert_status", "certification_status"),
    ("facility_status", "facility_status"),
    ("certification_body", "certification_body"),
    ("reference_no", "reference_no"),
    ("issue_date", "issue_date"),
    ("expiry_date", "expiry_date"),
    ("scope", "scope"),
    ("source_type", "source_type"),
    ("source_url", "source_url"),
    ("evidence_quote", "evidence_quote"),
    ("confidence", "confidence"),
    ("notes", "notes"),
]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "company"


def _val(row: dict, key: str) -> str:
    v = str(row.get(key, "") or "").strip()
    if v:
        return v
    return "not visible in sources checked" if key in (
        "certification_body", "reference_no", "issue_date", "expiry_date",
        "scope", "source_url", "evidence_quote") else "—"


def render(csv_path: Path, companies_path: Path, pages_dir: Path) -> int:
    # Address hints live in the source sheet, keyed by record_no.
    addr: dict[str, dict] = {}
    if companies_path.exists():
        with companies_path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                addr[str(r.get("record_no", ""))] = r

    # Group cert rows by record_no, preserving CSV order.
    by_rec: dict[str, list[dict]] = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            by_rec.setdefault(str(r.get("record_no", "")), []).append(r)

    pages_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for rec, rows in by_rec.items():
        head = rows[0]
        src = addr.get(rec, {})
        lines = [
            f"company: {head.get('company', '')}",
            f"record_no: {rec}",
            f"facility: {src.get('location', '') or head.get('location', '') or 'unknown (sheet hint missing)'}",
            f"address: {src.get('address', '') or 'unknown'}",
            "",
            "NOTE: facility/address above come from the source sheet and are unverified hints.",
            "",
        ]
        for row in rows:
            lines.append(f"{row.get('certification', 'none identified')}:")
            for key, label in FIELDS:
                lines.append(f"  {label}: {_val(row, key)}")
            lines.append("")
        lines.append(f"checked_at: {head.get('checked_at', '')}  "
                     f"model: {head.get('model', '')}  backend: {head.get('backend', '')}")
        path = pages_dir / f"{int(rec):03d}_{slugify(head.get('company', ''))}.md" if rec.isdigit() \
            else pages_dir / f"{slugify(head.get('company', ''))}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        written += 1
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    ap.add_argument("--pages-dir", type=Path, default=DEFAULT_PAGES)
    args = ap.parse_args()
    if not args.csv.exists():
        raise SystemExit(f"{args.csv} not found — run check_certifications.py first.")
    n = render(args.csv, args.companies, args.pages_dir)
    print(f"Wrote {n} company page(s) to {args.pages_dir}/")


if __name__ == "__main__":
    main()
