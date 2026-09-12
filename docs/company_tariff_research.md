# Company tariff evidence workflow

The company research uses the populated records in `data/GNEM_Excel_Data.xlsx`:
205 seed rows representing 193 distinct names. Every seed row is retained; similar
names and parent/subsidiary entities are not automatically merged. Seed location,
product, industry and EV-role fields remain unverified discovery hints.

The authorized plan contains 406 searches: a general company search and a targeted
sector/tariff search for every company, plus four shared policy searches per each
of five sectors. The user approved a cumulative 500-credit ceiling on September 10,
2026. All stages share one SQLite request ledger. Basic searches, bounded retries,
local Qwen, and downloaded-document extraction are used; paid Tavily extraction
is disabled. Shared policy searches apply official-domain restrictions.

The targeted vocabulary is in `data/tariffs/targeted_terms.json`. It covers
vehicles/auto parts, steel/aluminum/copper, batteries/critical minerals, PCBs and
electronics, and LCD/OLED/display modules, alongside tariff programs, HTS,
origin, effective dates, exclusions, valuation and stacking. Product descriptions
alone never establish actual import origin, classification, or duty liability.

## Completed results

All 406 planned searches finished. Usage was 396 provider-reported credits and
406 budget-accounted credits against the approved 500-credit ceiling. The reviewed
update covers all 193 companies; 19 have source-reported tariff effects or responses,
while 327 query answers retain insufficient-evidence flags.

- [Completion and quality report](../outputs/tariffs/company-research-2026-09-10/review-v1-2026-09-12/completion_report.md)
- [Reviewed company profiles](../outputs/tariffs/company-research-2026-09-10/review-v1-2026-09-12/index.md)
- [Company comparison CSV](../outputs/tariffs/company-research-2026-09-10/review-v1-2026-09-12/company_summary.reviewed.csv)

## Entry points

- `scripts/research_company_tariffs.py`: prepares the roster, seed-quality flags,
  query bank and reviewable budget plan; preserves recorded budget approval.
- `scripts/cleanup_tariff_quality.py`: reviews prior flagged fields and conflict
  pairs using cached sources and local Qwen, saving a separate v2 revision.
- `scripts/run_company_tariff_research.py`: runs policy checks before company
  searches, enforces the approved cumulative ceiling, resumes completed searches,
  and periodically exports company profiles.
- `scripts/build_company_tariff_profiles.py`: builds initial company/evidence
  links and one page per company; group-name matching remains explicitly provisional.
- `scripts/finalize_company_tariff_research.py`: reviews unique tariff candidates
  against cached context, applies recorded direct-review decisions, validates the
  completed corpus, and exports a separate reviewed update and completion report.

The collection resides in `outputs/tariffs/company-research-2026-09-10/web-run`.
The reviewed update is in
`outputs/tariffs/company-research-2026-09-10/review-v1-2026-09-12`.
The original 510-query run, earlier quality revisions, completed company collection,
and initial company profiles remain unchanged.

To regenerate reviewed exports from completed review records without new web/model calls:

```bash
outputs/tariffs/runtime-venv/bin/python scripts/finalize_company_tariff_research.py --export-only
```

The manual review/addendum JSON files in that directory are required audit inputs,
not automatically generated judgments. The finalizer refuses missing candidate
reviews, incomplete company/query coverage, broken quote/source relationships or
changed input hashes. All new evidence uses the original stored claim/chunk IDs
and explicit source paths.

The company status distinguishes source-reported effects, attributed responses or
opinions, operating context, potential group context, unverified leads, and evidence
gaps. A completed search for every company does not guarantee a usable tariff
finding for every company. Current company/facility duty liability remains unverified
until actual products, origins, entry dates, classifications and policy conditions
are established. Extraction caps and inaccessible documents are recorded in the
completion report.
