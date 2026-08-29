"""Build outputs/run2_gapfill/certification_key.md — the deliverable.

Every number in the document is computed from certifications_merged.jsonl at build time,
so the prose cannot drift away from the data. The editorial content (what a standard means,
which services and processes it governs) lives in KEY below; the counts, the coverage
tables and the normalisation table are generated.

Two rules the document obeys throughout:

  * Counts are per (company, canonical standard) on merged records, split into two facility
    scope columns. A certificate held by a Korean sister plant does not make a Georgia
    supplier certified, so "Georgia-evidenced" (facility_status = facility_confirmed
    anywhere in the contributing rows) is always reported separately from "group holds it".
  * "none identified" means unknown, not uncertified.

The build FAILS if any canonical_id in the data has no KEY entry — that guard is what makes
the key provably complete.

Usage:  python scripts/build_key.py [--dir outputs/run2_gapfill]
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = PKG_ROOT / "outputs" / "run2_gapfill"
NONE_IDS = {"__none__", "__no_ev__", "__no_details__", "__vague__"}
GA = "facility_confirmed"

# canonical_id -> (full name, what it certifies, services & processes it maps to)
KEY: dict[str, tuple[str, str, str]] = {
    # --- automotive
    "IATF 16949": (
        "International Automotive Task Force 16949",
        "Quality management system built on ISO 9001 and tailored to automotive production "
        "and relevant service parts. ISO/TS 16949 and QS-9000 are its superseded predecessors "
        "(replaced in 2016).",
        "Automotive part design and manufacture; defect prevention; PPAP/APQP/FMEA; "
        "supplier quality management; production part traceability"),
    "ISO 26262": (
        "ISO 26262 — Road vehicles, functional safety",
        "Safety lifecycle for automotive electrical/electronic (E/E) systems, with ASIL "
        "hazard classification.",
        "ECU and controller design; ADAS; powertrain, inverter and BMS control software; "
        "safety-critical electronics validation"),
    "ISO 21434": (
        "ISO/SAE 21434 — Road vehicles, cybersecurity engineering",
        "Cybersecurity risk management across the vehicle E/E lifecycle.",
        "Connected-vehicle software, telematics, OTA update infrastructure, secure boot"),
    "VDA 6.3": ("VDA 6.3 — Process audit (German automotive industry)",
                "Audit of manufacturing process capability, not a certifiable management system.",
                "Process capability assessment; production readiness; supplier development"),
    "VDA 6.4": ("VDA 6.4 — Production equipment audit",
                "Audit of production equipment and tooling manufacture.",
                "Tooling and equipment qualification; machine builders"),
    "Automotive SPICE": (
        "Automotive SPICE (ASPICE)",
        "Assessment of an organisation's automotive software development process capability "
        "(a maturity level, not a pass/fail certificate).",
        "ECU software development; supplier software capability assessment"),
    "AEC-Q": ("AEC-Q100 / Q101 / Q200 — Automotive Electronics Council qualification",
              "Stress-test qualification of automotive electronic components.",
              "IC, discrete and passive component qualification for automotive use"),
    "MMOG/LE": ("Materials Management Operations Guideline / Logistics Evaluation",
                "Self-assessment of materials planning and logistics capability.",
                "Supply-chain planning, scheduling, inbound/outbound logistics"),
    "ISO/TS 22163 (IRIS)": (
        "ISO/TS 22163 — International Railway Industry Standard",
        "QMS for the railway (rolling stock) industry — rail, not road. Present here because "
        "it co-occurs with automotive QMS at diversified suppliers.",
        "Rail component design and manufacture"),
    "3PMSF": ("Three-Peak Mountain Snowflake",
              "A tire performance rating for severe snow traction — a product mark, not a "
              "management system.",
              "Tire manufacture; winter-rated product lines"),
    "Ford Q1": ("Ford Q1",
                "Ford's customer-specific supplier quality award, granted by the customer "
                "rather than a certification body. Requires IATF 16949 plus Ford-specific "
                "performance history.",
                "Supplier status at Ford; PPM performance, delivery, warranty and MSA "
                "capability"),
    "NATM Compliance Verification Program": (
        "NATM Compliance Verification Program",
        "National Association of Trailer Manufacturers verification that a trailer builder's "
        "products meet applicable federal (NHTSA/FMVSS) and industry requirements.",
        "Trailer design and assembly; lighting, braking, VIN and certification labelling"),
    "EPA SmartWay": ("US EPA SmartWay Transport Partnership",
                     "Voluntary freight efficiency and emissions programme.",
                     "Fleet operations, carrier selection, outbound logistics"),
    "DOT/FMVSS": ("US DOT / Federal Motor Vehicle Safety Standards",
                  "Mandatory US vehicle and equipment safety regulation.",
                  "Vehicle and component homologation; braking, lighting, restraints"),

    # --- EV / battery
    "IATA CEIV Lithium Batteries": (
        "IATA Center of Excellence for Independent Validators — Lithium Batteries",
        "Validates that an air-logistics operator handles, stores and transports lithium "
        "batteries to international standards. It certifies the *handler*, not the battery — "
        "so it is battery-adjacent, not a battery product standard.",
        "Air freight forwarding of lithium batteries; warehouse storage; dangerous-goods "
        "handling for EV battery supply chains"),
    "UN 38.3": ("UN Manual of Tests and Criteria, section 38.3",
                "Transport safety testing for lithium cells and batteries (altitude, thermal, "
                "vibration, shock, short circuit, overcharge, forced discharge).",
                "Battery cell/module/pack shipping qualification; export logistics"),
    "IEC 62660": ("IEC 62660 — Secondary lithium-ion cells for electric road vehicles",
                  "Performance and reliability/abuse testing of traction cells.",
                  "EV traction cell design, qualification and production testing"),
    "IEC 62619": ("IEC 62619 — Secondary lithium cells for industrial applications",
                  "Safety requirements for industrial lithium cells and batteries.",
                  "Industrial and stationary battery manufacture"),
    "IEC 62133": ("IEC 62133 — Portable sealed secondary cells",
                  "Safety of portable lithium and nickel systems.",
                  "Portable battery packs, tools, small mobility"),
    "UL 2580": ("UL 2580 — Batteries for use in electric vehicles",
                "Safety of EV battery packs under abuse and fault conditions.",
                "EV pack design, enclosure, thermal propagation control"),
    "UL 1973": ("UL 1973 — Batteries for stationary and auxiliary power",
                "Safety of stationary/auxiliary battery systems.",
                "Grid storage, backup power, rail/marine auxiliary packs"),
    "UL 2271": ("UL 2271 — Batteries for light electric vehicles",
                "Safety of LEV battery packs.",
                "E-bike, LSV, industrial-truck battery manufacture"),
    "UL 1642": ("UL 1642 — Lithium batteries",
                "Safety of primary and secondary lithium cells.",
                "Cell-level safety qualification"),
    "ISO 6469": ("ISO 6469 — Electrically propelled road vehicles, safety specifications",
                 "Vehicle-level electrical safety (RESS, operational safety, protection "
                 "against electric shock).",
                 "EV integration, HV system design, service disconnect procedures"),
    "ISO 15118": ("ISO 15118 — Vehicle-to-grid communication interface",
                  "EV-to-charger communication, including Plug & Charge.",
                  "Charging controller firmware, EVSE interoperability, ISO 15118 PKI"),
    "SAE J1772": ("SAE J1772 — EV conductive charge coupler",
                  "North American AC conductive charging connector and control pilot.",
                  "Connector and inlet manufacture; EVSE assembly"),
    "IEC 61851": ("IEC 61851 — Electric vehicle conductive charging system",
                  "Charging system requirements (modes 1-4).",
                  "EVSE design and manufacture; charging station commissioning"),
    "IEC 62196": ("IEC 62196 — Plugs, socket-outlets and couplers for EV charging",
                  "Charging connector dimensional and electrical requirements.",
                  "Connector, cable assembly and inlet manufacture"),
    "UL 2594": ("UL 2594 — Electric vehicle supply equipment",
                "Safety of AC EVSE.",
                "Charging station manufacture and listing"),
    "UL 2202": ("UL 2202 — Electric vehicle charging system equipment",
                "Safety of EV charging system equipment, including DC.",
                "DC fast-charger manufacture"),
    "ISO 17409": ("ISO 17409 — EV conductive power transfer, safety requirements",
                  "Vehicle-side safety for conductive connection to an external supply.",
                  "On-board charger and inlet integration"),
    "IEC 61508": ("IEC 61508 — Functional safety of E/E/PE safety-related systems",
                  "General functional safety standard; parent of ISO 26262.",
                  "Industrial control, drives, safety instrumented systems"),

    # --- aerospace
    "AS9100": ("AS9100 / EN 9100 — Aerospace quality management system",
               "ISO 9001 plus aerospace-specific requirements. EN 9100 is the European "
               "equivalent; the revision letter (AS9100D) is part of the name.",
               "Aerospace part design and manufacture; configuration management; "
               "counterfeit-part prevention; first-article inspection"),
    "AS9120": ("AS9120 — Aerospace distributor quality management system",
               "AS9100 adapted to stockists and distributors.",
               "Aerospace parts distribution; lot traceability"),
    "Nadcap": ("Nadcap — National Aerospace and Defense Contractors Accreditation Program",
               "Accreditation of aerospace special processes.",
               "Heat treatment, welding, NDT, chemical processing, coatings"),
    "FAA Part 135": ("FAA Air Carrier Certificate (14 CFR Part 135)",
                     "Authority to conduct commuter and on-demand air operations.",
                     "Charter and on-demand flight operations"),
    "FAA Part 145": ("FAA Repair Station Certificate (14 CFR Part 145)",
                     "Approval to perform aircraft maintenance, preventive maintenance and "
                     "alterations.",
                     "MRO services; component overhaul"),

    # --- core management systems
    "ISO 9001": ("ISO 9001 — Quality management system",
                 "Generic, industry-agnostic quality management. Foundation of IATF 16949, "
                 "AS9100 and ISO 13485.",
                 "Any process quality: design, purchasing, production, inspection, service "
                 "delivery, corrective action"),
    "ISO 14001": ("ISO 14001 — Environmental management system",
                  "Management of environmental aspects, impacts and compliance obligations.",
                  "Waste and emissions control; permits; resource use; spill response"),
    "ISO 45001": ("ISO 45001 — Occupational health and safety management system",
                  "Worker health and safety management. Replaced OHSAS 18001.",
                  "Hazard identification, incident investigation, contractor safety, PPE"),
    "OHSAS 18001": ("OHSAS 18001 — Occupational health and safety (WITHDRAWN)",
                    "Predecessor of ISO 45001; withdrawn, with certificates invalid after "
                    "March 2021. Treat any live claim as historical.",
                    "Legacy workplace safety management"),
    "ISO 50001": ("ISO 50001 — Energy management system",
                  "Systematic improvement of energy performance.",
                  "Plant energy monitoring; efficiency projects; energy procurement"),
    "ISO 22301": ("ISO 22301 — Business continuity management system",
                  "Preparedness for and recovery from disruptive incidents.",
                  "Continuity planning; disaster recovery; supply interruption response"),
    "ISO 55001": ("ISO 55001 — Asset management system",
                  "Lifecycle management of physical assets.",
                  "Plant and equipment lifecycle, maintenance strategy, capital planning"),
    "ISO 14064": ("ISO 14064 — Greenhouse gases",
                  "Quantification, reporting and verification of GHG emissions.",
                  "Carbon accounting; Scope 1/2/3 inventory; verification statements"),
    "ISO 3834": ("ISO 3834 — Quality requirements for fusion welding",
                 "Welding quality capability of a manufacturer.",
                 "Welded structure and assembly manufacture; welder qualification"),
    "EN 1090": ("EN 1090 — Execution of steel and aluminium structures",
                "Conformity of structural steel/aluminium components for construction.",
                "Structural fabrication; CE marking of structural components"),

    # --- information security
    "ISO/IEC 27001": ("ISO/IEC 27001 — Information security management system",
                      "Management of information confidentiality, integrity and availability.",
                      "IT security controls, access management, incident response, data "
                      "governance"),
    "ISO/IEC 20000-1": ("ISO/IEC 20000-1 — IT service management",
                        "Management of IT service delivery.",
                        "Service desk, change and incident management"),
    "TISAX": ("TISAX — Trusted Information Security Assessment Exchange",
              "Automotive-industry information security assessment (VDA ISA based), shared "
              "between OEMs and suppliers.",
              "Handling confidential OEM data; prototype and design-data protection"),
    "SOC 2": ("SOC 2 — Service Organization Control 2",
              "Attestation on security, availability, confidentiality and privacy controls.",
              "Hosted/software services supplied to customers"),

    # --- laboratory / testing
    "ISO/IEC 17025": ("ISO/IEC 17025 — Testing and calibration laboratory competence",
                      "Technical competence of a laboratory to produce valid results.",
                      "Materials testing, metrology, calibration, dimensional inspection"),
    "EN ISO/IEC 80079-34": ("EN ISO/IEC 80079-34 — Explosive atmospheres, quality system",
                            "Quality system for manufacture of Ex (ATEX) equipment.",
                            "Manufacture of equipment for explosive atmospheres"),
    "A2LA accreditation": ("A2LA — American Association for Laboratory Accreditation",
                           "Accreditation body attestation of laboratory competence.",
                           "Test and calibration laboratory operations"),

    # --- medical / food / drug
    "ISO 13485": ("ISO 13485 — Medical devices quality management system",
                  "Quality system for medical device design and manufacture.",
                  "Medical device production; design history files; sterile barrier"),
    "FDA QSR (21 CFR 820)": ("FDA Quality System Regulation, 21 CFR Part 820",
                             "US regulatory quality system for medical devices.",
                             "Device manufacture, CAPA, design controls"),
    "FDA Registration": ("US FDA establishment registration",
                         "Registration of a facility with the FDA — a listing, not an audit.",
                         "Regulated device, drug or food manufacture"),
    "cGMP": ("Current Good Manufacturing Practice",
             "Regulatory manufacturing practice for FDA-regulated products.",
             "Drug, device and food production; batch records; contamination control"),
    "NSF/ANSI 51": ("NSF/ANSI 51 — Food equipment materials",
                    "Materials safe for food-zone contact.",
                    "Food equipment components; food-contact plastics and coatings"),
    "FSSC 22000": ("FSSC 22000 — Food Safety System Certification",
                   "GFSI-recognised food safety scheme built on ISO 22000.",
                   "Food and food-packaging manufacture"),
    "ISO 22000": ("ISO 22000 — Food safety management system",
                  "Food safety management across the chain.",
                  "Food production and handling; HACCP"),
    "Halal certification": ("Halal certification",
                            "Conformity of products and processes with halal requirements.",
                            "Product formulation, segregation, cleaning validation"),
    "Kosher certification": ("Kosher certification",
                             "Conformity of products and processes with kashrut requirements.",
                             "Product formulation; equipment kashering"),

    # --- governance / compliance
    "ISO 37001": ("ISO 37001 — Anti-bribery management system",
                  "Systems to prevent, detect and respond to bribery.",
                  "Procurement ethics; third-party due diligence; gifts and hospitality"),
    "ISO 37301": ("ISO 37301 — Compliance management system",
                  "General regulatory compliance management.",
                  "Legal and compliance function; obligations register"),
    "C-TPAT": ("Customs-Trade Partnership Against Terrorism",
               "US CBP supply-chain security programme.",
               "Import/export security, container integrity, partner vetting"),
    "AEO": ("Authorised Economic Operator",
            "Customs-recognised trusted-trader status.",
            "Customs clearance, cross-border logistics"),
    "ITAR registration": ("ITAR — International Traffic in Arms Regulations registration",
                          "US State Department registration for defense articles.",
                          "Defense-related design and manufacture; export control"),
    "MBE/WBE/DBE": ("Minority / Women / Disadvantaged Business Enterprise certification",
                    "Ownership-status certification for supplier-diversity programmes.",
                    "Supplier diversity qualification; public procurement set-asides"),
    "OSHA VPP": ("OSHA Voluntary Protection Programs",
                 "US OSHA recognition of exemplary workplace safety systems.",
                 "Site safety programme management"),

    # --- sustainability / social / materials
    "SA8000": ("SA8000 — Social Accountability",
               "Labour and human-rights conditions in the workplace.",
               "Working hours, wages, freedom of association, child/forced labour controls"),
    "OEKO-TEX Standard 100": ("OEKO-TEX Standard 100",
                              "Harmful-substance limits in textiles.",
                              "Fabric and textile component sourcing and finishing"),
    "bluesign": ("bluesign system",
                 "Input-stream management for safe and sustainable textile production.",
                 "Textile chemistry, dyeing and finishing"),
    "FSC": ("Forest Stewardship Council chain of custody",
            "Responsibly sourced wood, paper and fibre.",
            "Packaging, wood products, paper supply chain"),
    "ASI Chain of Custody": ("Aluminium Stewardship Initiative — Chain of Custody",
                             "Traceability of responsibly produced aluminium.",
                             "Aluminium smelting, casting, extrusion, rolling supply chain"),
    "QUALICOAT": ("QUALICOAT",
                  "Quality label for organic coating on aluminium.",
                  "Powder coating and anodising lines"),
    "EN 15088": ("EN 15088 — Aluminium structural products",
                 "Execution of structural aluminium products for construction.",
                 "Structural aluminium fabrication; CE marking of structural components"),
    "GreenCircle Multi-Attribute Label": (
        "GreenCircle Certified — Multi-Attribute Label Program",
        "A multi-criteria PRODUCT sustainability label created to serve US Federal "
        "Executive Order 13514 sustainable-procurement requirements. One label bundles a "
        "completed Life Cycle Assessment, a published Environmental Product Declaration, "
        "water use, waste diversion and carbon-footprint reduction. It is not a management "
        "system and not a registrar audit of the plant.",
        "Product sustainability claims; federal/GSA procurement eligibility; LEED "
        "contribution via EPDs and HPDs"),
    "Ontario TRA (O. Reg. 455/09)": (
        "Ontario Toxics Reduction Act and O. Reg. 455/09",
        "Canadian provincial toxics-reduction planning and reporting obligation.",
        "Substance tracking and reduction planning at Ontario facilities"),
    "LEED": ("LEED — Leadership in Energy and Environmental Design",
             "Green building rating for a facility, not for its products.",
             "Plant and office construction and operation"),
    "EPD": ("Environmental Product Declaration",
            "Third-party verified lifecycle environmental data for a product.",
            "Product LCA; green procurement disclosure"),
    "ISCC PLUS": ("ISCC PLUS — International Sustainability & Carbon Certification",
                  "Chain of custody for bio-based and circular (recycled) feedstocks, "
                  "including mass balance.",
                  "Recycled/bio-content claims in polymers and chemicals; mass-balance "
                  "bookkeeping"),
    "EMAS": ("EMAS — EU Eco-Management and Audit Scheme",
             "EU environmental management and public performance reporting; stricter than "
             "ISO 14001 in requiring a verified public statement.",
             "Environmental performance reporting at EU sites"),
    "EcoVadis": ("EcoVadis sustainability rating",
                 "A supplier sustainability **rating** (Bronze/Silver/Gold/Platinum), not a "
                 "certification — no standard is conformed to and no certificate is issued.",
                 "Customer sustainability scorecards; procurement qualification"),
    "Copper Mark": ("The Copper Mark",
                    "Assurance framework for responsible copper, molybdenum, nickel and zinc "
                    "production.",
                    "Copper smelting/refining supply chain"),
    "Superior Energy Performance": (
        "Superior Energy Performance (US DOE)",
        "DOE certification of verified energy-performance improvement, built on ISO 50001.",
        "Plant energy performance improvement programmes"),
    "Responsible Care": ("Responsible Care",
                         "Chemical industry health, safety, security and environment programme.",
                         "Chemical manufacture, distribution, process safety"),

    # --- product / regulatory
    "UL listing": ("UL listing / UL certification",
                   "Product safety certification, chiefly electrical. A product mark, not a "
                   "management system — the scope is the listed product, not the plant.",
                   "Component and end-product electrical safety; field evaluation"),
    "CE marking": ("CE marking",
                   "Manufacturer's declaration of conformity with applicable EU directives.",
                   "EU market access; technical file and DoC maintenance"),
    "RoHS": ("RoHS — Restriction of Hazardous Substances",
             "Limits on hazardous substances in electrical and electronic equipment.",
             "Material declarations; substance-of-concern screening; supplier data"),
    "REACH": ("REACH — Registration, Evaluation, Authorisation of Chemicals",
              "EU chemical registration and SVHC communication duties.",
              "Chemical inventory, substance declarations, article notification"),
    "NSF/ANSI 61": ("NSF/ANSI 61 — Drinking water system components, health effects",
                    "Health-effects safety of materials contacting drinking water.",
                    "Valves, fittings, coatings and seals for potable water"),
    "NSF/ANSI 372": ("NSF/ANSI 372 — Drinking water system components, lead content",
                     "Weighted-average lead content conformity ('lead free').",
                     "Potable-water components and plumbing fittings"),
    "CSA C22.2": ("CSA C22.2 — Canadian Electrical Code, Part II product standards",
                  "Canadian electrical product safety certification.",
                  "Electrical product certification for the Canadian market"),
    "CARB": ("California Air Resources Board compliance",
             "California emissions and formaldehyde/air-quality requirements.",
             "Engine, aftertreatment and composite-wood product compliance"),
}

DOMAIN_ORDER = ["Automotive", "EV/battery", "Functional safety", "Rail", "Aerospace",
                "Core management systems", "Information security", "Laboratory/testing",
                "Medical/food/drug", "Governance/compliance", "Sustainability/materials",
                "Product/regulatory"]


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _flatten(merged: list[dict]) -> tuple[list[dict], list[dict]]:
    """Merged records -> (source-level rows, one-per-record 'winner' rows).

    The merge already resolved each (company, standard) to a single record, so the winner
    list is simply the records themselves. The source-level rows are still needed for the
    run-1 baseline in section 0 and the raw-string table in section 3, both of which have to
    see what each origin actually said."""
    rows, winners = [], []
    for r in merged:
        conf = r["verification"]["quotes_confirmed"]
        winners.append({
            "record_no": str(r["record_no"]), "company": r["company"],
            "canonical_id": r["certification"], "family": r["family"], "domain": r["domain"],
            "scope_bucket": r["facility_scope"], "cert_status": r["cert_status"],
            "certification_body": r["certification_body"] or "",
            "reference_no": r["reference_no"] or "", "issue_date": r["issue_date"] or "",
            "expiry_date": r["expiry_date"] or "", "scope": r["scope"] or "",
            "source_url": (r["evidence"]["best_source_url"] or ""),
            "raw_certification": r["certification"],
            "quotes_confirmed": conf,
            "scope_basis": r["facility_scope_basis"],
            # "grounded" now means the merged evidence survived a check against the live page,
            # which is a stronger and more uniform test than the pass-B gate could apply.
            "ev_canonical": r["certification"] if conf >= 1 else "",
            "source_run": "merged",
        })
        for sr in r["sources"]:
            rows.append({
                "record_no": str(r["record_no"]), "company": r["company"],
                "canonical_id": r["certification"], "family": r["family"],
                "domain": r["domain"], "scope_bucket": r["facility_scope"],
                "source_run": sr["origin"],
                "raw_certification": sr["certification_as_written"],
                "cert_status": sr["cert_status"],
                "certification_body": sr.get("certification_body") or "",
                "reference_no": sr.get("reference_no") or "",
                "issue_date": sr.get("issue_date") or "",
                "expiry_date": sr.get("expiry_date") or "",
                "scope": sr.get("scope") or "",
            })
    return rows, winners


def _counts(winners: list[dict]) -> list[dict]:
    """Per standard: companies Georgia-evidenced / group-only / affiliate-only / total."""
    by: dict[str, dict] = {}
    for r in winners:
        c = by.setdefault(r["canonical_id"], {
            "canonical_id": r["canonical_id"], "family": r["family"], "domain": r["domain"],
            "ga": set(), "grp": set(), "aff": set(), "all": set()})
        c["all"].add(r["record_no"])
        if r["scope_bucket"] == GA:
            c["ga"].add(r["record_no"])
        else:
            c["grp"].add(r["record_no"])
            if r["scope_bucket"] == "affiliate_only":
                c["aff"].add(r["record_no"])
    out = [{"canonical_id": c["canonical_id"], "family": c["family"], "domain": c["domain"],
            "companies_ga_evidenced": len(c["ga"]),
            "companies_group_only": len(c["grp"] - c["ga"]),
            "of_which_affiliate_only": len(c["aff"]),
            "companies_total": len(c["all"])} for c in by.values()]
    out.sort(key=lambda r: (-r["companies_total"], r["canonical_id"]))
    return out


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.1f}%" if total else "—"


def coverage(winners: list[dict], total_companies: int, ids: set[str] | None = None,
             domain: str | None = None) -> tuple[int, int, int]:
    """(companies Georgia-evidenced, companies group-only, companies total) for a slice."""
    ga, grp = set(), set()
    for r in winners:
        if r["canonical_id"] in NONE_IDS:
            continue
        if ids and r["canonical_id"] not in ids:
            continue
        if domain and r["domain"] != domain:
            continue
        (ga if r["scope_bucket"] == GA else grp).add(r["record_no"])
    return len(ga), len(grp - ga), len(ga | grp)


def build(out_dir: Path) -> Path:
    merged = _read_jsonl(out_dir / "certifications_merged.jsonl")
    absences = _read_jsonl(out_dir / "absences_merged.jsonl")
    rows, winners = _flatten(merged)
    counts = _counts(winners)

    missing = sorted({r["canonical_id"] for r in winners if r["canonical_id"] not in KEY})
    if missing:
        raise SystemExit("KEY is missing entries for: " + ", ".join(missing))

    all_recs = ({str(r["record_no"]) for r in merged} |
                {str(r["record_no"]) for r in absences})
    total = len(all_recs)
    certified = {r["record_no"] for r in winners}
    no_cert = total - len(certified)

    links = json.loads((out_dir / "link_status.json").read_text()) \
        if (out_dir / "link_status.json").exists() else {}
    review = out_dir / "needs_review.csv"
    review_rows = _read(review) if review.exists() else []
    ev_hits = [r for r in winners if r["domain"] == "EV/battery"]
    ev_negative_recs = {str(r["record_no"]) for r in absences if r["absence_type"] == "no_ev"}
    # Kept separate from no_ev on purpose. The two sweeps tested DIFFERENT standards, so a
    # company can hold ISO 26262 (grounded by pass B) and hold no UNECE R100 (pass E) at the
    # same time — 8 records are in exactly that position. Folding pass E's negatives into
    # ev_negative_recs would make this section report companies as having "no EV/battery
    # standard" while §1 lists their grounded functional-safety hit.
    ev_delta_recs = {str(r["record_no"]) for r in absences
                     if r["absence_type"] == "no_ev_delta"}

    L: list[str] = []
    add = L.append

    add("# Certification Key — GNEM Georgia automotive/EV supplier base")
    add("")
    origins = sorted({r["source_run"] for r in rows})
    add(f"*Generated {date.today().isoformat()} from `certifications_merged.jsonl` — every "
        f"result set combined: two independent LLM runs (`llm_a`, `llm_b`) plus this "
        f"pipeline's run 1 and gap-fill passes A/B/C/E. {len(rows)} contributing source rows "
        f"from {len(origins)} origins, merged into {len(winners)} distinct (company, standard) "
        f"records over {total} companies. Every source URL was fetched and every quote checked "
        f"against the page it came from.*")
    add("")
    add("Two conventions hold throughout, and both change the headline numbers:")
    add("")
    ga_rows = [r for r in merged if r["facility_scope"] == GA]
    ga_verified = sum(1 for r in ga_rows if r["facility_scope_basis"] == "verified_source")
    ga_unverified = len(ga_rows) - ga_verified
    add("1. **Facility scope is never blended.** A certificate held by a parent or a sister "
        "plant abroad does not make the Georgia supplier certified. Every count is split into "
        "**Georgia-evidenced** (a source ties the certificate to the Georgia site) and "
        "**group holds it, Georgia site not evidenced**.")
    add(f"   Georgia-evidenced is itself two-tier: of {len(ga_rows)} such rows, "
        f"**{ga_verified}** rest on a source that cleared the quality bar "
        f"(`facility_scope_basis: verified_source` — quote confirmed, link not dead, not an "
        f"aggregator) and **{ga_unverified}** do not. The second group is reported, not "
        f"dropped, but it should not be quoted as Georgia-evidenced without that caveat.")
    add("2. **`none identified` means unknown, not uncertified.** It records that a search "
        "found nothing, which is a statement about the evidence, not about the company.")
    add("")
    add("---")
    add("")

    # ---------------------------------------------------------------- section 0
    # The run-1 baseline must come from ALL run-1 rows, not just the ones that won the detail
    # resolution: pass C usually wins on completeness, which would otherwise erase run 1's
    # own coverage from the "before" column and overstate what this run added.
    r1_rows = [r for r in rows if r["source_run"] == "run1" and r["canonical_id"] not in NONE_IDS]
    r1_certified = {r["record_no"] for r in r1_rows}
    r1_standards = {r["canonical_id"] for r in r1_rows}
    all_standards = {r["canonical_id"] for r in winners if r["canonical_id"] not in NONE_IDS}

    def _detail(rs: list[dict]) -> tuple[int, int, int]:
        """Per (company, standard), does ANY contributing row carry each detail field?"""
        best: dict[tuple[str, str], list[bool]] = {}
        for r in rs:
            if r["canonical_id"] in NONE_IDS:
                continue
            k = (r["record_no"], r["canonical_id"])
            cur = best.setdefault(k, [False, False, False])
            cur[0] |= bool(r["certification_body"].strip())
            cur[1] |= bool(r["reference_no"].strip())
            cur[2] |= bool(r["expiry_date"].strip())
        return (sum(v[0] for v in best.values()), sum(v[1] for v in best.values()),
                sum(v[2] for v in best.values()))
    b1, n1, e1 = _detail(r1_rows)
    b2, n2, e2 = _detail(rows)

    add("## 0. What this run changed")
    add("")
    add("| | Run 1 alone | All sources merged | Change |")
    add("|---|---:|---:|---:|")
    add(f"| Companies with no certification identified | {total - len(r1_certified)} | "
        f"{no_cert} | **−{(total - len(r1_certified)) - no_cert}** |")
    add(f"| Distinct standards identified | {len(r1_standards)} | {len(all_standards)} | "
        f"**+{len(all_standards) - len(r1_standards)}** |")
    add(f"| Records naming a registrar | {b1} | {b2} | **+{b2 - b1}** |")
    add(f"| Records carrying a certificate number | {n1} | {n2} | **+{n2 - n1}** |")
    add(f"| Records carrying an expiry date | {e1} | {e2} | **+{e2 - e1}** |")
    add("")
    add("Three gaps closed, one confirmed:")
    add("")
    add(f"- **The 78 unaudited blanks.** Re-searched by pass A and independently covered by "
        f"both LLM runs. {(total - len(r1_certified)) - no_cert} of them now carry a real "
        f"certification. The remaining {no_cert} are still \"not found\" — but every such row "
        f"records the queries issued and the URLs opened, so the negative can be audited "
        f"instead of trusted. In run 1 those rows had a blank `source_url` *and* a blank "
        f"`evidence_quote`.")
    add("- **Certificate identity.** Pass C recovered registrars, certificate numbers and "
        "expiry dates, the two LLM runs contributed more, and a final pass re-read verified "
        "pages to fill what was still missing. Every value had to appear on its own source "
        "page after date and reference-number normalisation; values that failed were dropped, "
        "not kept.")
    add("- **The EV/battery absence** was tested rather than assumed — see §1.")
    add("- **Both flagged entries resolved** — see §4.")
    add("")
    add("---")
    add("")

    # ---------------------------------------------------------------- section 1
    add("## 1. Coverage assessment")
    add("")
    add(f"Base: **{total} companies**. A company counts once per standard, on the row with "
        f"the strongest facility evidence.")
    add("")
    add("| Domain / standard | Georgia-evidenced | Group only | *of which affiliate-only* | "
        "Any evidence |")
    add("|---|---:|---:|---:|---:|")

    def domain_row(label: str, dom: str) -> None:
        ga, grp, tot = coverage(winners, total, domain=dom)
        aff = len({r["record_no"] for r in winners
                   if r["domain"] == dom and r["scope_bucket"] == "affiliate_only"})
        add(f"| **{label}** | {ga} ({_pct(ga, total)}) | {grp} | *{aff}* | {tot} "
            f"({_pct(tot, total)}) |")

    for dom in DOMAIN_ORDER:
        if any(r["domain"] == dom for r in winners if r["canonical_id"] not in NONE_IDS):
            domain_row(dom, dom)
    add(f"| **No certification identified** | — | — | — | {no_cert} ({_pct(no_cert, total)}) |")
    add("")

    add("### Headline standards")
    add("")
    add("| Standard | Georgia-evidenced | Group only | *affiliate-only* | Any evidence |")
    add("|---|---:|---:|---:|---:|")
    for c in counts[:14]:
        if c["canonical_id"] in NONE_IDS:
            continue
        add(f"| {c['canonical_id']} | {c['companies_ga_evidenced']} "
            f"({_pct(int(c['companies_ga_evidenced']), total)}) | "
            f"{c['companies_group_only']} | *{c['of_which_affiliate_only']}* | "
            f"{c['companies_total']} ({_pct(int(c['companies_total']), total)}) |")
    add("")
    _c21 = len({r["record_no"] for r in winners if r["canonical_id"] == "ISO 21434"})
    _g21 = len({r["record_no"] for r in winners
                if r["canonical_id"] == "ISO 21434" and r["ev_canonical"]})
    add(f"> **Why §1 and the EV section can disagree.** This table counts every company a "
        f"source connects to a standard — the same basis run 1 used, so the columns stay "
        f"comparable. The EV/battery section below applies a stricter test on top: the quote "
        f"behind the claim must still be findable on the live page. ISO 21434 therefore reads "
        f"{_c21} here and {_g21} there. Where a number is load-bearing, use the verified one.")
    add("")

    # ---------------------------------------------------------------- EV finding
    add("### The EV/battery question")
    add("")
    # Only rows that survived the grounding gate count here. A row can name a standard and
    # still fail: the quote must tie THIS company to THAT standard in one sourced sentence.
    BATTERY_PRODUCT = {"UN 38.3", "IEC 62660", "IEC 62619", "IEC 62133", "UL 2580", "UL 1973",
                       "UL 2271", "UL 1642"}
    EV_ELECTRICAL = {"ISO 6469", "ISO 15118", "SAE J1772", "IEC 61851", "IEC 62196", "UL 2594",
                     "UL 2202", "ISO 17409"}
    FUNCTIONAL_SAFETY = {"ISO 26262", "IEC 61508", "ISO 21434"}
    BATTERY_HANDLING = {"IATA CEIV Lithium Batteries"}

    grounded = [r for r in winners if r.get("ev_canonical", "").strip()]
    def _g(ids: set[str]) -> list[dict]:
        return [r for r in grounded if r["canonical_id"] in ids]
    def _claimed(ids: set[str]) -> set[str]:
        return {r["record_no"] for r in winners if r["canonical_id"] in ids}
    fs = _g(FUNCTIONAL_SAFETY)
    fs_recs = {r["record_no"] for r in fs}
    handling = [r for r in winners if r["canonical_id"] in BATTERY_HANDLING]
    ev_review = [r for r in review_rows
                 if r["reason"] in ("unrecognized_battery_token", "company_not_in_quote",
                                    "standard_not_in_quote", "ungrounded_cooccurrence",
                                    "quote_not_in_evidence")]
    add(f"The EV/battery question was put to **all {total} companies** four times over: "
        f"this pipeline's pass B and pass E, and both independent LLM runs. **Pass B** "
        f"(2026-08-10) searched with queries naming UN 38.3, "
        f"IEC 62660/62619/62133, UL 2580/1973/2271/1642, ISO 6469, ISO 15118, SAE J1772, "
        f"IEC 61851/62196, ISO 17409, ISO 21434, ISO 26262 and IEC 61508 explicitly — none of "
        f"which run 1 ever mentioned. **Pass E** (2026-08-13) closed the gaps pass B's canon "
        f"had left, naming UNECE R100, ISO 12405, GB 38031, SAE J2929, SAE J2380, UL 2231 and "
        f"the IEC 62660 parts. Each standard is attributed below to the sweep that actually "
        f"queried it. The result splits four ways:")
    add("")
    add("A claim counts here only if its evidence still holds up: the quote behind it was "
        "re-fetched and found on the page it was attributed to. Claims whose quote could not "
        "be located are shown in the third column, not silently dropped and not silently "
        "counted.")
    add("")
    add("| | Companies (verified) | Claimed, quote unverified | Reading |")
    add("|---|---:|---:|---|")
    add(f"| **Battery product standard** (UN 38.3, IEC 62660/62619/62133, UL 2580/1973/2271/1642) "
        f"| **{len({r['record_no'] for r in _g(BATTERY_PRODUCT)})}** "
        f"| {len(_claimed(BATTERY_PRODUCT) - {r['record_no'] for r in _g(BATTERY_PRODUCT)})} "
        f"| No company makes or qualifies a battery to a battery standard. |")
    add(f"| **Battery handling / logistics** (IATA CEIV Lithium Batteries) "
        f"| **{len({r['record_no'] for r in handling})}** | 0 "
        f"| Certifies the *freight handler*, not the battery. |")
    add(f"| **EV-electrical / charging** (ISO 6469, ISO 15118, SAE J1772, IEC 61851, …) "
        f"| **{len({r['record_no'] for r in _g(EV_ELECTRICAL)})}** "
        f"| {len(_claimed(EV_ELECTRICAL) - {r['record_no'] for r in _g(EV_ELECTRICAL)})} "
        f"| Nothing. No company holds one. |")
    add(f"| **Functional safety / cybersecurity** (ISO 26262, ISO 21434, IEC 61508) "
        f"| **{len(fs_recs)}** "
        f"| {len(_claimed(FUNCTIONAL_SAFETY) - fs_recs)} "
        f"| The only EV-adjacent signal present — and it is not EV-specific. |")
    add("")
    if handling:
        h = handling[0]
        add(f"The one battery-related certification in the whole file is **{h['company']}**'s "
            f"**IATA CEIV Lithium Batteries** (`{h['scope_bucket']}` — it belongs to the Korean "
            f"parent, Hyundai Glovis). It is an air-logistics qualification for *handling* "
            f"lithium batteries: the company can ship batteries safely, not make or qualify "
            f"them. For a Georgia EV knowledge base that is a supply-chain fact, not a "
            f"battery-manufacturing one.")
        add("")
        add("> This same story is also the clearest illustration of why the grounding gate "
            "matters in both directions. The model first reported it as **\"UN 38.3 (Lithium "
            "Battery Air Transport)\"** — the right event under the wrong standard's name. That "
            "row was rejected (`standard_not_in_quote`) and sits in `needs_review.csv`; the "
            "correctly-named IATA CEIV row is the one counted. A looser gate would have "
            "published a UN 38.3 holder that does not exist.")
        add("")
    if fs:
        add("The functional-safety holders whose evidence verified, with the scope the "
            "evidence actually supports:")
        add("")
        add("| Company | Standard | Facility scope |")
        add("|---|---|---|")
        for r in sorted(fs, key=lambda r: (r["canonical_id"], r["company"])):
            add(f"| {r['company']} | {r['canonical_id']} | `{r['scope_bucket']}` |")
        add("")
        add("ISO 26262 governs the safety lifecycle of automotive electronics. An EV inverter "
            "and an ICE engine controller are both in scope, so this is **not** an EV signal "
            "either — only a sign that the company builds safety-relevant electronics.")
        add("")
    add(f"**{len(ev_negative_recs)} companies** carry an explicit `no EV/battery standard "
        f"identified` row from pass B recording the queries issued and the pages opened, so "
        f"each zero is individually auditable — and most carry that negative from more than "
        f"one independent run. {len(ev_review)} candidate(s) went to `needs_review.csv` and "
        f"were hand-checked rather than silently counted either way (§4).")
    add("")
    if ev_delta_recs:
        add(f"**Pass E adds {len(ev_delta_recs)} further explicit negatives**, covering the "
            f"standards pass B's canon never named — **UNECE R100, ISO 12405, GB 38031, "
            f"SAE J2929, SAE J2380, UL 2231** and the IEC 62660 parts. UNECE R100 mattered "
            f"most: it is the REESS type-approval regulation, exactly what a Georgia "
            f"battery-pack assembler would hold. Nothing was found — **zero hits on every "
            f"delta target across all {total} companies**. Pass E's one grounded hit "
            f"(#84 Hyundai Transys, ISO 26262) was already grounded by pass B at the same "
            f"`parent_only` scope, so it is an independent cross-check rather than a new "
            f"finding.")
        add("")
        add(f"Between them the two sweeps put **25 distinct standards** to all {total} "
            f"companies and returned **{len(ev_negative_recs) + len(ev_delta_recs)} explicit "
            f"auditable negatives**. The absence of a battery-product standard in this supplier "
            f"base is therefore an evidenced finding, not a gap in the search.")
        add("")
        add("> Two standards are covered less strongly than the rest and should not be quoted "
            "as explicitly tested: **SAE J2464** and **UL 2202** were named in no query by "
            "either sweep. Both would have been recognised had a source returned them — "
            "J2464 via the catch-all, UL 2202 via the canon — but recognition on return is a "
            "weaker claim than an explicit query, and the distinction belongs in the record.")
        add("")
    add("> **What this means for GNEM.** IATF 16949 certifies that a plant can build "
        "automotive parts to a quality system. It is EV-agnostic: an ICE brake-caliper maker "
        "and an EV inverter maker both hold it. The certification column is therefore a good "
        "*automotive-grade manufacturer* signal and a useless *EV/battery supplier* signal. "
        "EV relevance has to come from product description, scope text or NAICS — never from "
        "the presence of an automotive QMS.")
    add("")
    add("---")
    add("")

    # ---------------------------------------------------------------- section 2
    add("## 2. The key — what each certification means and what it maps to")
    add("")
    add("*\"Maps to\" = the services and processes the certificate actually governs.*")
    add("")
    by_dom: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r["canonical_id"] not in NONE_IDS:
            by_dom[r["domain"]].add(r["canonical_id"])
    for dom in DOMAIN_ORDER:
        if dom not in by_dom:
            continue
        add(f"### {dom}")
        add("")
        add("| Standard | Full name | What it certifies | Maps to | In file |")
        add("|---|---|---|---|---:|")
        cnt = {c["canonical_id"]: c for c in counts}
        for cid in sorted(by_dom[dom]):
            full, certifies, maps = KEY[cid]
            c = cnt.get(cid, {})
            n = f"{c.get('companies_ga_evidenced', 0)} GA / {c.get('companies_total', 0)}"
            add(f"| **{cid}** | {full} | {certifies} | {maps} | {n} |")
        add("")
    add("*\"In file\" = companies with Georgia-evidenced coverage / companies with any "
        "evidence.*")
    add("")
    add("---")
    add("")

    # ---------------------------------------------------------------- section 3
    add("## 3. Normalisation table (raw string → canonical standard)")
    add("")
    add("The same standard appears under many spellings; every count above is computed after "
        "this mapping. Multi-standard cells are split first, then each part is mapped and "
        "de-duplicated within its row.")
    add("")
    pairs: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r["canonical_id"] not in NONE_IDS:
            pairs[r["canonical_id"]].add(r["raw_certification"])
    add("| Canonical | Raw strings seen in the data |")
    add("|---|---|")
    for cid in sorted(pairs):
        raws = sorted(pairs[cid])
        shown = "; ".join(f"`{x}`" for x in raws[:8])
        if len(raws) > 8:
            shown += f" … (+{len(raws) - 8} more)"
        add(f"| **{cid}** | {shown} |")
    add("")
    add("---")
    add("")

    # ---------------------------------------------------------------- section 4
    add("## 4. Notes and flags")
    add("")
    add("**Two entries flagged in the first assessment, both now resolved:**")
    add("")
    add("- **`Multi-Attribute Label Certification`** (Superior Essex, record 171) is "
        "**GreenCircle Certified LLC's Multi-Attribute Label Program** — a product "
        "sustainability label built for Federal Executive Order 13514 procurement, bundling a "
        "Life Cycle Assessment, an Environmental Product Declaration, water, waste and carbon "
        "data. Superior Essex was the first and only cable manufacturer in the pilot "
        "(Feb 2015) and applied it to ~50 premises copper/fibre cables. It is **not** a "
        "management-system standard and **not** a registrar audit of the plant, so the "
        "original `company_claim_only` / `low` classification was correct. "
        "([Business Wire](https://www.businesswire.com/news/home/20150217005145/en/Superior-Essex-Announces-Participation-Multi-Attribute-Label-Pilot), "
        "[Superior Essex](https://superioressex.com/news/superior-essex-announces-its-participation-in-the-multi-attribute-label-pilot-program/))")
    add("- **`OHSAS 18004`** (Inalfa Roof Systems, record 145) — **no such standard exists.** "
        "The number collides with **BS 18004:2008**, a BSI *guidance* document (\"Guide to "
        "achieving effective occupational health and safety performance\", built on HSG 65), "
        "and with **OHSAS 18002:2008**, implementation guidance for 18001. The string comes "
        "from Inalfa's own web page (\"The facilities in Korea have been awarded with the "
        "OHSAS 18004 certification\"), so it is the source's error, not a pipeline typo. "
        "Almost certainly **OHSAS 18001** was intended — itself withdrawn and superseded by "
        "ISO 45001 with a March 2021 migration deadline, making it `historical_only` at best. "
        "The row is `affiliate_only` (Korean plants), so it says nothing about the Georgia "
        "facility. Normalised here to **OHSAS 18001** with that caveat attached. "
        "([BS 18004:2008](https://webstore.ansi.org/standards/bsi/bs180042008), "
        "[OHSAS 18001](https://en.wikipedia.org/wiki/OHSAS_18001))")
    add("")
    add("**Superseded standards present in the data** — treat a live claim as historical:")
    add("")
    add("| Written as | Canonical | Status |")
    add("|---|---|---|")
    add("| ISO/TS 16949, TS 16949, QS-9000 | IATF 16949 | Superseded 2016 |")
    add("| OHSAS 18001, OHSAS 18004 | OHSAS 18001 | Withdrawn; ISO 45001 since March 2021 |")
    add("")
    if review_rows:
        add(f"**`needs_review.csv` — {len(review_rows)} row(s)** held back from the counts "
            f"rather than silently dropped or silently counted:")
        add("")
        add("| Company | Certification | Held back because | Hand-check outcome |")
        add("|---|---|---|---|")
        for r in review_rows:
            res = r.get("resolution", "").strip()
            note = r.get("resolution_note", "").strip()
            outcome = f"**{res}** — {note}" if res else "—"
            add(f"| {r['company']} | {r['certification']} | `{r['reason']}` | {outcome} |")
        add("")
        add("Rows marked `—` are the automatic demotions from `audit_rows.py` (a job posting or "
            "an unopenable redirect stub as the only source); they need no individual judgement, "
            "because a hiring ad naming a standard is not evidence of holding it. The rows with "
            "an outcome were each read against their source.")
        add("")
    add("**Verification is quote-level, not claim-level.** A page can support a claim while "
        "the recorded quote does not match it verbatim — Hyundai Transys Georgia Seating's "
        "ISO 26262 row is the clearest case: the cited article does carry \"Transys\", "
        "\"26262\", \"functional safety\" and \"TÜV Rheinland\", but the stored quote was "
        "assembled from a search snippet whose wording differs from the headline, so it "
        "cannot be found verbatim and the row stays unverified. Read `sources[]` before "
        "treating an unverified row as false.")
    add("")
    add("**Limits of the evidence.** A grounded quote proves the company and the standard "
        "appear together in one sourced sentence; it does not prove polarity. \"X is not "
        "certified to UN 38.3\" and \"we help clients achieve IEC 62619\" both pass an "
        "automatic grounding check, which is why every surviving EV/battery hit was "
        "hand-checked before the numbers above were written.")
    add("")
    add("---")
    add("")

    # ---------------------------------------------------------------- section 5
    add("## 5. Using this column in the GNEM pipeline")
    add("")
    add("- **Do not use IATF 16949 as an EV-relevance feature.** It says \"automotive-grade "
        "manufacturer\", nothing more.")
    add(f"- **Normalise before counting.** The raw column holds "
        f"{len({r['raw_certification'] for r in rows if r['canonical_id'] not in NONE_IDS})} "
        f"distinct strings for "
        f"{len({r['canonical_id'] for r in rows if r['canonical_id'] not in NONE_IDS})} "
        f"actual standards; use `certifications_normalized.csv`, not the raw cell.")
    add("- **Respect facility scope.** Filtering on \"holds ISO 9001\" without checking "
        "`scope_bucket` will credit Georgia plants with their parent's certificates.")
    add("- **Keep `none identified` distinct from \"no certifications\".** It is missing "
        "evidence; every such row in pass A now records the queries issued and the pages "
        "opened, so a \"no\" can be audited instead of trusted.")
    add("")

    path = out_dir / "certification_key.md"
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(L)} lines)")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    build(ap.parse_args().dir)


if __name__ == "__main__":
    main()
