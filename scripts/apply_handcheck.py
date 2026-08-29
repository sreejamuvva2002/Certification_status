"""Apply the blocking hand-check of pass B to the data, and record every verdict.

The grounding gate proves a company token and a standard token share one sourced quote. It
cannot prove polarity, cannot tell a parent from a subsidiary, and cannot tell that "SSS" in
a semiconductor trade article is Sony Semiconductor Solutions rather than Southern Switches
Corp of Georgia. So every surviving hit and every near-miss was checked by hand against its
source before any EV/battery number was published. This script writes those verdicts down —
`handcheck_decisions.csv` — and applies the two corrections they produced.

Run once, after the passes and audit_rows.py, before normalize_certs.py.
"""
from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = PKG_ROOT / "outputs" / "run2_gapfill"

# record_no, company, claim as extracted, verdict, why (each checked against its source)
DECISIONS = [
    ("136", "Panasonic Automotive Systems Co.", "ISO 26262 / facility_confirmed", "accept",
     "Verified: UL issued its first tier-one ENTERPRISE-WIDE ISO 26262 ASIL D lifecycle "
     "process certification to Panasonic Automotive (Nov 2021). Panasonic Automotive Systems "
     "America is at 776 Highway 74 S, Peachtree City, GA, and an enterprise-wide scope covers "
     "it, so facility_confirmed stands."),
    ("137", "Panasonic Automotive Systems Co.", "ISO 26262 / facility_confirmed", "accept",
     "Same certificate as record 136 (duplicate GNEM record, kept separate by design)."),
    ("83", "Hyundai Motor Group", "ISO 26262 / affiliate_only", "accept",
     "Real, but the certificate belongs to Hyundai Mobis, an affiliate — affiliate_only is "
     "the correct scope and it is not a Georgia certificate."),
    ("84", "Hyundai Transys Georgia Powertrain", "ISO 26262 / parent_only", "accept",
     "Real: Hyundai Transys obtained ISO 26262 Functional Safety Management. Obtained by the "
     "Korean parent; the Georgia powertrain plant is not named."),
    ("99", "Hyundai MOBIS (Georgia)", "ISO 26262 / parent_only", "accept",
     "Real: ISO 26262:2018 2nd edition from Exida for a semiconductor development process in "
     "Korea. Not the Georgia facility."),
    ("130", "Hyundai Transys Georgia Seating Systems", "ISO 26262 (gate: standard_not_in_quote)",
     "accept_corrected",
     "Gate rejected it because the quote names 'Automotive Functional Safety' rather than the "
     "number. Verified real: certification from TUV Rheinland at the Hwaseong, Gyeonggi-do "
     "Electrification R&D Centre — so ISO 26262, parent_only."),
    ("82", "GLOVIS Georgia LLC", "UN 38.3 (gate: standard_not_in_quote)", "reject_corrected",
     "The UN 38.3 label is wrong — UN 38.3 is a battery transport TEST standard. What Hyundai "
     "Glovis actually won (May 2023) is IATA CEIV Lithium Batteries, an air-logistics handling "
     "certification. Recorded correctly as IATA CEIV Lithium Batteries, parent_only."),
    ("154", "SAFT America Inc.", "UL 2580 (gate: company_not_in_quote)", "reject",
     "Gate was right. The source is hawkerpowersource.com and the quote describes HAWKER's "
     "battery line, not Saft's. Counting it would have attributed another manufacturer's "
     "certificate to Saft."),
    ("166", "Southern Switches Corp.", "ISO 26262 + ISO/SAE 21434 (gate: company_not_in_quote)",
     "reject",
     "Gate was right. 'SSS' in the source is Sony Semiconductor Solutions, not Southern "
     "Switches Corp — a wrong-company attribution to a Georgia switch manufacturer."),
    ("116", "Minebea AccessSolutions USA Inc.", "ISO 26262 (gate: company_not_in_quote)", "reject",
     "Evidence is the fragment 'ISO26262 Compliance' on the European affiliate's site. "
     "'Compliance' is not certification and the site is not the US entity."),
    ("173", "TCI Powder Coatings", "UL 1332 listing (catch-all)", "reject_not_battery",
     "Catch-all fired on the UL number shape, as designed. UL 1332 is a powder-coating "
     "product listing, not a battery standard. Stays a UL listing."),
    # --- second round: rows the corrected ISO/SAE 21434 canon pulled back through the gate
    ("100", "Lear Corporation", "ISO/SAE 21434 (re-gated)", "accept",
     "Grounded against re-gathered full evidence. Held by the parent, so parent_only."),
    ("187", "Valeo", "ISO/SAE 21434 (re-gated)", "accept",
     "Grounded against re-gathered full evidence. Held by the parent, so parent_only."),
    ("28", "Mando America Corp.", "ISO/SAE 21434 (re-gated, demoted)", "reject_but_probably_real",
     "The quote — 'Attainment of Automotive Cybersecurity Global ISO/SAE 21434 Certification "
     "2022' — is from HL Mando's own corporate timeline, so the certification is probably "
     "genuine. It belongs to the Korean parent HL Mando, not the Georgia plant, and it did "
     "not ground against re-gathered evidence, so it stays in needs_review rather than being "
     "counted."),
    ("136", "Panasonic Automotive Systems Co.", "ISO/SAE 21434 (re-gated, demoted)", "reject",
     "The quote names Panasonic Automotive Systems EUROPE receiving a TUV Nord certificate "
     "and never contains '21434'. Wrong entity and unsupported number."),
    ("137", "Panasonic Automotive Systems Co.", "ISO/SAE 21434 (re-gated, demoted)", "reject",
     "Same as record 136."),
    ("108", "Magna International", "ISO/SAE 21434 (re-gated, demoted)", "reject",
     "Did not ground against re-gathered evidence; run-1 scope was already not_applicable."),
    ("174", "TDK Components USA Inc.", "UL 1449 (catch-all)", "reject_not_battery",
     "UL 1449 covers surge protective devices, not batteries. The certificate is also issued "
     "to TDK (Zhuhai FTZ) Co., Ltd in China."),
]

# Rows the hand-check adds or corrects, written into passB_ev.csv.
CORRECTIONS = [
    {"record_no": "82", "company": "GLOVIS Georgia LLC",
     "certification": "IATA CEIV Lithium Batteries", "cert_status": "parent_only",
     "facility_status": "parent_only", "confidence": "medium",
     "source_type": "news_directory",
     "source_url": "https://www.kedglobal.com/logistics/newsView/ked202305300002",
     "evidence_quote": "Hyundai Glovis wins certification for lithium battery air transport "
                       "(IATA CEIV Lithium Batteries, May 2023)",
     "scope": "Air logistics handling, transport and storage of lithium batteries",
     "notes": "HAND-CHECKED correction: pass B extracted this as 'UN 38.3', which is wrong — "
              "UN 38.3 is a battery transport test standard, this is IATA's CEIV Lithium "
              "Batteries logistics certification. Held by the Korean parent Hyundai Glovis, "
              "not the Georgia entity."},
    {"record_no": "130", "company": "Hyundai Transys Georgia Seating Systems",
     "certification": "ISO 26262", "cert_status": "confirmed_active",
     "facility_status": "parent_only", "confidence": "medium",
     "source_type": "news_directory",
     "source_url": "https://www.asiae.co.kr/en/article/2025021808413511048",
     "evidence_quote": "Hyundai Transys Obtains International Standard Certification for "
                       "Automotive Functional Safety ... received the certification from "
                       "TUV Rheinland ... at its Electrification Research and Development "
                       "Center in Hwaseong, Gyeonggi-do Province.",
     "scope": "Automotive functional safety management, Electrification R&D Centre (Korea)",
     "notes": "HAND-CHECKED promotion: the grounding gate rejected this because the quote "
              "names 'Automotive Functional Safety' rather than the number ISO 26262. "
              "Verified real; scope is the Korean R&D centre, so parent_only."},
]


def apply(out_dir: Path, dry_run: bool = False) -> None:
    dec_path = out_dir / "handcheck_decisions.csv"
    if not dry_run:
        with dec_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["record_no", "company", "claim_as_extracted", "verdict", "reasoning",
                        "checked_at"])
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            for d in DECISIONS:
                w.writerow([*d, now])
        print(f"wrote {dec_path} ({len(DECISIONS)} verdicts)")

    path = out_dir / "passB_ev.csv"
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)

    existing = {(r["record_no"], r["certification"]) for r in rows}
    added = 0
    for c in CORRECTIONS:
        if (c["record_no"], c["certification"]) in existing:
            continue
        template = next((r for r in rows if r["record_no"] == c["record_no"]), None)
        row = {k: "" for k in fields}
        if template:
            for k in ("location", "queries_tried", "urls_fetched", "model", "backend"):
                row[k] = template.get(k, "")
        row.update(c)
        row["pass"] = "B-handcheck"
        row["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows.append(row)
        added += 1

    # The mislabelled UN 38.3 row must not survive as a battery standard.
    dropped = 0
    for r in rows:
        if r["record_no"] == "82" and r["certification"].startswith("UN 38.3"):
            r["certification"] = "(withdrawn by hand-check: mislabelled UN 38.3)"
            r["cert_status"] = "unclear"
            r["ev_canonical"] = ""
            r["confidence"] = "low"
            r["notes"] = ("withdrawn by hand-check: the real certification is IATA CEIV "
                          "Lithium Batteries, recorded as a separate corrected row")
            dropped += 1

    print(f"passB_ev.csv: +{added} corrected row(s), {dropped} mislabelled row(s) withdrawn")
    if not dry_run:
        shutil.copy2(path, path.with_suffix(".prehandcheck.csv"))
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    apply(a.dir, a.dry_run)


if __name__ == "__main__":
    main()
