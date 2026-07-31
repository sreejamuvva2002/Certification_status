"""Table schemas, enums, and the evidence model.

Two enums do the heavy lifting and they are deliberately orthogonal:

  EVIDENCE_LEVELS  — how good is our access to the source?
  CELL_STATUSES    — what happened when we tried to ground this value?

The single most important distinction in this file is `not_stated` vs
`unverifiable`. `not_stated` is a POSITIVE finding: we hold the full text and it
does not report this quantity. `unverifiable` means we never got close enough to
know. Collapsing them would let "we couldn't read the paper" masquerade as "the
paper omits this" — a fabricated claim about the literature. The rule is
enforced in code (see `resolve_missing`), never left to the model.

This mirrors the research_status / certification_status split that the
certification pipeline uses to keep search failures from reading as findings.
"""
from __future__ import annotations

EVIDENCE_LEVELS = {
    "full_text_verified",  # quote located in retrieved full text
    "abstract_only",       # quote located in the abstract; full text never obtained
    "metadata_only",       # from Crossref/OpenAlex/Google Patents JSON, not from prose
    "not_stated",          # we HAVE the full text and it does not report this
    "unverifiable",        # we could not retrieve enough to know
}

CELL_STATUSES = {
    "grounded_verbatim",     # value is a substring of the retrieved text
    "grounded_numeric",      # magnitude + canonical unit matched a quantity in the text
    "grounded_controlled",   # enum value backed by a grounded quote
    "inference_from_quote",  # appraisal; the QUOTE grounds, the value is analysis
    "quote_repaired",        # model's quote fuzzy-matched back to an exact source span
    "ungrounded_blanked",    # failed grounding -> blanked, flagged, confidence dropped
    "not_stated",
    "unverifiable",
    "conflicting",
}

PUB_TYPES = {
    "original_research", "review", "systematic_review", "meta_analysis",
    "book_chapter", "conference_paper", "thesis", "patent", "other",
}
PREP_METHODS = {
    "solution_casting", "electrospinning", "extrusion", "coating", "impregnation",
    "lyophilization", "spray_drying", "coacervation", "hot_melt", "printing",
    "lamination", "other", "not_stated",
}
TRIGGERS = {
    "humidity_moisture", "liquid_water", "temperature", "ph", "enzymatic",
    "mechanical", "passive_diffusion", "other", "not_stated",
}
RELEASE_METHODS = {
    "gc_fid", "gc_ms", "headspace_gc", "ptr_ms", "photoacoustic", "colorimetric",
    "gravimetric", "bioassay", "other", "not_stated",
}
KINETIC_MODELS = {
    "zero_order", "first_order", "higuchi", "korsmeyer_peppas", "weibull",
    "peppas_sahlin", "fickian", "avrami", "other", "none_reported",
}
SCALEUP_BANDS = {"high", "medium", "low", "not_assessable"}
CONCEPT_RELEVANCE = {"core", "adjacent_material", "adjacent_mechanism", "background", "low"}
CLAIM_SCOPE_TYPES = {
    "composition_broad", "composition_narrow", "method_of_making", "method_of_use",
    "apparatus", "packaging_article", "other",
}
SCREEN_DECISIONS = {"include", "exclude", "maybe"}

# Grounding mode per field. Drives grounding.ground_cell dispatch.
#   metadata   - from API JSON; never grounded against prose
#   numeric    - magnitude + unit must match a quantity in the text
#   phrase     - normalized substring / token-overlap against the quote
#   controlled - clamped to an enum, must carry a grounded quote
#   inference  - analysis; the QUOTE must ground and the value may introduce no
#                number that is absent from the quote
LIT_COLS: list[tuple[str, str, str]] = [
    ("reference",              "Reference",                     "metadata"),
    ("doi",                    "DOI",                           "metadata"),
    ("pub_type",               "Publication type",              "controlled"),
    ("substrate_polymer",      "Packaging substrate / polymer", "phrase"),
    ("mcp_carrier",            "1-MCP carrier / inclusion",     "phrase"),
    ("antimicrobial",          "Antimicrobial active",          "phrase"),
    ("prep_method",            "Preparation method",            "controlled"),
    ("manufacturing_temp_c",   "Manufacturing temperature",     "numeric"),
    ("trigger_mechanism",      "Trigger mechanism",             "controlled"),
    ("rh_conditions_pct",      "Relative-humidity conditions",  "numeric"),
    ("storage_temp_c",         "Storage temperature",           "numeric"),
    ("mcp_loading",            "1-MCP loading",                 "numeric"),
    ("release_method",         "Release-measurement method",    "controlled"),
    ("release_duration",       "Release duration",              "numeric"),
    ("kinetic_model",          "Kinetic model",                 "controlled"),
    ("release_result",         "Main release result",           "phrase"),
    ("produce_tested",         "Produce tested",                "phrase"),
    ("package_vol_mass",       "Package volume & produce mass", "numeric"),
    ("quality_outcomes",       "Quality outcomes",              "phrase"),
    ("mechanical_props",       "Mechanical properties",         "numeric"),
    ("barrier_props",          "Barrier properties",            "numeric"),
    ("antimicrobial_outcomes", "Antimicrobial outcomes",        "phrase"),
    ("limitations",            "Major limitations",             "inference"),
    ("scaleup_relevance",      "Scale-up relevance",            "inference"),
    ("concept_relevance",      "Relevance to proposed invention", "inference"),
]

PAT_COLS: list[tuple[str, str, str]] = [
    ("family_id",               "Patent-family identifier",   "metadata"),
    ("title",                   "Title",                      "metadata"),
    ("priority_date",           "Priority date",              "metadata"),
    ("publication_date",        "Publication date",           "metadata"),
    ("assignee",                "Applicant / assignee",       "metadata"),
    ("inventors",               "Inventors",                  "metadata"),
    ("jurisdictions",           "Jurisdictions",              "metadata"),
    # Deliberately NOT "legal status": the Google Patents payload carries no
    # reliable grant/lapse data and EPO OPS needs a key we don't have, so that
    # column would be ~100% unverifiable. Observed family members are directly
    # evidenced by the priority/family tables on each patent page and are a
    # better proxy for how seriously a family was prosecuted.
    ("family_members_seen",     "Family members observed",    "metadata"),
    ("independent_claim_gist",  "Independent-claim summary",  "inference"),
    ("packaging_format",        "Packaging format",           "phrase"),
    ("mcp_carrier",             "1-MCP carrier",              "phrase"),
    ("release_trigger",         "Release trigger",            "controlled"),
    ("release_control",         "Release-control mechanism",  "phrase"),
    ("antimicrobial_component", "Essential-oil / antimicrobial", "phrase"),
    ("manufacturing_method",    "Manufacturing method",       "phrase"),
    ("claim_limitations",       "Key claim limitations",      "inference"),
    ("overlap_with_concept",    "Possible overlap with concept", "inference"),
    ("design_around",           "Design-around opportunities", "inference"),
    ("uncertainty",             "Remaining uncertainty",      "inference"),
]

LIT_KEYS = [k for k, _, _ in LIT_COLS]
PAT_KEYS = [k for k, _, _ in PAT_COLS]
LIT_MODE = {k: m for k, _, m in LIT_COLS}
PAT_MODE = {k: m for k, _, m in PAT_COLS}
LIT_LABELS = [(k, lbl) for k, lbl, _ in LIT_COLS]
PAT_LABELS = [(k, lbl) for k, lbl, _ in PAT_COLS]

# Enum bound to each controlled field.
FIELD_ENUMS = {
    "pub_type": PUB_TYPES,
    "prep_method": PREP_METHODS,
    "trigger_mechanism": TRIGGERS,
    "release_method": RELEASE_METHODS,
    "kinetic_model": KINETIC_MODELS,
    "release_trigger": TRIGGERS,
}

# Provenance columns appended to the CSV only (not part of the 25/19 deliverable).
LIT_PROVENANCE = [
    "work_id", "year", "venue", "authors", "source", "oa_status", "fulltext_source",
    "fulltext_chars", "screen_decision", "extraction_model", "extracted_at",
    "n_full_text_cells", "n_abstract_cells", "n_not_stated", "n_unverifiable",
    "n_blanked", "row_confidence",
]
PAT_PROVENANCE = [
    "pub_number", "n_family_members", "claims_chars", "extraction_model",
    "extracted_at", "n_blanked", "row_confidence",
]

# Keywords that must appear near a matched number for it to count as that
# field's value. Stops a real number being lifted from an unrelated sentence —
# the most common "plausible but wrong" extraction failure.
NUMERIC_CONTEXT = {
    "manufacturing_temp_c": {"dry", "dried", "drying", "cure", "cured", "extrud",
                             "cast", "oven", "process", "prepar", "coat", "press"},
    "rh_conditions_pct":    {"rh", "relative humidity", "humid"},
    "storage_temp_c":       {"stor", "cold", "shelf", "chamber", "refrigerat", "kept", "held"},
    "mcp_loading":          {"load", "content", "encapsulat", "complex", "dos",
                             "concentration", "w/w", "wt%", "per gram", "mg/g"},
    "release_duration":     {"releas", "over", "within", "after", "during", "period"},
    "package_vol_mass":     {"package", "jar", "container", "headspace", "volume",
                             "mass", "weight", "fruit", "kg", "g of"},
    "mechanical_props":     {"tensile", "elongation", "modulus", "strength",
                             "break", "puncture", "young"},
    "barrier_props":        {"permeab", "wvp", "wvtr", "otr", "oxygen",
                             "water vapour", "water vapor", "transmission"},
}


def pick(value: object, allowed: set[str], default: str) -> str:
    """Clamp a model-supplied value to an enum. Same discipline as _norm_row."""
    s = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if s in allowed:
        return s
    for a in allowed:  # tolerate 'korsmeyer peppas model' -> 'korsmeyer_peppas'
        if a in s or s in a:
            return a
    return default


def new_cell(**kw) -> dict:
    cell = {"value": "", "unit": "", "raw": "", "quote": "", "locator": "",
            "level": "unverifiable", "status": "unverifiable", "checks": []}
    cell.update(kw)
    return cell


def resolve_missing(has_full_text: bool) -> tuple[str, str]:
    """The not_stated / unverifiable decision. Made in code, never by the model.

    Only a work whose full text we actually hold can be said to omit something.
    """
    return ("not_stated", "not_stated") if has_full_text else ("unverifiable", "unverifiable")


def row_confidence(cells: dict[str, dict]) -> str:
    """Confidence band from how much of the row is genuinely grounded."""
    graded = [c for k, c in cells.items() if LIT_MODE.get(k) != "metadata"]
    if not graded:
        return "low"
    full = sum(1 for c in graded if c["level"] == "full_text_verified")
    blanked = sum(1 for c in graded if c["status"] == "ungrounded_blanked")
    if blanked > 2:
        return "low"
    if full >= len(graded) * 0.4:
        return "high"
    if full or any(c["level"] == "abstract_only" for c in graded):
        return "medium"
    return "low"


def cell_counts(cells: dict[str, dict]) -> dict[str, int]:
    return {
        "n_full_text_cells": sum(1 for c in cells.values() if c["level"] == "full_text_verified"),
        "n_abstract_cells": sum(1 for c in cells.values() if c["level"] == "abstract_only"),
        "n_not_stated": sum(1 for c in cells.values() if c["level"] == "not_stated"),
        "n_unverifiable": sum(1 for c in cells.values() if c["level"] == "unverifiable"),
        "n_blanked": sum(1 for c in cells.values() if c["status"] == "ungrounded_blanked"),
    }
