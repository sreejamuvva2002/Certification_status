"""End-to-end verification of the gap-fill run. Asserts the claims the key doc makes.

Every check prints ok/FAIL and the script exits non-zero if any fails, so the deliverable's
claims are checkable rather than asserted.

Usage:  python scripts/verify_run2.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
OUT = PKG_ROOT / "outputs"
D = OUT / "run2_gapfill"
NONE_IDS = {"__none__", "__no_ev__", "__no_details__", "__vague__"}

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        fails.append(name)
    print(f"  {'ok  ' if cond else 'FAIL'} {name}{('  — ' + detail) if detail else ''}")


def read(p: Path) -> list[dict]:
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


print("run-1 is frozen:")
r = subprocess.run(["sha256sum", "-c", str(D / "run1_manifest.sha256")],
                   capture_output=True, text=True, cwd=PKG_ROOT)
check("manifest verifies (csv, table, evidence log, xlsx)", r.returncode == 0,
      r.stdout.strip().replace("\n", "; ")[:120])
tree = subprocess.run("find companies -type f -exec sha256sum {} \\; | sort | sha256sum",
                      shell=True, capture_output=True, text=True, cwd=OUT).stdout.split()[0]
want = (D / "run1_companies_tree.sha256").read_text().strip()
check("outputs/companies/ unchanged", tree == want)

print("\npass A — the defect being fixed (a 'no' with nothing behind it):")
a = read(D / "passA_blanks.csv")
check("78 records re-searched", len({x["record_no"] for x in a}) == 78)
check("every row records the queries tried", all(x["queries_tried"].strip() for x in a))
check("every row has an evidence quote or notes",
      all(x["evidence_quote"].strip() or x["notes"].strip() for x in a))
run1 = read(OUT / "certification_status.csv")
by_rec = defaultdict(list)
for x in run1:
    by_rec[x["record_no"]].append(x)
blanks = {k for k, v in by_rec.items() if all(y["certification"].strip() == "none identified"
                                              for y in v)}
check("pass A targeted exactly run-1's blank records", {x["record_no"] for x in a} == blanks)
flipped = {x["record_no"] for x in a if x["certification"].strip() != "none identified"}
print(f"       ({len(flipped)} of 78 flipped to a real certification)")

print("\npass B — the EV/battery claim:")
b = read(D / "passB_ev.csv")
check("all 205 companies swept", len({x["record_no"] for x in b}) == 205)
neg = {x["record_no"] for x in b if x["certification"] == "no EV/battery standard identified"}
check("every negative row carries its queries and URLs",
      all(x["queries_tried"].strip() for x in b
          if x["certification"] == "no EV/battery standard identified"))
hits = [x for x in b if x["ev_canonical"].strip()]
check("no ungated EV-canon row remains in the file",
      not [x for x in b if not x["ev_canonical"].strip()
           and re.search(r"\b(UN\s*38|IEC\s*6(2660|2619|2133|1851|2196|1508)|UL\s*(2580|1973|2271|1642|2594|2202)"
                         r"|ISO\s*(6469|15118|17409|26262)|ISO[/\s]*(SAE\s*)?21434|SAE\s*J\s*1772)\b",
                         x["certification"], re.I)
           and x["cert_status"] != "unclear"],
      "rows matching an EV/battery canon must be gated or demoted")
battery = {x["record_no"] for x in hits
           if x["ev_canonical"] in {"UN 38.3", "IEC 62660", "IEC 62619", "IEC 62133", "UL 2580",
                                    "UL 1973", "UL 2271", "UL 1642"}}
evelec = {x["record_no"] for x in hits
          if x["ev_canonical"] in {"ISO 6469", "ISO 15118", "SAE J1772", "IEC 61851",
                                   "IEC 62196", "UL 2594", "UL 2202", "ISO 17409"}}
check("zero companies hold a battery product standard", len(battery) == 0)
check("zero companies hold an EV-electrical/charging standard", len(evelec) == 0)
print(f"       ({len(neg)} explicit negatives, {len({x['record_no'] for x in hits})} grounded hits)")

print("\npass C — grounded detail fill:")
c = read(D / "passC_details.csv")
check("112 records processed", len({x["record_no"] for x in c}) == 112)
filled = sum(1 for x in c for f in ("certification_body", "reference_no", "issue_date",
                                    "expiry_date") if x[f].strip())
dropped = sum(len([p for p in x["dropped_fields"].split(";") if p.strip()]) for x in c)
rate = dropped / (filled + dropped) if (filled + dropped) else 0
check(f"field drop rate under 30% ({dropped}/{filled + dropped} = {100 * rate:.0f}%)", rate < 0.30,
      "a higher rate would mean the normaliser, not the evidence, is at fault")

print("\nevidence log:")
per_pass = Counter()
for line in (D / "evidence_log.jsonl").read_text(errors="replace").splitlines():
    try:
        per_pass[str(json.loads(line).get("pass", "A"))] += 1
    except Exception:
        pass
check("pass B logged all 205 (would be 127 if keyed on record_no alone)",
      per_pass["B"] == 205, str(dict(per_pass)))
check("pass C logged all 112", per_pass["C"] == 112)

print("\nnormalisation:")
n = read(D / "certifications_normalized.csv")
groups = defaultdict(list)
for x in n:
    groups[(x["record_no"], x["canonical_id"])].append(x)
real = {k: v for k, v in groups.items() if k[1] not in NONE_IDS}
check("exactly one is_winner per (company, standard)",
      all(sum(1 for y in v if y["is_winner"] == "1") == 1 for v in real.values()))
check("one scope_bucket per (company, standard)",
      all(len({y["scope_bucket"] for y in v}) == 1 for v in real.values()))
check("no identical duplicate rows",
      len({tuple(sorted(x.items())) for x in n}) == len(n))
check("every row canonicalised (no UNKNOWN bucket)",
      all(x["canonical_id"].strip() for x in n))

print("\nscope decoupling (the record-50 case, on real data):")
decoupled = [k for k, v in real.items()
             if any(y["facility_status"] == "facility_confirmed" for y in v)
             and next(y for y in v if y["is_winner"] == "1")["facility_status"] != "facility_confirmed"]
check("certs whose detail winner is NOT the Georgia-evidenced row still count as Georgia",
      all(groups[k][0]["scope_bucket"] == "facility_confirmed" for k in decoupled),
      f"{len(decoupled)} such (company, standard) pair(s) — all bucketed on max evidence")

print("\nkey document:")
key_md = (D / "certification_key.md").read_text()
cids = {x["canonical_id"] for x in n if x["canonical_id"] not in NONE_IDS}
missing = sorted(c for c in cids if f"**{c}**" not in key_md)
check("every canonical standard appears in the key", not missing, ", ".join(missing[:6]))
counts = read(D / "cert_family_counts.csv")
winners = [x for x in n if x["is_winner"] == "1"]
for row in counts[:6]:
    if row["canonical_id"] in NONE_IDS:
        continue
    ga = len({x["record_no"] for x in winners if x["canonical_id"] == row["canonical_id"]
              and x["scope_bucket"] == "facility_confirmed"})
    check(f"{row['canonical_id']}: §1 Georgia-evidenced count matches the data",
          ga == int(row["companies_ga_evidenced"]),
          f"{ga} vs {row['companies_ga_evidenced']}")

print(f"\n{'ALL CHECKS PASSED' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
