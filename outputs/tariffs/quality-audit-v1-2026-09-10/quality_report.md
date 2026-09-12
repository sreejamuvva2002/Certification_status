# Georgia EV tariff corpus: quality audit v1

Audit date: September 10, 2026. Original research date: September 9, 2026; original run completed September 10. Branch: `Tariffs-data`.

The 510-query run is complete as a collection run. It is a sector/regional research baseline, not a verified tariff-exposure register for every company. This audit preserves all original files and creates a separate revision. It made **zero additional Tavily calls and zero external document downloads**. Local Qwen and cached source text were used; current law was not independently rechecked.

## What was reviewed

The original corpus contains 10,217 extracted claims, 2,171 chunks, 910 source URL records, and 748 downloaded files. There are 664 full-document evidence records and 246 snippet fallbacks. Of 510 answers, 481 select evidence; 125 are marked insufficient (96 contain partial evidence and 29 select none). Completion therefore does not establish research sufficiency.

All 125 insufficient answers received local classification/recovery attempts. A seeded purposive sample of 30 claims (six per sector) was read directly against cached quotations and surrounding context, covering company/facility claims, authority documents, snippets, historical/proposed measures, and random selections. An additional eight conflict pairs spanning all sectors and fifteen insufficiency classifications were checked directly. This is an assistant review, not an independent human or legal review. The purposive sample does not support a corpus-wide error-rate estimate.

## Causes of insufficient evidence

| cause | primary | primary_or_contributing |
| --- | --- | --- |
| missing_sources | 4 | 4 |
| weak_geographic_or_company_relevance | 58 | 64 |
| inaccessible_documents | 11 | 64 |
| conflicting_or_outdated_evidence | 52 | 84 |
| extraction_problems | 0 | 4 |

Primary causes sum to 125; the final column overlaps. Classification is local-model triage constrained by observed retrieval metrics, with the fifteen documented manual checks/overrides in [manual_cause_review.json](manual_cause_review.json). The requested weak relevance category also includes product/sector mismatch. “Conflicting or outdated” includes inability to establish current applicability; it does not mean a source was proven false. “Extraction problems” includes omitted synthesis evidence; zero selected claims alone is not proof of extraction failure.

The complete per-query explanations, original metrics, contributing causes, and remaining gaps are in [insufficiency_classification.csv](insufficiency_classification.csv). Four original searches returned no candidates. Other gaps involve broad national rules being offered for local company questions, inaccessible full text, dated/proposed measures, and missing product/origin specificity. No new search has been used to fill those gaps.

No case retains extraction problems as its primary cause after direct review of the two model assignments (q_105 and q_151): their available claims did not answer the requested product/program scope, so omitting them was not evidence of extraction failure. Four cases retain extraction/synthesis problems as a contributing signal. Separately, the field corrections below address confirmed extraction/interpretation problems across the sampled corpus.

## Cached recovery

The local FTS index contains 11,235 passages from previously downloaded full documents. For each insufficient answer, it retrieved up to eight passages with topic, geography, and named-company boosts, then asked local Qwen for up to four exact quotes. Every accepted quote was checked against its supplied passage, original chunk, and document relationship.

There are **356 accepted quoted passages across 112 queries**; 11 quotes exactly duplicate an already extracted quote for that query. These are additional evidence candidates, not necessarily new facts or adequate answers. The validator rejected 140 proposed quotations. Local review failures remaining: 0.

**All 125 insufficient flags remain in the revision.** Additional quotations alone do not verify current policy or company-specific applicability. Recovery claims remain explicitly marked as locally extracted, quote-validated, and not manually verified. The bounded retrieval did not exhaust every possible passage combination; no useful recovery means none was accepted under these settings.

## Coverage by sector

| Group | Queries | Any evidence | Full text | Authority | Topic/place term | Insufficient | Recovery |
| --- | --- | --- | --- | --- | --- | --- | --- |
| automotive_and_trade | 230 | 219 | 198 | 83 | 166 | 56 | 52 |
| metals | 79 | 77 | 76 | 35 | 65 | 14 | 11 |
| batteries_and_minerals | 136 | 125 | 106 | 39 | 113 | 37 | 35 |
| pcbs_and_electronics | 50 | 47 | 41 | 16 | 32 | 14 | 12 |
| displays | 37 | 34 | 27 | 13 | 23 | 14 | 12 |

Counts are queries, not documents. Sector assignments overlap, so sector totals exceed 510. `with_selected_evidence` means any original citation; `with_full_text_citation` means at least one selected full-document claim; `with_trade_authority_citation` means a selected claim from a publisher tagged as an official trade authority. These columns are separate tests: an official citation may still be a snippet or off topic. `with_topic_location_term` is an exact term/word-boundary proxy in selected quotations, not a semantic relevance determination. The displayed recovery counts are additional candidates and do not replace insufficiency flags.

The sample revealed off-topic evidence even in authority documents: a hypothetical pasta entry appeared in automotive evidence, face-mask directives and aircraft products appeared in PCB evidence, and general automobile tariff statements appeared in display evidence. Display-specific classification must distinguish monitors, signaling displays, and automotive modules by function and product details. Authority provenance alone is insufficient.

## Coverage by geography

| Group | Queries | Any evidence | Full text | Authority | Topic/place term | Insufficient | Recovery |
| --- | --- | --- | --- | --- | --- | --- | --- |
| national_international_context | 362 | 347 | 313 | 171 | not_applicable | 68 | 59 |
| southeast_georgia | 64 | 57 | 50 | 6 | 32 | 27 | 24 |
| statewide_georgia | 84 | 77 | 67 | 3 | 46 | 30 | 29 |

Geography groups are mutually exclusive query labels. Southeast Georgia term matches use named local places/region terms, excluding a bare “Georgia”; statewide matches require “Georgia.” These are location mentions, not proof of a facility’s tariff liability. National/international questions have no geographic-match test. Named-company fields are also only context indicators and may contain unreviewed extraction errors; their counts are available in [evidence_coverage.csv](evidence_coverage.csv).

A national tariff plus a Georgia factory address does not establish that factory’s imports, origin, HTS classification, entry date, content value, exemptions, or actual cost. For instance, the Covington recycling evidence describes operations in Georgia but does not establish Southeast Georgia exposure or tariff causation.

## Citation support and corrections

All 30 sampled quotations were found in their cached chunks after whitespace normalization. Nevertheless, 20 of those records needed field corrections. Additional conflict-context review produced six more corrected claim records: **26 total records with manual field corrections**. Supporting quotations remain unchanged. New field values require exact support in the original chunk; removals and before/after values are recorded in [claim_corrections.csv](claim_corrections.csv).

Examples, indexed in [manual_review.json](manual_review.json) and [manual_conflict_review.json](manual_conflict_review.json):

- S04: automobile and auto-part effective dates were collapsed into one date; the correction preserves the separately quoted conditions.
- S07: the country of one factory was attached to another factory’s city/state; the unsupported country assignment was removed.
- S10/S11/S28: a page-update date, capacity-forecast year, or unanchored “now” was treated as an effective date; these fields were cleared.
- S18: a flattened tariff-table row mixed the general rate with preferential treatment; the rate was cleared while the supported HTS code was retained.
- S19: national Hyundai investment/output/job figures were mixed with a single plant and tariff causation. The unsupported investment-effect field was cleared. Cached 500,000-unit Georgia plant reports and the broader 1.2-million-unit statement require dated scope reconciliation; neither figure is adopted as current verified capacity.
- S01/S05/S15/S30: manufacturing locations, export controls, marking law, or policy rationale were mislabeled as origin rules, import tariff programs, or measured production effects.
- MC01/MC07: Schedule B export codes were treated as import HTS codes, and a ruling signatory/CBP was treated as a company. A comparator product also inherited the subject ruling’s duty rate.

[unsupported_assertions.csv](unsupported_assertions.csv) lists 24 records with manually cleared unsupported or misclassified fields, including their old values and source links. Lexical quotation support and the applicability of a structured field are separate checks.

The broader deterministic screen flags **173 claim records after manual corrections** for review. Flags include non-company names in company fields, update/relative dates used as effective dates, counties in city fields, and unverified HTS jurisdiction. [screening_flags.csv](screening_flags.csv) contains candidates, not confirmed errors; these uncertain fields were not silently rewritten.

## Conflicts and unresolved questions

The original model supplied 753 unique claim pairs in conflict groups. Their revised triage is:

| classification | pairs |
| --- | --- |
| complementary_or_no_conflict | 420 |
| different_products_origins_or_programs | 139 |
| apparent_same_scope_conflict | 55 |
| different_dates_or_policy_stages | 137 |
| insufficient_scope | 2 |

These are provisional cached-evidence classifications. Eight pairs were directly reviewed; identical normalized quotes can also be cleared as textual contradictions mechanically. No pair is labeled as a verified resolution of current law. 0 remaining model label/reason inconsistencies require review. Raw prior model outputs are retained alongside the revised results.

The direct review found that duplicate CBP statements, an investigation date versus an imposition date, expiry “unless renewed” versus a later extension, and different graphite forms or LCD functions had been treated as conflicts. Those distinctions explain the text but still do not establish current legal applicability.

Unresolved high-risk issues include battery vendors reporting 57.4% and roughly 70–170% without aligned dates/HTS components, graphite AD and other tariff components being mistaken for a total duty, steel/aluminum content valuation and stacking rules, and current PCB exclusion eligibility/expiry. The apparent-same-scope and insufficient-scope rows in [conflict_review.csv](conflict_review.csv) form the verification queue. Preserve their product, origin, program, rate basis, date, and source links; do not average conflicting rates or select the newest-looking snippet.

## Sector terms and company research

Targeted terminology is maintained in [targeted_terms.json](../../../data/tariffs/targeted_terms.json) for automotive, metals, batteries/minerals, PCBs/electronics, and displays, plus tariff programs, origin rules, exclusions, HTS, and Georgia locations. The audit applies these terms to cached retrieval. It also prepares **125 deduplicated follow-up drafts** in [targeted_query_drafts.csv](targeted_query_drafts.csv), linked to the 125 original gaps. All are marked `not_executed`; original query text is unchanged.

Use both levels: retain the 510-query baseline for policy and sector context, then investigate individual companies only where a company-specific conclusion is needed. A company dossier needs named company/facility evidence, the actual product/material and origin, and a dated applicable policy. Drafts naming a company inherit that name from the original query; they do not assert a supply relationship or proven exposure. Subsequent searches should prioritize the unresolved primary-authority and product/origin gaps instead of repeating all 510 queries for every company.

## Versioned outputs and preservation

- [claims.v1.jsonl](claims.v1.jsonl) and [claims.v1.csv](claims.v1.csv): all 10,217 original claim IDs with supported field corrections, review metadata, and explicit paths back to original source text.
- [answers.v1.jsonl](answers.v1.jsonl): all 510 original source-quote answers, their statuses preserved, linked to corrections and recovery evidence.
- [recovery_claims.jsonl](recovery_claims.jsonl): separately identified cached recovery quotes with original document/chunk provenance.
- Classification, coverage, screening, conflict, and manual-review files linked above explain the limitations and every intervention.
- [preservation_check.json](preservation_check.json) verifies all original file hashes and the unchanged request ledger. [quality_summary.json](quality_summary.json) contains machine-readable counts.

The original output directory was not overwritten. The revised data is suitable for evidence navigation and prioritizing verification, with the recorded qualifications; it does not certify every extracted field or supply a current company-level duty calculation.
