# 3. Systematic-search methodology

## 3.1 Design principle: retrieval-first

The brief forbids fabricated references, values, and conclusions. A language
model asked to produce a 40-paper × 25-column table from memory will invent most
of it, so this review was built so that fabrication is structurally impossible
rather than merely discouraged:

1. **Identifiers never originate from a model.** DOIs, publication years,
   journal names, author lists and patent numbers come from OpenAlex, Crossref,
   Europe PMC and Google Patents. The extraction model is never given the
   opportunity to emit one.
2. **The model only ever reads retrieved text.** Extraction runs against a
   document already stored on disk — never against recall.
3. **Every asserted value is re-checked against that text.** An independent
   grounding step verifies each value; anything the document does not contain is
   blanked and flagged, and the row survives with reduced confidence.

The pipeline implementing this is in `scripts/harvest/` and is re-runnable.

## 3.2 Sources actually used

| Source | Role | Status |
|---|---|---|
| OpenAlex | primary discovery | used; `title_and_abstract.search` with explicit boolean operators |
| Crossref | reference strings, DOI verification | used |
| Europe PMC | discovery + open-access JATS full text | used |
| Unpaywall | open-access location lookup | used |
| Tavily | grey literature, commercial/regulatory pages, patent retrieval | used |
| Google Patents | patent discovery and full documents | used **indirectly** (see 3.6) |
| Semantic Scholar | citation enrichment | **not used** — rate-limited without a key; OpenAlex + Europe PMC + Crossref already covered this literature |
| Web of Science, Scopus, CAB Abstracts, AGRICOLA | — | **not accessible**; no subscription or API credentials available |
| EPO OPS, PatentsView | patent metadata cross-check | **not accessible**; both require API keys |

The brief lists Web of Science, Scopus, CAB Abstracts and AGRICOLA. None were
reachable from this environment. Their absence is a genuine coverage limitation:
CAB Abstracts and AGRICOLA in particular index horticultural and postharvest
literature — including conference and extension material — that OpenAlex and
Europe PMC cover unevenly. Any conclusion about the *absence* of prior work
should be read with that gap in mind.

## 3.3 Query grid

30 literature queries and 18 patent queries were run, built from the concept list
in the brief. The grid is in `scripts/harvest/queries.py` and each query is
tagged with a band so the coverage report can show which part of the question a
paper answers.

Bands span the core topic (1-MCP release, humidity triggering, cyclodextrin
carriers, packaging formats, measurement, produce validation, scale-up,
stability) and a deliberate **analogue band** that does not mention 1-MCP at all
— humidity-triggered release of any volatile active, CNC-stabilised Pickering
emulsion films, essential-oil packaging, roll-to-roll coating, and release
kinetics. A grid anchored only on 1-MCP would have missed the materials-science
half of the question.

Date range 2000–present, as specified.

## 3.4 Screening

Records were deduplicated on DOI, then on normalised-title overlap for records
without one.

A **deterministic pre-filter** ran before any model time was spent. Crossref's
bibliographic search returns loosely related work for any query: of 1 570 unique
harvested records, 278 contained no topical term whatsoever (3D bioprinting,
ischemic heart disease, urinary-tract infections) and 258 predated 2000. These
were removed by regular expression, not by judgement, and the dropped set is
recorded in `02_dropped.jsonl` for audit.

Remaining records were ranked by topical-anchor density and the top 700 screened
by the local model against the brief's inclusion and exclusion criteria, which
were embedded verbatim in the prompt so each decision is auditable against a
fixed text.

Two safeguards protect recall:

* An uninformative or missing abstract yields **"maybe"**, never "exclude" —
  absence of information is not evidence of irrelevance.
* Any record whose signals indicate 1-MCP **and** controlled release, humidity
  triggering, or a cyclodextrin carrier is forced into review even when the
  model voted to exclude.

## 3.5 Full-text acquisition and its limits

Full text was obtained **only where openly licensed** — Europe PMC JATS, then
open-access PDF via Unpaywall, then open-access landing pages. Paywalled papers
were left at abstract depth.

**Open-access coverage of this literature is thin.** Roughly a quarter of screened
papers yielded usable full text. This matters directly for the table: process
detail — drying temperature, 1-MCP loading, coat weight, package volume and
headspace — is usually reported in methods sections and almost never in
abstracts. Consequently many cells in the literature table are legitimately
empty, and the table distinguishes two different reasons:

* **not stated** — the full text is held and does not report the quantity.
* **unverifiable** — too little of the paper could be obtained to know.

These are never merged. Collapsing them would let "we could not read the paper"
masquerade as "the paper omits this", which would be a fabricated claim about the
literature. Per-column counts of each are in `tables/coverage.csv`.

A PDF ingest path (`--pdf-drop`) exists so specific papers can be upgraded to
full-text depth later without re-running the rest of the pipeline. This is the
single highest-leverage way to deepen the evidence base.

## 3.6 Patent retrieval

Google Patents' search endpoint **blocked this IP** after roughly six rapid
requests during method development and did not recover through four rounds of
exponential backoff. Patent discovery therefore ran through site-restricted web
search, and full patent documents — including complete claim text, priority and
family tables — were retrieved through Tavily's crawler, which reaches the same
pages independently.

Patent metadata (assignee, priority date, inventors) is extracted from the
retrieved document text and then grounded against it, so it is evidenced rather
than recalled. Publication numbers are taken deterministically from URLs.

Two limitations follow and are carried into the patent table:

* **Families are clustered heuristically** from title, assignee and priority
  date. INPADOC family data was unavailable, so family membership is
  *observed* — the members we saw — not authoritative.
* **Legal status is not reported.** Google Patents' own status field carries an
  explicit disclaimer that it is not a legal conclusion, and no independent
  source was reachable to verify it. A column of unverified statuses would
  invite exactly the misreading the brief warns against, so the table reports
  observed family members instead.

## 3.7 Grounding and verification

Each extracted value passes three deterministic checks before it may appear in a
table cell:

1. The model's supporting quote must be locatable in the retrieved document
   (exactly, or repaired by fuzzy match back to the exact source span, so what
   ships is always the source's own wording).
2. For numeric fields, the magnitude must match a quantity in the document after
   unit canonicalisation, so `2.1 mg g⁻¹` and `2.1 mg/g` compare equal.
3. The matched number must sit near a keyword for that field. Without this, any
   paper containing "40" would appear to confirm a drying temperature of 40 °C.

For appraisal columns the value may paraphrase, but it may not introduce a
number absent from the quote — that is where invented precision otherwise enters.

The grounding module was adversarially tested: **10/10 true values grounded, 7/7
fabrications caught** (wrong magnitude, correct number in the wrong context,
number absent entirely, quote not present in source, fabricated material,
invented number inside an appraisal).

A verification stage then re-resolves every DOI against Crossref, re-checks every
stored quote against its stored source independently of the extraction path,
detects duplicates, and reports per-column evidence coverage. Prose citations are
checked against the retrieved corpus, so the report cannot cite a source the
pipeline never fetched.

## 3.8 What this methodology cannot tell you

* It cannot establish that something has **never** been published. Four indexes
  named in the brief were inaccessible, and patent coverage rests on a single
  provider.
* It cannot assess **claim scope or validity**. The patent analysis is technical
  description only.
* Cells marked *unverifiable* are statements about our access, not about the
  paper.
