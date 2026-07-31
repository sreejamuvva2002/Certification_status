"""Prompts, in the numbered-rule house style of docs/certification_research_prompt.md.

Extraction is split into four blocks rather than one 25-field call. Local models
degrade badly past roughly eight fields of structured JSON, and blocks let a
single failed field group be retried for a fraction of the cost.

Every prompt enforces the same contract: quote or say nothing. A value without a
locatable quote is discarded downstream by grounding.py, so the prompt and the
verifier agree on what counts as evidence.
"""
from __future__ import annotations

SCREEN_CRITERIA = """INCLUDE a paper if it reports evidence on at least one of:
  - 1-MCP encapsulation, retention, or stability
  - humidity-, moisture-, or water-activated release of 1-MCP or another volatile active
  - release kinetics at defined relative humidity or temperature
  - incorporation of 1-MCP into polymers, papers, coatings, labels, pads, sachets, films or inserts
  - chitosan and/or cellulose-nanocrystal films or coatings
  - CNC-stabilised essential-oil Pickering emulsions
  - essential-oil release from packaging, or vapour-phase antimicrobial activity
  - mechanical, barrier, thermal or optical properties of such materials
  - postharvest validation on climacteric produce
  - industrial coating or film-manufacturing compatibility for active packaging
  - food-contact migration, toxicity, sensory effects or regulation of these actives
  - cost, sustainability, recyclability or biodegradability of such packaging

EXCLUDE a paper if it:
  - only mentions active packaging in passing, with no formulation, mechanism, or data
  - studies 1-MCP as a field or pre-harvest spray with no packaging or delivery element
  - is purely about produce physiology with no delivery system and no packaging material
  - is off-topic (medicine, drug delivery with no packaging relevance, unrelated polymers)"""

SCREEN_SYSTEM = (
    "You are a systematic-review screener for a study on humidity-responsive 1-MCP "
    "packaging. You judge relevance from title and abstract only. Output one JSON object "
    "and nothing else."
)

SCREEN_USER = """Screen this record against the criteria.

{criteria}

RECORD
Title: {title}
Year: {year}
Venue: {venue}
Crossref/OpenAlex type: {type}
Abstract: {abstract}

RULES
1. Judge only what the title and abstract state. Do not use outside knowledge of the paper.
2. "maybe" is a legitimate and expected answer. If the abstract is missing or uninformative,
   answer "maybe" — an uninformative abstract is NOT grounds for exclusion.
3. Screening decides inclusion only. Do not attempt to fill in study details here.
4. pub_type must reflect what the record IS, not what it is about. A paper that reviews
   other studies is a review even if the venue is a research journal. Look for signs of
   original data (methods, measurements, results) versus survey language.

OUTPUT JSON:
{{"decision": "include|exclude|maybe",
  "pub_type": "original_research|review|systematic_review|meta_analysis|book_chapter|conference_paper|thesis|other",
  "primary_topic": "<12 words or fewer>",
  "signals": {{"mentions_1mcp": bool, "controlled_release": bool,
              "humidity_or_moisture_trigger": bool, "antimicrobial_eo": bool,
              "cyclodextrin_carrier": bool, "nanocellulose_or_chitosan": bool,
              "pickering_emulsion": bool, "climacteric_produce": bool,
              "packaging_material": bool, "manufacturing_or_scaleup": bool}},
  "exclusion_reason": "<empty unless decision is exclude>",
  "confidence": 0.0}}"""

# --- extraction blocks ------------------------------------------------------

EXTRACT_SYSTEM = (
    "You extract experimental facts from a scientific document into JSON. You are a "
    "transcriber, not an interpreter. Every value you report must be quoted from the "
    "document. Output one JSON object and nothing else."
)

_EXTRACT_RULES = """RULES — these override any instinct to be helpful:
1. Every field is {{"value": ..., "unit": ..., "quote": ..., "where": ...}}.
   `quote` MUST be copied EXACTLY from the Document, character for character.
   If you cannot quote it, the field is {{"value": "not stated"}}.
2. Copy numbers and units exactly as printed, including the printed unit form
   (write "mg g-1" if that is what appears; do NOT convert units — code does that).
3. "not stated" is the correct and expected answer whenever the Document does not report
   the field. Never estimate. Never infer a value from a related one. Never carry a value
   over from a different field or a different study mentioned in the introduction.
4. Report only what THIS study did. Values cited from other papers in the introduction or
   discussion are not this study's values.
5. Never output a DOI, reference, author, year or journal name. Those are supplied separately.
6. If the Document states two conflicting values, report both inside `quote` and set
   "conflict": true.
7. `where` is the section the quote came from: abstract, methods, results, discussion,
   table, caption, or conclusion.
8. Echo the marker at the very end of the Document in "doc_end_marker"."""

EXTRACT_BLOCKS: dict[str, tuple[str, list[str], str]] = {
    "E1": (
        "materials and manufacture",
        ["substrate_polymer", "mcp_carrier", "antimicrobial", "prep_method",
         "manufacturing_temp_c", "trigger_mechanism"],
        """Extract how the material was made.

FIELDS
- substrate_polymer: the packaging substrate or matrix polymer (e.g. chitosan, PLA, paper).
- mcp_carrier: what holds the 1-MCP (e.g. alpha-cyclodextrin, inclusion complex, MOF, silica).
  "not stated" if the study uses no 1-MCP.
- antimicrobial: the antimicrobial active, if any (thymol, carvacrol, essential oil...).
- prep_method: one of solution_casting, electrospinning, extrusion, coating, impregnation,
  lyophilization, spray_drying, coacervation, hot_melt, printing, lamination, other, not_stated.
- manufacturing_temp_c: the temperature at which the material was DRIED, CURED or PROCESSED.
  Not the storage or test temperature.
- trigger_mechanism: what releases the active — humidity_moisture, liquid_water, temperature,
  ph, enzymatic, mechanical, passive_diffusion, other, not_stated.""",
    ),
    "E2": (
        "release performance",
        ["rh_conditions_pct", "storage_temp_c", "mcp_loading", "release_method",
         "release_duration", "kinetic_model", "release_result"],
        """Extract the release measurements.

FIELDS
- rh_conditions_pct: relative humidity or humidities at which release was measured.
- storage_temp_c: the temperature at which release or storage was carried out.
- mcp_loading: how much 1-MCP the material contained (mg/g, %w/w, µL/L...).
- release_method: gc_fid, gc_ms, headspace_gc, ptr_ms, photoacoustic, colorimetric,
  gravimetric, bioassay, other, not_stated.
- release_duration: the period over which release was followed.
- kinetic_model: zero_order, first_order, higuchi, korsmeyer_peppas, weibull, peppas_sahlin,
  fickian, avrami, other, none_reported.
- release_result: the headline release finding, quoted with its numbers.""",
    ),
    "E3": (
        "application and measured outcomes",
        ["produce_tested", "package_vol_mass", "quality_outcomes", "mechanical_props",
         "barrier_props", "antimicrobial_outcomes"],
        """Extract what the material was tested on and what was measured.

FIELDS
- produce_tested: the fruit or vegetable, if any. "not stated" for material-only studies.
- package_vol_mass: package/jar/container volume and the mass of produce in it.
- quality_outcomes: firmness, colour, soluble solids, weight loss, ethylene rate, decay.
- mechanical_props: tensile strength, elongation at break, modulus, puncture.
- barrier_props: water-vapour permeability, oxygen transmission rate.
- antimicrobial_outcomes: log reductions, inhibition zones, target organisms.""",
    ),
    "E4": (
        "appraisal",
        ["limitations", "scaleup_relevance", "concept_relevance"],
        """Appraise the study for a project developing a humidity-responsive, controlled-release
1-MCP packaging material (optionally with an essential-oil antimicrobial) for climacteric fruit.

FIELDS
- limitations: the study's main weaknesses as an evidence source. Quote the passage you base
  this on (a stated limitation, a small sample, a missing control, lab-only conditions).
- scaleup_relevance: how relevant the preparation route is to industrial manufacture.
  value must be one of high, medium, low, not_assessable.
- concept_relevance: value must be one of core, adjacent_material, adjacent_mechanism,
  background, low.

EXTRA RULE for this block: your `value` may paraphrase, but it MUST NOT contain any number
that does not appear in your quote or in the Document. Invented precision is the failure mode
this rule exists to stop.""",
    ),
}


def extract_prompt(block: str, document: str, context: str = "") -> tuple[str, str]:
    label, _fields, body = EXTRACT_BLOCKS[block]
    user = (
        f"Extract the {label} from the Document below.\n\n{body}\n\n"
        f"{_EXTRACT_RULES}\n\n"
        + (f"ALREADY EXTRACTED (for context only — do not repeat or contradict):\n{context}\n\n"
           if context else "")
        + f"DOCUMENT\n{document}\n\n"
        f"OUTPUT JSON with one key per field listed above, plus \"doc_end_marker\"."
    )
    return EXTRACT_SYSTEM, user


# --- patents ----------------------------------------------------------------

PATENT_SYSTEM = (
    "You analyse patent documents for a prior-art landscape. You report only what the "
    "document says, quoting it. Output one JSON object and nothing else."
)

PATENT_USER = """Analyse this patent document for a project developing a humidity-responsive,
controlled-release 1-MCP packaging material, optionally with an essential-oil antimicrobial.

FIELDS — each is {{"value": ..., "unit": ..., "quote": ..., "where": ...}}
- title: the invention title as printed.
- priority_date: the priority date as printed (YYYY-MM-DD).
- publication_date: the publication date as printed (YYYY-MM-DD).
- assignee: the current or original assignee as printed.
- inventors: the inventors as printed.
- jurisdictions: patent-office country codes visible for this family (e.g. US, EP, CN, JP).
- family_members_seen: publication numbers of family members listed in the priority or
  related-applications section.
- independent_claim_gist: what independent claim 1 actually requires, in one or two sentences.
- packaging_format: film, coating, laminate, sachet, label, insert, fibre, powder...
- mcp_carrier: what holds the 1-MCP (alpha-cyclodextrin, inclusion complex, MOF...).
- release_trigger: humidity_moisture, liquid_water, temperature, ph, enzymatic, mechanical,
  passive_diffusion, other, not_stated.
- release_control: the mechanism the claims rely on to control release rate.
- antimicrobial_component: any essential oil or antimicrobial named.
- manufacturing_method: how the article is made, as claimed or described.
- claim_limitations: the narrowing limitations in claim 1 (ratios, thicknesses, sequences).
- overlap_with_concept: where this document would overlap the project described above.
- design_around: technical routes that would avoid claim 1's limitations.
- uncertainty: what you could not determine from this document.

RULES
1. `quote` MUST be copied EXACTLY from the Document. No quote means {{"value": "not stated"}}.
2. Describe what is CLAIMED, not what the background or field-of-invention section discusses.
   A patent's background often describes prior art it does not claim; do not attribute that
   to this patent.
3. For the last four fields you may reason, but your value MUST NOT contain a number absent
   from your quote or the Document.
4. Do not assess validity, infringement, or freedom to operate. Describe only.
5. Echo the marker at the very end of the Document in "doc_end_marker".

DOCUMENT
{document}

OUTPUT JSON with one key per field above, plus "doc_end_marker"."""

PATENT_SCREEN_SYSTEM = (
    "You triage patents for a prior-art landscape. Output one JSON object and nothing else."
)

PATENT_SCREEN_USER = """Is this patent relevant to a project developing a humidity-responsive,
controlled-release 1-MCP packaging material, optionally with an essential-oil antimicrobial,
for climacteric fruit?

Publication number: {pub_number}
Title: {title}
Assignee: {assignee}
Priority date: {priority_date}
Snippet: {snippet}

Relevant means it concerns any of: 1-MCP or cyclopropene delivery; cyclodextrin or other
encapsulation of volatile actives for packaging; humidity/moisture-triggered release;
controlled, delayed, differential or sequential release of a volatile in packaging;
essential-oil active packaging; or ethylene management in produce packaging.

RULES
1. Judge from the fields given. "maybe" is a legitimate answer when the snippet is thin.
2. Do not speculate about claim scope from the title alone.

OUTPUT JSON:
{{"decision": "include|exclude|maybe", "relevance": "core|adjacent|background|off_topic",
  "why": "<15 words or fewer>", "confidence": 0.0}}"""
