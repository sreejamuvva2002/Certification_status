# Company tariff research — completion and quality report

All **193 distinct company names** in the supplied workbook have completed two web searches and a reviewed evidence profile. All **205 populated seed rows** are preserved, including duplicates and separate facility/location information. The collection finished September 11, 2026 at 01:33 UTC; the final cached quality review was performed September 12.

The work contains **386 company searches plus 20 shared policy searches: 406 total, zero failed queries**. Tavily usage is **406 estimated credits / 396 provider-reported credits**, below the user-approved cumulative cap of **500**. The final quality review made no additional Tavily calls. Paid extraction was disabled; local Qwen `qwen3.5:35b-a3b` handled extraction and review.

The original query answers mark **327 of 406 queries as insufficient evidence** and 79 as complete. These flags remain unchanged; even complete answers are source-grounded research outputs, not verified current duty calculations.

## Company findings

| Evidence status | Companies |
| --- | --- |
| company context only | 71 |
| group context only | 19 |
| company tariff response or opinion | 12 |
| no usable company evidence | 83 |
| source reported company tariff effect | 7 |
| unverified tariff leads only | 1 |

**19 companies have retained source-reported tariff effects or attributed responses/opinions after this review.** Other profiles retain operating context, potential group links, unverified leads, or explicit gaps. These categories describe collected evidence; they do not establish zero exposure for a company with no usable evidence. Every profile includes the original seed locations, completed-query count, citations, evidence limitations, and remaining verification questions.

A source-reported effect can be a dispute, market movement, cost statement or other attributed observation. A response/opinion can be a petition, forecast, announced mitigation strategy or executive view. Neither certifies current legal liability or a particular Georgia facility’s imports. Parent/group evidence is kept separate from company-name matches, and company-name matching itself does not verify legal-entity identity.

[Browse all 193 reviewed profiles](index.md), [compare companies in CSV](company_summary.reviewed.csv), or [download the full reviewed evidence table](company_evidence.reviewed.csv).

## Collection and provenance

| Output | Count |
| --- | --- |
| Completed company queries | 386 |
| Completed shared policy queries | 20 |
| Search-result candidates | 3082 |
| Retained query/source relationships | 522 |
| Retained source URLs | 412 |
| Full-document evidence sources | 287 |
| Snippet fallback sources | 125 |
| Newly collected claims | 1,889 |
| Newly collected chunks | 556 |
| Company/evidence relationships, including cached baseline and group context | 1408 |
| Unique tariff candidates reviewed locally | 339 |
| Company candidates directly reviewed against cached context | 39 |
| Rejected wrong-company relationships | 3 |

Relationship and claim counts are not counts of independent facts: duplicate passages and source reposts remain linked to their original records.

The source collection is preserved in [web-run](../web-run). Documents, chunk offsets/hashes, quotations, field excerpts and answer citations passed the [structural audit](structural_audit.json). The final [validation record](validation.json) confirms all company/query mappings, source paths, quoted evidence relationships, budget and preserved inputs. Structural validation proves stored provenance, not correct tariff interpretation.

Extraction retained at most three sources per query and ranked up to six chunks per retained document for processing. **26 retained query/source links hit the chunk limit**; their original full text remains available. Query and source retention, inaccessible pages, sparse names and noisy seed labels limit recall. Snippets can omit qualifications. The search completion count is not a guarantee that every relevant source was found.

## Targeted terms and sector coverage

The query bank applies automotive/vehicles/auto-parts terms; steel/aluminum/copper; batteries/critical minerals/lithium/graphite; PCB/printed-circuit/electronics; and LCD/OLED/display-module terms, alongside import duties, Section 232/301, HTS, Chapter 99, origin, exclusions and stacking. Twenty shared searches restrict discovery to CBP, Federal Register, USTR, USITC and Commerce domains. All five sectors received four policy searches each. 19 of the 20 policy answers select retained evidence; all retain current-law qualifications.

| Sector | Companies with unverified sector hint | Companies with tariff assertion and sector term |
| --- | --- | --- |
| automotive and trade | 176 | 4 |
| metals | 29 | 5 |
| batteries and minerals | 7 | 4 |
| pcbs and electronics | 16 | 1 |
| displays | 16 | 0 |

Sector hints are unverified and overlap; counts must not be summed into a unique-company total. The final column is a word-boundary term match within retained company tariff assertions, not a comprehensive sector classification. The seed workbook contains inconsistent product/role/location labels, including 67 rows flagged by the local location check. Those fields were not silently corrected or used as proof of company activity. Weak display/PCB company evidence remains visible as a gap despite completed searches.

Shared policy material is in [shared_policy_evidence.csv](shared_policy_evidence.csv). A national rule is never attached as proven company exposure merely because the company makes a broadly similar product.

## Direct quality-review findings

The review inspected one candidate and its surrounding cached text for each of the 28 initially identified company-name tariff matches. The follow-up inspected all 11 remaining direct-company relationships classified as effects, bringing direct review to 39 relationships. This is a purposive sample, not a population error-rate estimate. [Manual review decisions](manual_company_review.json) distinguish measured/source-reported effects from opinions, proposals, operating context and mistaken identities.

Examples:

- **Novelis:** a company filing reports a disputed CBP assessment of Brazilian aluminum shipments; nearby text describes a cash deposit. Preserve the dispute and deposit status rather than treating it as final expense or assigning it to a Georgia facility.
- **Kia Georgia:** a historical ruling names the applicant and specific Chinese battery pouch cells. This supports a product/applicant relationship, not current import volume or automatic application of the old classification to every battery.
- **JAC Products:** reporting describes a Michigan supplier dispute over tariff payment. It is a reported contractual allegation, not proof of a Georgia plant effect.
- **Club Car, Textron and Bonnell:** petitions and responses to preliminary trade-remedy actions support company positions; requested/preliminary rates are not final current duties.
- **Hyundai Transys:** a purchasing job description mentions tariff and origin work; that establishes a compliance role, not a duty amount.
- **Morgan Corp.:** Morgan Motor USA sports-car dealer pages were rejected as unestablished links to the seed entity.
- **Ascend Elements:** a grant-cancellation passage was removed from tariff evidence. A Goodyear sector-analysis passage remains an unverified lead because its broad country rates do not establish actual company costs.
- **Goodyear and TCI:** a C-TPAT statement and a coatings-brand description do not establish a tariff effect. **TE Connectivity:** an automated agent-result page remains an unverified lead.

Tariff dates are anchored to the source/research context. Earlier 2025/2026 measures are historical at this review date. Relative “today,” forecasts and company opinions are not upgraded to verified current policy. The manual cases and local-model decisions are saved alongside their exact claim and company IDs.

## Remaining baseline cleanup

The separate cached v2 review covered all **173 flagged claim records** and **57 remaining conflict pairs**. It cleared 165 field assignments, quarantined seven pending verification, and retained one. Nine proposed retains were checked directly; eight required correction. Original values and reasons remain in [v2 field history](../../quality-audit-v2-2026-09-10/field_review.csv).

Five additional direct conflict-context checks are recorded in [baseline_conflict_addendum.json](baseline_conflict_addendum.json), without overwriting v2. After the addendum, the 753 baseline pairs are classified as 432 complementary/no textual conflict, 166 different products/origins/programs, 153 different dates/stages and 2 with insufficient scope. These are explanations of cached text, not verified resolutions of current law.

The two scope gaps concern incomparable battery-rate figures and an undated PCB-rate table versus a dated historical rate. The apparent aluminum-foil code discrepancy concerns different countries, proceedings and dates; both sources say written scope controls. No rate is averaged or chosen solely because it appears newer.

## What remains unknown

All 193 companies were researched within the approved plan. Evidence remains insufficient to calculate current company/facility duty liabilities. A usable calculation needs the actual imported product, origin, HTS classification, entry date, value/content basis, exclusions and applicable stacking rules. Many sources describe group strategy or benefits from duties on competitors, which differ from duties the company itself pays.

The original 510-query baseline, v1/v2 outputs, completed company collection and initial profiles are preserved. This reviewed update is separate. No unused credit headroom was spent automatically. The next focused work should pursue primary company/customs evidence for specific business questions in the gap profiles rather than treating a complete search count as complete exposure verification.
