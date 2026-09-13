# Completed tariff research run

Completed: 2026-09-10T02:28:33.421416+00:00. Research date: 2026-09-09. Branch: Tariffs-data.
Local model: qwen3.5:35b-a3b. All 510 original queries searched and processed; zero remaining processing failures.

| Output / measure | Final total |
| --- | --- |
| Query inputs / exact duplicates | 510 / 0 |
| Queries with selected evidence | 481 |
| Insufficient-evidence answers | 125 (96 contain partial evidence; 29 contain no selected evidence) |
| Retrieved candidates / retained query-source relationships | 3,994 / 1,375 |
| Retained source URLs / unique content hashes | 910 / 895 |
| Downloaded source files | 748 |
| Full-document evidence / snippet fallback sources | 664 / 246 |
| Retained claims / RAG chunks | 10,217 / 2,171 |
| Whole-claim rejection events / optional-field warnings | 3333 / 5660 |
| Historical failure events | 277 ({'document': 252, 'processing': 25}) |
| Remaining failed queries | 0 |
| Estimated / budget-accounted credits | 510 / 510 |
| Provider-reported credits | 506 |
| Authorized cumulative cap / unused budget headroom | 700 / 190 |
| Regression tests / provenance audit | 37 passed / passed |
| Claims flagged by targeted semantic review | 34 |

Four empty-result searches reported zero provider credits; all 510 attempts remain reserved in the conservative budget ledger. Paid extraction and query expansion were disabled. No further searches are queued.

The findings are source-reported evidence. Quote, field-support, content-hash and citation-path checks pass; this is not verification of current legal applicability or facility-specific exposure. `manual-review.json` preserves targeted field-label/snippet concerns. Historical failures and model responses remain auditable.

Main outputs: `findings.md`, `queries.csv`, `candidates.csv`, `query_sources.jsonl`, `documents.jsonl`, `documents/`, `text/`, `claims.csv`, `claims.jsonl`, `chunks.jsonl`, `answers.jsonl`, `answers/`, `corpus.sqlite`, `summary.json`, `audit.json`, `manual-review.json`, and `full-bank-execution.json`.

To audit again without network calls:

```bash
PYTHONDONTWRITEBYTECODE=1 outputs/tariffs/runtime-venv/bin/python scripts/audit_tariff_corpus.py outputs/tariffs/pilot-2026-09-09
```

To resume this completed run (successful work is cached):

```bash
PYTHONDONTWRITEBYTECODE=1 outputs/tariffs/runtime-venv/bin/python scripts/research_tariffs.py --out outputs/tariffs/pilot-2026-09-09 --max-queries 510 --max-credits 700 --retry-failed
```

Changes and data remain local; no commit, push or merge was performed. The existing GNEM pipeline and unrelated edits were preserved.
