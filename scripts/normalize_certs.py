"""Pass D — canonicalise the certification column across run 1 and the gap-fill run.

Code only, no network. Three jobs:

1. EXPLODE  Cells that pack several standards into one string ("ISO 9001, ISO 14001,
   ISO 45001, IATF 16949, AS/EN 9100, ISO/TS 22163-IRIS") become one row per standard,
   while names that merely contain a slash ("ISO/TS 16949", "AS/EN 9100", "FDA/NSF-51")
   stay whole.

2. CANONICALISE  ~72 distinct raw strings in run 1 alone collapse to canonical families:
   IATF 16949 / IATF 16949:2016 / ISO/TS 16949 / ISO/TS 16949:2009 / TS 16949 / QS-9000 are
   all the same lineage. Anything the table cannot map is reported and the script EXITS
   NON-ZERO — a silent "UNKNOWN" bucket would quietly corrupt every count downstream.

3. RESOLVE  Per (record_no, canonical_id), two independent resolutions, because displaying
   a certificate and counting its scope are different questions:

     is_winner     which row supplies the detail columns (registrar, number, dates, scope).
                   Most complete certificate identity first.
     scope_bucket  which facility-scope column the certificate counts in. The STRONGEST
                   facility evidence across ALL contributing rows.

   Collapsing the two understates the headline: a thin facility_confirmed run-1 row plus a
   complete parent_only pass-C row would let completeness pick the parent row and drop that
   certificate out of the Georgia-evidenced column — losing it precisely on the companies
   documented well enough for pass C to succeed.

Usage:
    python scripts/normalize_certs.py                  # run1 + passes A/B/C
    python scripts/normalize_certs.py --self-test      # resolution unit tests, no I/O
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
RUN1_CSV = PKG_ROOT / "outputs" / "certification_status.csv"
DEFAULT_DIR = PKG_ROOT / "outputs" / "run2_gapfill"

# Rows that record an absence rather than a certification, plus claims too vague to name a
# standard. Kept, flagged, never counted as a standard — "none identified" means unknown,
# not uncertified, and "Occupational Safety" is marketing language, not ISO 45001.
NONE_IDS = {"__none__", "__no_ev__", "__no_details__", "__vague__"}

# Fragments produced by exploding an enumeration inside ONE listing string — e.g. TCI's
# "UL 1332/DTOV2 (4000, 6000, 7000, 8000, and 9000 series)" is a single UL listing covering
# several product series, not nine standards. Dropped, and the count is reported.
IGNORE_FRAGMENTS = [
    r"^\d{3,4}$", r"^\d{3,4}\s*series$", r"^and\s+\d{3,4}\s*series$",
    r"^D[TO]{2}V\d$", r"^series$",
]

# ---------------------------------------------------------------------------- alias table
# (regex, canonical_id, family, domain, note). First match wins, so put the specific
# patterns before the general ones (ISO 45001 before ISO 4..., IATF before ISO 9001).
ALIASES: list[tuple[str, str, str, str, str]] = [
    # --- absence markers
    (r"^\s*none identified\b.*$", "__none__", "No certification identified", "None", ""),
    (r"no (?:Georgia[\s\-]facility )?EV/battery standard identified", "__no_ev__", "No EV/battery standard identified",
     "None", ""),
    (r"^\(?no certificate details found\)?$", "__no_details__", "No certificate details found",
     "None", ""),
    # Claims that name no standard. Deliberately NOT folded into ISO 45001 / 14001 / 50001:
    # promoting "Occupational Safety" to a named certification would invent one.
    (r"^(?:Occupational Safety|Energy\s*management|Emissions Compliance|Operator Certificate|"
     r"Independent environmental management certification|ISO|AIA Certified|ASTM Standards|"
     r"Quality Assurance|Environmental Compliance)$",
     "__vague__", "Unspecified certification claim", "None",
     "Named no standard; kept visible but never counted as one"),

    # --- automotive
    (r"\b(IATF\s*16949|ISO[/\s]*TS\s*16949|(?<![A-Za-z])TS\s*16949|QS[\s\-]?9000|ISO\s*16949|^IATF$)\b",
     "IATF 16949", "Automotive QMS", "Automotive",
     "ISO/TS 16949 and QS-9000 are superseded predecessors of IATF 16949"),
    (r"\bISO\s*26262\b|\bASIL\b", "ISO 26262", "Automotive functional safety", "Automotive", ""),
    (r"Automotive\s*SPICE|\bASPICE\b", "Automotive SPICE",
     "Automotive software process assessment", "Automotive", ""),
    (r"\bAEC[\s\-]?(Q\d+)?\b", "AEC-Q", "Automotive electronic component qualification",
     "Automotive", ""),
    (r"\bVDA\s*6\.?3\b", "VDA 6.3", "Automotive process audit", "Automotive", ""),
    (r"\bVDA\s*6\.?4\b", "VDA 6.4", "Automotive equipment audit", "Automotive", ""),
    (r"\bISO[/\s]*(?:SAE\s*)?21434\b", "ISO 21434", "Automotive cybersecurity", "Automotive", ""),
    (r"\bMMOG[/\s]*LE\b", "MMOG/LE", "Automotive materials management", "Automotive", ""),
    (r"\bISO[/\s]*TS\s*22163|IRIS\b", "ISO/TS 22163 (IRIS)", "Rail QMS", "Rail", ""),
    (r"Three[\s\-]?Peak|3PMSF", "3PMSF", "Tire severe-snow rating", "Automotive", ""),
    (r"SmartWay", "EPA SmartWay", "Freight efficiency programme", "Automotive", ""),
    (r"Ford\s*Q1", "Ford Q1", "Customer-specific quality rating (Ford)", "Automotive", ""),
    (r"\bNATM\b", "NATM Compliance Verification Program",
     "Trailer-manufacturer compliance verification", "Automotive", ""),

    # --- EV / battery (mirrors gapfill_run.EV_BATTERY_CANON)
    (r"\bUN\s*38[.\s]*3\b", "UN 38.3", "Lithium battery transport testing", "EV/battery", ""),
    # Found by the pass-B hand-check: the model had extracted this as "UN 38.3", which is a
    # different thing (a battery TEST standard). CEIV certifies the logistics operator, not
    # the battery, so it is battery-adjacent rather than a battery standard.
    (r"CEIV|IATA.*Lithium", "IATA CEIV Lithium Batteries",
     "Lithium battery air-logistics handling", "EV/battery",
     "Certifies handling/transport competence, NOT the battery itself"),
    (r"\bIEC\s*62660\b", "IEC 62660", "Li-ion traction cell performance/safety", "EV/battery", ""),
    (r"\bIEC\s*62619\b", "IEC 62619", "Li-ion industrial cell safety", "EV/battery", ""),
    (r"\bIEC\s*62133\b", "IEC 62133", "Portable Li-ion cell safety", "EV/battery", ""),
    (r"\bUL\s*2580\b", "UL 2580", "EV battery pack safety", "EV/battery", ""),
    (r"\bUL\s*1973\b", "UL 1973", "Stationary/auxiliary battery safety", "EV/battery", ""),
    (r"\bUL\s*2271\b", "UL 2271", "Light EV battery safety", "EV/battery", ""),
    (r"\bUL\s*1642\b", "UL 1642", "Lithium cell safety", "EV/battery", ""),
    (r"\bISO\s*6469\b", "ISO 6469", "Electric road vehicle safety", "EV/battery", ""),
    (r"\bISO\s*15118\b", "ISO 15118", "EV-to-charger communication", "EV/battery", ""),
    (r"\bSAE\s*J\s*1772\b", "SAE J1772", "EV conductive charge coupler", "EV/battery", ""),
    (r"\bIEC\s*61851\b", "IEC 61851", "EV conductive charging system", "EV/battery", ""),
    (r"\bIEC\s*62196\b", "IEC 62196", "EV charging connectors", "EV/battery", ""),
    (r"\bUL\s*2594\b", "UL 2594", "EV supply equipment (EVSE)", "EV/battery", ""),
    (r"\bUL\s*2202\b", "UL 2202", "EV charging system equipment", "EV/battery", ""),
    (r"\bISO\s*17409\b", "ISO 17409", "EV conductive connection safety", "EV/battery", ""),
    (r"\bIEC\s*61508\b", "IEC 61508", "General functional safety", "Functional safety", ""),

    # --- aerospace
    # Revision letters are part of the name in aerospace: AS9100D, AS9100C.
    (r"\b(?:AS\s*/?\s*EN|AS|EN)\s*9100[A-Za-z]?\b", "AS9100", "Aerospace QMS", "Aerospace",
     "EN 9100 is the European equivalent of AS9100"),
    (r"FAA\s*Part\s*145|Part\s*145", "FAA Part 145", "Aircraft repair station", "Aerospace", ""),
    (r"Part\s*135", "FAA Part 135", "Air carrier / commuter operations certificate",
     "Aerospace", ""),
    (r"\bAS\s*9120\b", "AS9120", "Aerospace distributor QMS", "Aerospace", ""),
    (r"\bNADCAP\b", "Nadcap", "Aerospace special-process accreditation", "Aerospace", ""),

    # --- core management systems
    # National adoptions write it as UNI EN / BS EN / DIN EN (ISO) 9001.
    (r"\bISO\s*900[12]\b|Quality Management System|\b(?:UNI|BS|DIN|EN)\s*(?:EN\s*)?9001\b",
     "ISO 9001", "Quality management system", "Core management systems",
     "ISO 9002:1994 was withdrawn and absorbed into ISO 9001:2000"),
    (r"\bISO\s*14001\b", "ISO 14001", "Environmental management system",
     "Core management systems", ""),
    (r"\bISO\s*45001\b", "ISO 45001", "Occupational health & safety MS",
     "Core management systems", ""),
    (r"\b(?:OHSAS|ISO|BS)\s*1800[0-9]\b", "OHSAS 18001",
     "Occupational health & safety MS (withdrawn)", "Core management systems",
     "OHSAS 18004 is not a standard: BS 18004:2008 is BSI guidance and OHSAS 18002 is "
     "implementation guidance. OHSAS 18001 itself was superseded by ISO 45001 (March 2021)."),
    (r"\bISO\s*50001\b", "ISO 50001", "Energy management system", "Core management systems", ""),
    (r"\bISO\s*22301\b", "ISO 22301", "Business continuity management system",
     "Core management systems", ""),
    (r"\bISO\s*55001\b", "ISO 55001", "Asset management system", "Core management systems", ""),
    (r"\bISO\s*14064\b", "ISO 14064", "Greenhouse gas quantification/verification",
     "Core management systems", ""),
    (r"\bISO\s*3834\b", "ISO 3834", "Welding quality requirements", "Core management systems", ""),
    (r"\bEN\s*1090\b", "EN 1090", "Structural steel/aluminium execution",
     "Core management systems", ""),

    # --- information security / IT
    (r"\bISO[/\s]*IEC\s*27001\b|\bISO\s*27001\b|^ISMS$", "ISO/IEC 27001", "Information security MS",
     "Information security", ""),
    (r"\bISO[/\s]*IEC\s*20000\b", "ISO/IEC 20000-1", "IT service management",
     "Information security", ""),
    (r"TISAX|VDA\s*ISA", "TISAX", "Automotive information-security assessment", "Information security", ""),
    (r"\bSOC\s*2\b", "SOC 2", "Service organisation controls", "Information security", ""),

    # --- laboratory / testing
    (r"\bISO[/\s]*(?:IEC\s*)?17025\b", "ISO/IEC 17025", "Testing & calibration lab competence",
     "Laboratory/testing", ""),
    (r"80079[\s\-]*34", "EN ISO/IEC 80079-34", "Ex-equipment quality system",
     "Laboratory/testing", ""),
    (r"\bA2LA\b", "A2LA accreditation", "Laboratory accreditation", "Laboratory/testing", ""),

    # --- medical / food / drug
    (r"\bISO\s*13485\b", "ISO 13485", "Medical device QMS", "Medical/food/drug", ""),
    (r"\bNSF[\s/\-]*(ANSI[\s/\-]*)?51\b", "NSF/ANSI 51", "Food-equipment materials",
     "Medical/food/drug", ""),
    (r"cGMP|Good Manufacturing", "cGMP", "Current good manufacturing practice",
     "Medical/food/drug", ""),
    (r"FDA.*(QSR|Quality System Regulation|21 CFR 820)|^\s*QSR\s*$", "FDA QSR (21 CFR 820)",
     "US medical-device quality system regulation", "Medical/food/drug", ""),
    (r"FDA\s*(?:Registration|Registered|Certification|Approved|Compliance)", "FDA Registration",
     "US FDA establishment registration", "Medical/food/drug", ""),
    (r"\bFSSC\s*22000\b", "FSSC 22000", "Food safety system certification",
     "Medical/food/drug", ""),
    (r"\bISO\s*22000\b", "ISO 22000", "Food safety management system", "Medical/food/drug", ""),
    (r"Halal", "Halal certification", "Halal product conformity", "Medical/food/drug", ""),
    (r"\bKosher\b", "Kosher certification", "Kosher product conformity", "Medical/food/drug", ""),

    # --- governance / compliance
    (r"\bISO\s*37001\b", "ISO 37001", "Anti-bribery management system",
     "Governance/compliance", ""),
    (r"\bISO\s*37301\b", "ISO 37301", "Compliance management system",
     "Governance/compliance", ""),
    (r"C[\s\-]?TPAT|Customs[\s\-]Trade Partnership", "C-TPAT", "Customs-Trade Partnership Against Terrorism",
     "Governance/compliance", ""),
    (r"\bAEO\b", "AEO", "Authorised Economic Operator", "Governance/compliance", ""),
    (r"\bITAR\b", "ITAR registration", "US defense-trade registration",
     "Governance/compliance", ""),
    (r"\b(MBE|WBE|DBE|WOSB|WBENC|NMSDC)\b|minority.?owned|women.?owned", "MBE/WBE/DBE",
     "Diverse-supplier registration", "Governance/compliance", ""),
    (r"OSHA\s*VPP", "OSHA VPP", "OSHA Voluntary Protection Program",
     "Governance/compliance", ""),

    # --- sustainability / social / materials
    (r"SA\s*8000", "SA8000", "Social accountability / labour", "Sustainability/materials", ""),
    (r"OEKO[\s\-]?TEX", "OEKO-TEX Standard 100", "Textile harmful-substance limits",
     "Sustainability/materials", ""),
    (r"bluesign", "bluesign", "Sustainable textile production", "Sustainability/materials", ""),
    (r"\bFSC\b|Forest Stewardship", "FSC", "Responsible forestry chain of custody",
     "Sustainability/materials", ""),
    (r"Aluminium Stewardship|\bASI\b", "ASI Chain of Custody",
     "Responsible aluminium sourcing", "Sustainability/materials", ""),
    (r"QUALICOAT", "QUALICOAT", "Aluminium coating quality label", "Sustainability/materials", ""),
    (r"\bEN\s*15088\b", "EN 15088", "Structural aluminium products",
     "Sustainability/materials", ""),
    (r"Multi[\s\-]?Attribute|GreenCircle", "GreenCircle Multi-Attribute Label",
     "Multi-criteria product sustainability label", "Sustainability/materials",
     "GreenCircle Certified LLC programme built for Federal EO 13514 procurement; bundles "
     "LCA, EPD, water, waste and carbon data. A product label, not a management system."),
    (r"Ontario Regulation 455|\bTRA\b|Toxics Reduction", "Ontario TRA (O. Reg. 455/09)",
     "Ontario toxics-reduction compliance", "Sustainability/materials", ""),
    (r"\bLEED\b", "LEED", "Green building certification", "Sustainability/materials", ""),
    (r"ISCC\s*PLUS|\bISCC\b", "ISCC PLUS", "Circular/bio-based feedstock chain of custody",
     "Sustainability/materials", ""),
    (r"\bEMAS\b", "EMAS", "EU Eco-Management and Audit Scheme",
     "Sustainability/materials", ""),
    (r"EcoVadis", "EcoVadis", "Supplier sustainability rating (not a certification)",
     "Sustainability/materials", ""),
    (r"Copper Mark", "Copper Mark", "Responsible copper production assurance",
     "Sustainability/materials", ""),
    (r"Superior Energy Performance|\bSEP\b", "Superior Energy Performance",
     "US DOE energy-performance certification", "Sustainability/materials", ""),
    (r"\bEPD\b|Environmental Product Declaration", "EPD",
     "Environmental product declaration", "Sustainability/materials", ""),
    (r"Responsible Care", "Responsible Care", "Chemical industry HSE programme",
     "Sustainability/materials", ""),

    # --- product safety / regulatory (last: these patterns are broad)
    (r"\bRoHS", "RoHS", "Restriction of hazardous substances", "Product/regulatory", ""),
    (r"\bREACH\b", "REACH", "EU chemical registration/authorisation", "Product/regulatory", ""),
    (r"\bCARB\b", "CARB", "California Air Resources Board compliance", "Product/regulatory", ""),
    (r"\bCE\s*(marking|mark)\b", "CE marking", "EU product conformity", "Product/regulatory", ""),
    (r"NSF[\s/\-]*(?:ANSI[\s/\-]*)?61\b", "NSF/ANSI 61",
     "Drinking-water system components, health effects", "Product/regulatory", ""),
    (r"NSF[\s/\-]*(?:ANSI[\s/\-]*)?372\b", "NSF/ANSI 372",
     "Drinking-water lead-content conformity", "Product/regulatory", ""),
    (r"\bCSA\s*C22\.2\b|\bCSA\b", "CSA C22.2", "Canadian electrical product safety",
     "Product/regulatory", ""),
    (r"\bDOT\b|FMVSS", "DOT/FMVSS", "US vehicle safety regulation", "Product/regulatory", ""),
    (r"\bUL\b", "UL listing", "Product safety listing", "Product/regulatory", ""),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), cid, fam, dom, note)
             for p, cid, fam, dom, note in ALIASES]

# ---------------------------------------------------------------------------- explode

_PAREN_SAME = re.compile(r"\((?:formerly|previously|now|prev\.?|ex)\b[^)]*\)", re.IGNORECASE)


def explode(raw: str) -> list[str]:
    """Split a certification cell into individual standard strings.

    A slash only separates when it has a space beside it, or sits between a digit and a
    letter — so 'IATF 16949 / ISO 9001' and 'ISO 9001/IATF 16949' split, while 'ISO/TS
    16949', 'AS/EN 9100', 'FDA/NSF-51' and '455/09' survive intact."""
    s = str(raw or "").strip()
    if not s:
        return []
    s = _PAREN_SAME.sub(" ", s)              # '(formerly ISO/TS 16949)' adds nothing new
    # Any parenthetical that survived names a *second* standard: 'ISO 9001:1994 (with
    # QS9000:1995)' is two. Where it names the same one under another label — 'AS9100D
    # (EN 9100:2018)' — both tokens canonicalise alike and the per-row dedupe collapses them.
    inner = re.findall(r"\(([^)]*)\)", s)
    parts = [re.sub(r"\([^)]*\)", " ", s)] + inner
    for pat in (r"\s*[,;]\s*", r"\s+&\s+", r"\s+and\s+",
                r"(?<=[0-9])\s*/\s*(?=[A-Za-z])", r"\s+/\s+"):
        nxt = []
        for p in parts:
            nxt.extend(re.split(pat, p))
        parts = nxt
    out = []
    for p in parts:
        p = p.strip(" ()-").strip()
        if p:
            out.append(p)
    return out or [s]


def canonicalise(token: str) -> tuple[str, str, str, str] | None:
    """Map one standard string to its canonical id, or None.

    Tries the token as written, then with every space and hyphen removed. Different models
    write the same standard as "IATF 16949", "IATF-16949" and even "IA T F 169 49:2016";
    squeezing collapses all of those onto the same pattern, and the alias regexes already
    use `\\s*` between the acronym and the number so they match either form. Tokens reach
    here already split by explode(), so squeezing cannot fuse two standards into one."""
    for rx, cid, fam, dom, note in _COMPILED:
        if rx.search(token):
            return cid, fam, dom, note
    squeezed = re.sub(r"[\s\-]+", "", token)
    if squeezed and squeezed != token:
        for rx, cid, fam, dom, note in _COMPILED:
            if rx.search(squeezed):
                return cid, fam, dom, note
    return None


# ---------------------------------------------------------------------------- resolution

CERT_RANK = ["confirmed_active", "active_expiry_unknown", "confirmed_expired",
             "company_claim_only", "parent_only", "affiliate_only", "historical_only",
             "conflicting", "unclear", "not_found_after_search", "search_failed",
             "source_unavailable"]
# Strongest evidence that the GEORGIA site is covered, best first.
FACILITY_RANK = ["facility_confirmed", "parent_only", "affiliate_only", "unclear",
                 "facility_not_confirmed", "not_applicable"]
GA_EVIDENCED = "facility_confirmed"


def _completeness(row: dict) -> int:
    """3 = registrar + number + expiry, 2 = registrar + number, 1 = any one, 0 = none."""
    body = bool(row.get("certification_body", "").strip())
    ref = bool(row.get("reference_no", "").strip())
    exp = bool(row.get("expiry_date", "").strip())
    if body and ref and exp:
        return 3
    if body and ref:
        return 2
    return 1 if (body or ref or exp) else 0


def _rank(seq: list[str], value: str) -> int:
    try:
        return seq.index(value)
    except ValueError:
        return len(seq)


def pick_winner(rows: list[dict]) -> dict:
    """The row that supplies the DETAIL columns. Completeness first — this is about which
    certificate record to show, not about who is covered by it."""
    return max(rows, key=lambda r: (
        _completeness(r),
        -_rank(CERT_RANK, r.get("cert_status", "")),
        -_rank(FACILITY_RANK, r.get("facility_status", "")),
        r.get("checked_at", ""),
    ))


def scope_bucket(rows: list[dict]) -> tuple[str, str]:
    """The strongest facility evidence across ALL contributing rows, and the run it came
    from. Computed independently of pick_winner: if any row ties the certificate to the
    Georgia site, the certificate is Georgia-evidenced regardless of which row happens to
    carry the registrar and certificate number."""
    best = min(rows, key=lambda r: (_rank(FACILITY_RANK, r.get("facility_status", "")),
                                    -_completeness(r)))
    return best.get("facility_status", "unclear"), best.get("source_run", "")


# ---------------------------------------------------------------------------- pipeline

OUT_COLS = ["record_no", "company", "location", "canonical_id", "family", "domain",
            "raw_certification",
            "source_run", "cert_status", "facility_status", "certification_body",
            "reference_no", "issue_date", "expiry_date", "scope", "source_type", "source_url",
            "evidence_quote", "confidence", "notes", "checked_at", "ev_canonical",
            "is_winner", "scope_bucket", "scope_bucket_source_run", "canonical_note"]


def _read(path: Path, source_run: str) -> list[dict]:
    if not path.exists():
        print(f"  (skip {path.name}: not present)")
        return []
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["source_run"] = source_run
    print(f"  {path.name}: {len(rows)} rows")
    return rows


def build(rows: list[dict]) -> tuple[list[dict], list[str], int]:
    """Explode + canonicalise every row.

    Returns (exploded rows, unmapped raw tokens, dropped enumeration fragments)."""
    out, unmapped, dropped = [], [], 0
    for r in rows:
        raw = r.get("certification", "")
        seen_in_row = set()
        for token in explode(raw):
            if any(re.fullmatch(p, token, re.IGNORECASE) for p in IGNORE_FRAGMENTS):
                dropped += 1
                continue
            hit = canonicalise(token)
            if not hit:
                unmapped.append(token)
                continue
            cid, fam, dom, note = hit
            if cid in seen_in_row:           # same standard written twice in one cell
                continue
            seen_in_row.add(cid)
            out.append({**r, "canonical_id": cid, "family": fam, "domain": dom,
                        "raw_certification": raw, "canonical_note": note})
    return out, unmapped, dropped


def resolve(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(str(r["record_no"]), r["canonical_id"])].append(r)
    out = []
    for (_rec, cid), grp in groups.items():
        if cid in NONE_IDS:
            for r in grp:
                r.update(is_winner="0", scope_bucket="not_applicable",
                         scope_bucket_source_run="")
            out.extend(grp)
            continue
        win = pick_winner(grp)
        bucket, bucket_run = scope_bucket(grp)
        for r in grp:
            r.update(is_winner="1" if r is win else "0",
                     scope_bucket=bucket, scope_bucket_source_run=bucket_run)
        out.extend(grp)
    return out


def counts(rows: list[dict]) -> list[dict]:
    """One row per canonical standard, companies counted once, split by facility scope."""
    winners = [r for r in rows if r["is_winner"] == "1"]
    by_cid: dict[str, dict] = {}
    for r in winners:
        c = by_cid.setdefault(r["canonical_id"], {
            "canonical_id": r["canonical_id"], "family": r["family"], "domain": r["domain"],
            "ga_evidenced": set(), "group_only": set(), "affiliate_only": set(), "all": set()})
        rec = str(r["record_no"])
        c["all"].add(rec)
        if r["scope_bucket"] == GA_EVIDENCED:
            c["ga_evidenced"].add(rec)
        else:
            c["group_only"].add(rec)
            if r["scope_bucket"] == "affiliate_only":
                c["affiliate_only"].add(rec)
    out = []
    for c in by_cid.values():
        out.append({"canonical_id": c["canonical_id"], "family": c["family"],
                    "domain": c["domain"],
                    "companies_ga_evidenced": len(c["ga_evidenced"]),
                    "companies_group_only": len(c["group_only"]),
                    "of_which_affiliate_only": len(c["affiliate_only"]),
                    "companies_total": len(c["all"])})
    out.sort(key=lambda r: (-r["companies_total"], r["canonical_id"]))
    return out


def _write(path: Path, rows: list[dict], cols: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path} ({len(rows)} rows)")


# ---------------------------------------------------------------------------- self-test

def self_test() -> int:
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)
        print(f"  {'ok  ' if cond else 'FAIL'} {name}")

    print("explode:")
    check("6-standard cell splits to 6",
          len(explode("ISO 9001, ISO 14001, ISO 45001, IATF 16949, AS/EN 9100, "
                      "ISO/TS 22163-IRIS")) == 6)
    check("'IATF 16949 (formerly ISO/TS 16949)' stays one",
          explode("IATF 16949 (formerly ISO/TS 16949)") == ["IATF 16949"])
    check("'ISO/TS 16949' not split by its slash", explode("ISO/TS 16949") == ["ISO/TS 16949"])
    check("'TS 16949 / ISO 14001' splits", len(explode("TS 16949 / ISO 14001")) == 2)
    check("'ISO 9001:1994 (with QS9000:1995)' splits",
          len(explode("ISO 9001:1994 (with QS9000:1995)")) == 2)
    check("'FDA/NSF-51' stays one", explode("FDA/NSF-51") == ["FDA/NSF-51"])
    check("5-standard textile cell splits to 5",
          len(explode("ISO 9001, ISO 14001, ISO 45001, OEKO-TEX STANDARD 100, "
                      "bluesign system")) == 5)

    print("canonicalise:")
    for raw, want in (("IATF 16949:2016", "IATF 16949"), ("ISO/TS 16949:2009", "IATF 16949"),
                      ("TS 16949", "IATF 16949"), ("QS-9000", "IATF 16949"),
                      ("BS EN ISO 9001:2000", "ISO 9001"), ("DIN EN ISO 14001:2015", "ISO 14001"),
                      ("OHSAS 18004", "OHSAS 18001"), ("AS9100D (EN 9100:2018)", "AS9100"),
                      ("Multi-Attribute Label Certification", "GreenCircle Multi-Attribute Label"),
                      ("UN 38.3", "UN 38.3"), ("none identified", "__none__")):
        got = canonicalise(explode(raw)[0])
        check(f"{raw!r} -> {want}", got and got[0] == want)

    print("winner vs scope_bucket (the record-50 case):")
    base = {"record_no": "50", "canonical_id": "IATF 16949", "family": "Automotive QMS",
            "domain": "Automotive"}
    thin_ga = {**base, "certification_body": "", "reference_no": "", "expiry_date": "",
               "cert_status": "company_claim_only", "facility_status": "facility_confirmed",
               "checked_at": "2026-07-22", "source_run": "run1"}
    full_parent = {**base, "certification_body": "DQS", "reference_no": "123456",
                   "expiry_date": "2027-01-01", "cert_status": "confirmed_active",
                   "facility_status": "parent_only", "checked_at": "2026-08-10",
                   "source_run": "C"}
    grp = [thin_ga, full_parent]
    check("detail winner is the complete parent_only row", pick_winner(grp) is full_parent)
    bucket, run = scope_bucket(grp)
    check(f"scope_bucket is facility_confirmed (got {bucket!r} from {run!r})",
          bucket == GA_EVIDENCED and run == "run1")

    resolved = resolve([dict(thin_ga), dict(full_parent)])
    winners = [r for r in resolved if r["is_winner"] == "1"]
    check("exactly one winner per (record_no, canonical_id)", len(winners) == 1)
    check("every row in the group carries the same scope_bucket",
          len({r["scope_bucket"] for r in resolved}) == 1)
    check("counts put record 50 in the Georgia-evidenced column",
          counts(resolved)[0]["companies_ga_evidenced"] == 1)

    print(f"\n{'ALL PASSED' if not fails else str(len(fails)) + ' FAILURES: ' + ', '.join(fails)}")
    return 1 if fails else 0


# ---------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--run1", type=Path, default=RUN1_CSV)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        raise SystemExit(self_test())

    print("reading:")
    rows = _read(args.run1, "run1")
    for name, tag in (("passA_blanks.csv", "A"), ("passB_ev.csv", "B"),
                      ("passC_details.csv", "C"), ("passE_ev.csv", "E")):
        rows += _read(args.dir / name, tag)

    exploded, unmapped, dropped = build(rows)
    if unmapped:
        uniq = sorted(set(unmapped))
        print(f"\n{len(uniq)} UNMAPPED certification string(s) — add them to ALIASES and re-run:")
        for u in uniq:
            print(f"   {u!r}")
        raise SystemExit(1)

    if dropped:
        print(f"  dropped {dropped} enumeration fragment(s) from multi-series listing strings")
    resolved = resolve(exploded)
    _write(args.dir / "certifications_normalized.csv", resolved, OUT_COLS)
    _write(args.dir / "cert_family_counts.csv", counts(resolved),
           ["canonical_id", "family", "domain", "companies_ga_evidenced",
            "companies_group_only", "of_which_affiliate_only", "companies_total"])

    winners = [r for r in resolved if r["is_winner"] == "1"]
    real = [r for r in winners if r["canonical_id"] not in NONE_IDS]
    print(f"\n{len(rows)} input rows -> {len(exploded)} exploded -> "
          f"{len(real)} distinct (company, standard) pairs")
    print(f"distinct canonical standards: {len({r['canonical_id'] for r in real})}")
    ga = {r['record_no'] for r in real if r['scope_bucket'] == GA_EVIDENCED}
    print(f"companies with >=1 Georgia-evidenced certificate: {len(ga)}")


if __name__ == "__main__":
    main()
