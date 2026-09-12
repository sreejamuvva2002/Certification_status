# Tariff workflow execution status

## Company collection and reviewed update completed — September 12, 2026

All **193 companies** (205 preserved seed rows) received both planned searches.
The **406-query run** includes 20 shared policy searches and has zero processing
failures. Tavily reported **396 credits**; the budget ledger accounts for **406**,
within the approved 500-credit ceiling. The final local review made no Tavily calls.

The collection contains 412 source URLs, 556 chunks and 1,889 new claims. Local
Qwen reviewed 339 unique tariff candidates; direct cached-source review covered
39 company/evidence relationships. The reviewed profiles identify seven companies
with source-reported effects and 12 with responses/opinions. The remaining profiles
retain context or evidence gaps. **327 query answers remain insufficient evidence**;
current company/facility duty liabilities are not established.

All company/query mappings, source relationships, budget and preserved input hashes
validate. The original 510-query corpus and earlier revisions remain unchanged.
The baseline addendum also records five further conflict reviews and leaves two
scope gaps; it does not certify current law. The historical audit counts below
are superseded where addressed by this update.

See the [completion report](../outputs/tariffs/company-research-2026-09-10/review-v1-2026-09-12/completion_report.md),
[193 reviewed company pages](../outputs/tariffs/company-research-2026-09-10/review-v1-2026-09-12/index.md),
and [company summary CSV](../outputs/tariffs/company-research-2026-09-10/review-v1-2026-09-12/company_summary.reviewed.csv).

## Cached quality audit completed — September 10, 2026

The separate quality revision is complete at `outputs/tariffs/quality-audit-v1-2026-09-10`.
All 125 insufficient answers and all 753 original conflict pairs have review records,
with zero remaining local-review failures. This stage made no new Tavily calls or
external downloads. All 2,716 original files match the saved hashes, and the request
ledger remains 510 estimated / 506 provider-reported credits.

Primary insufficiency causes: 58 weak relevance, 52 conflicting/outdated evidence,
11 inaccessible documents, four missing sources, and zero primarily extraction
problems (four retain extraction/synthesis as a contributing signal). Cached Qwen
recovery yielded 356 quote-validated evidence candidates across 112 queries; all
125 insufficient flags remain until their unresolved scope/date/applicability gaps
are established. These candidates do not certify current law.

Direct review covered 30 stratified claims, eight conflict pairs and 15 cause
classifications. Twenty-six claim records received field corrections; 173 other
screening flags remain review candidates. Conflict triage leaves 55 apparent
same-scope conflicts and two pairs with insufficient scope, subject to verification.
The remaining pair labels identify complementary evidence or product/date differences.

The revision exports all 10,217 claims and 510 answers, with original source paths,
correction history, sector/geography coverage, unsupported assertions, and 125
unexecuted targeted follow-up drafts. All 46 tariff tests pass; all revised claim
quotes, nonnull field provenance and original source paths validate.
See [the quality report](../outputs/tariffs/quality-audit-v1-2026-09-10/quality_report.md)
and [the revised claims CSV](../outputs/tariffs/quality-audit-v1-2026-09-10/claims.v1.csv).
The original collection-run records below remain historical and unchanged.

## Full run completed — September 10, 2026

All **510 queries** finished processing at **02:28 UTC**, with **zero remaining processing failures**. The final provenance audit passed, and all **37 regression tests** pass.

Final outputs: **3,994 search candidates**, **910 retained source URLs**, **10,217 claims**, and **2,171 RAG chunks**. **481 answers** contain selected evidence; **125 answers** flag insufficient evidence, including 96 with partial support. Estimated/budget-accounted usage is **510 credits**; Tavily reported **506**, within the authorized **700-credit cap**.

The final report is `outputs/tariffs/pilot-2026-09-09/completion-report.md`; the live summary, full-bank execution record and active-process record now show completion. Targeted field-label and snippet concerns remain in `manual-review.json`; passing the structural audit does not establish current tariff applicability or facility exposure. The detailed notes below describe earlier checkpoints and are superseded by this completion record.

## Full 510-query run authorized and started — September 9, 2026

The user authorized finishing all remaining 460 queries after reviewing the proposed
700-credit cumulative cap. The full-bank run started at 15:15 UTC, reusing the existing
50-query pilot corpus and all prior paid requests. The 700 ceiling includes the 50
credits already spent, leaving at most 650 additional estimated credits. Baseline
remaining searches require 460 credits; paid extraction and query expansion remain off.

A detached supervisor records execution in `full-bank-execution.json`, writes each
pass to `full-bank-pass-N.log`, and runs the provenance audit after processing. It
allows at most three passes, with successful work cached and all request attempts
counting against the same 700-credit cap. `active-process.json` identifies its PID
and process start time. `pilot-completed-summary.json` preserves the pilot checkpoint.

The full run is in progress. Use the live `summary.json` and SQLite query states for
actual counts; the pilot results below are historical. No further permission is needed
to finish this authorized run within its approved cap.

## Full-bank recovery — September 9, 20:07 UTC

The initial full-bank pass reached 237 searched queries and 226 processed answers
by 19:58 UTC. Eleven queries had failed: two from malformed/overlong model output,
and nine from model HTTP errors/timeouts. Ollama logs showed CUDA illegal-memory
access crashes and a stalled model-loading queue. The existing service subsequently
recovered and resumed extraction without replacing the installed model or altering
other GPU workloads.

Recovery limits source-field values/excerpts to 300/600 characters and synthesis
to 20 selected claims with at most five bounded conflict groups. These changes
prevent the observed runaway output patterns; citation/field provenance validation
remains in place. All 34 regression tests pass. The latest checkpoint audit also
passes. This does not prove the underlying GPU issue is permanently resolved.

The worker was interrupted at its resumable checkpoint to load the fix, and restarted
at 20:07 UTC under the existing 700-credit authorization. Prior execution/audit
records are archived under `revisions/20260909T200710Z/`. Failed queries are retried
from cached searches before new queries continue; completed work remains cached.
Consult live `summary.json` and `full-bank-execution.json` for newer counts and status.

## Recovery validation — September 9, approximately 20:15 UTC

Seven of the eleven earlier failed queries recovered after the bounded-output fix;
usage remained 239 credits during those cached retries. A remaining PDF case repeatedly
returned incomplete JSON while copying table dot leaders. Model-input preprocessing
now removes long standalone dot leaders while preserving the original stored source
and chunk text, offsets and hashes. An isolated live test of that exact failing chunk
returned two claims validated against the original text, with zero Tavily requests.
The test artifacts are in `outputs/tariffs/q113-recovery-check/`.

All 35 regression tests pass. Recovery also skips intermediate exports for already
completed query batches, while retaining the required final export. The worker was
restarted at 20:10 UTC to apply that resume optimization; the preceding execution
is archived under `revisions/20260909T201012Z/`. The PDF preprocessing fix will be
loaded by the supervisor's next recovery pass, which retries failed work from cache.
The full 510-query run remains active under the approved 700-credit cap.

## Final two-query recovery — September 10

The automatic passes searched all 510 queries and processed 508 before stopping at
02:17 UTC. The two remaining failures were duplicate IDs in q_351 synthesis and a
repeated/omitted candidate in q_502 relevance assessment. Candidate responses now use
required object keys for all original IDs; validated repeated citations/conflict groups
are deduplicated. No unsupported citations or missing assessments are accepted.
All 37 regression tests pass. Recovery uses the existing cached Tavily responses and
retains the approved 700-credit cumulative cap.

At this checkpoint, Tavily reported 506 credits versus 510 reserved search attempts.
Queries q_349, q_398, q_433 and q_460 returned no results and each reported zero credits.
The conservative budget ledger retains all 510 reservations. This distinction is
preserved in the final usage report.

## September 9 pilot completed

Branch: `Tariffs-data`. Live corpus: `outputs/tariffs/pilot-2026-09-09/`.
All 510 original queries are loaded with no exact duplicates. The balanced pilot
selects 50 original IDs from `data/tariffs/pilot_query_ids.txt`, under a cumulative
100-credit ceiling. It covers regional automotive, metals, batteries/minerals,
PCBs, displays and official trade sources. The full bank has not been launched.

All 50 pilot queries completed at 14:49 UTC with zero remaining processing failures.
All 50 searches succeeded and Tavily reported 50 credits. Five local model output
failures were found in the first completed pass. Recovery uses task-specific JSON
schemas and cached searches/documents/extractions; it does not repeat paid searches.
All five processing failures were resolved without additional Tavily credits.
The installed extraction model is `qwen3.5:35b-a3b` (Q4_K_M), served locally by Ollama.
All 33 focused tests pass, including request schemas, citation validation, budget
limits, resume, key failover and stopping a usage-check batch after HTTP 429.

The live structural provenance audit passes. Semantic spot checks found issues
requiring review, recorded in `manual-review.json`: county text in city fields,
generic company identities, production-volume wording in a product field, and
facility labels based only on snippets. This corpus is source-reported evidence;
current tariff applicability and facility exposure remain unverified. Original
claims are preserved for review rather than silently rewritten.

## Final pilot results

| Measure | Result |
| --- | --- |
| Original queries loaded / exact duplicates | 510 / 0 |
| Queries searched / processed | 50 / 50 |
| Queries with selected evidence | 47 |
| Answers marked insufficient evidence | 17, including 14 with partial evidence |
| Retrieved / retained candidate relationships | 390 / 136 |
| Retained URLs / unique content hashes | 119 / 115 |
| Downloaded files / full-document evidence / snippet fallbacks | 100 / 90 / 29 |
| Retained claims / RAG chunks | 1,473 / 564 |
| Whole-claim rejection events / optional-field warnings | 815 / 836 |
| Remaining failed queries | 0 |
| Historical failure events | 35: 29 document retrieval/readability failures, 6 processing events |
| Estimated / provider-reported / budget-accounted credits | 50 / 50 / 50 |
| Configured pilot ceiling | 100 credits |
| Tests / final structural provenance audit | 33 passed / passed |

Downloaded files can be unreadable; therefore the downloaded count exceeds the
full-document evidence count. Rejection counts include historical attempts and
optional-field warnings, not only unique rejected claims. The audit checks stored
quotes, hashes, field support and citation paths, not semantic correctness or
current legal applicability.

The final artifacts include `findings.md`, `claims.csv`, `claims.jsonl`,
`chunks.jsonl`, `corpus.sqlite`, `summary.json`, `audit.json`, and the targeted
`manual-review.json`. All remain local under the live corpus directory. The branch
contains the new workflow, usage checker, auditor, tests, dependency list, original
query bank, balanced pilot selection, and documentation. `.env.example`, `.gitignore`
and README contain configuration/help changes. Existing unrelated edits, including
tracked bytecode changes, were preserved. No commit, push or merge was performed.

## Latest credit observations

All 17 supplied keys are in Git-ignored `.env` with permissions 0600. A scan of
Git-eligible files found no Tavily credentials. Key failover is configured; no live
failover was needed for this pilot.

At approximately 14:34 UTC on September 9, key 1 returned 950 credits remaining,
and keys 2–14 returned 1,000 each. Keys 15–17 were rate-limited. A later paced refresh at approximately 14:48 UTC reconfirmed keys 1–13 before
key 14 was rate-limited and the remaining checks were deferred. Its records are in
`outputs/tariffs/credit-check-recovered/`. Unknown balances are not zero.
See `outputs/tariffs/credit-check-final/last-successful-observation.md` and the latest
raw status in that directory. The initial complete 17-key check remains under
`outputs/tariffs/credit-check/`.

The 13,950 sum of the latest successful per-key readings is not a verified independent
pool total: Tavily's usage response provides no account identity. Key 1 alone has
sufficient observed balance for the remaining 460 basic searches before retries.
The full 510-query baseline costs 510 basic or 1,020 advanced search credits.
Paid extraction remains off. A proposed cumulative basic-search cap of 700 credits
would leave 190 credits of headroom above the baseline, counting the 50 already used.
This expanded cap has not been applied.

## Resume and proposed full-bank command

Resume only the authorized pilot:

```bash
PYTHONDONTWRITEBYTECODE=1 outputs/tariffs/runtime-venv/bin/python scripts/research_tariffs.py \
  --out outputs/tariffs/pilot-2026-09-09 \
  --query-ids-file data/tariffs/pilot_query_ids.txt \
  --max-queries 50 --max-credits 100 --retry-failed
```

After explicit authorization of the proposed 700-credit cumulative ceiling, run
all original queries while reusing the completed pilot:

```bash
PYTHONDONTWRITEBYTECODE=1 outputs/tariffs/runtime-venv/bin/python scripts/research_tariffs.py \
  --out outputs/tariffs/pilot-2026-09-09 \
  --max-queries 510 --max-credits 700 --retry-failed
```

The full-bank command above has not been executed. It permits at most 650 further
estimated credits and may stop early if failures consume the retry allowance.

## Historical execution notes

The following dated notes describe earlier checkpoints; the current pilot and
credit observations above supersede their environment and completion statuses.

## Credential and credit check — 2026-09-09

Saved 17 distinct Tavily keys in the Git-ignored `.env` with mode 0600.
All 17 authenticated against the official usage endpoint. Each returned zero
account plan usage and 1,000 account plan credits remaining. Seven keys reported
a 1,000 key-level cap; ten had no numeric key-level cap in the response.

The arithmetic sum across keys is 17,000 credits, but that is **not a verified
independent pool total**: the response supplies no account identifier, so some or
all keys may share their account's 1,000-credit balance. At least one key currently
has access to the 1,000-credit plan balance needed to cover 510 basic searches.

All 510 baseline queries need 510 basic-search credits or 1,020 advanced-search
credits before retries. Current paid extraction is off. Reserving for two transient
retries of every basic query would require 1,530 credits, plus failed-key reservations
if quota rotation occurs (up to 16 extra when moving through 17 keys to a working one).
The existing 50-query / 100-credit pilot ceiling was not changed, and no searches
were submitted by this credit check. Qwen model installation remains outstanding.

Credential-free per-key balances and the budget calculation are in
`outputs/tariffs/credit-check/report.md` and `summary.json`. The reusable checker is
`scripts/check_tavily_usage.py`.

## Key rotation update — 2026-09-09

Added automatic failover for exhausted/invalid Tavily keys, persistent key state,
shared Search/Extract selection, and a reset flag after quota replenishment.
Temporary rate limits preserve Retry-After deadlines. The cumulative run budget
still applies across every key. All 26 offline regression tests passed, including
quota switching, restart behavior, all-keys-exhausted handling, secret redaction,
shared budget enforcement and cooldown preservation. No live Tavily key was used.

## Environment update — 2026-09-09

Ollama 0.33.3 is now installed at `/home/sm11926/.local/bin/ollama`
and running on `http://127.0.0.1:11434`. The server detected all four NVIDIA
RTX A6000 GPUs. Installation used the [official Linux package](https://docs.ollama.com/linux)
under the user's `.local` directory; no system service was installed.

`ollama list` returned no installed models. No model weights were downloaded,
in accordance with the original research brief. The refreshed pilot preflight now
reports two blockers: a missing Tavily credential and no installed Qwen 35B model.
Searches and estimated credits remain zero. The server log is
`outputs/tariffs/ollama-server.log`. If the server is stopped or the machine restarts,
start it again with `ollama serve`.

The execution record below describes the initial September 8 run.

Execution date: 2026-09-08. Branch: `Tariffs-data`.

Implementation and offline validation are complete. **The live Tavily/Qwen crawl did not run:** preflight stopped before any paid request.

| Measure | Actual result |
| --- | --- |
| Queries loaded | 510 |
| Unique / exact duplicate queries | 510 / 0 |
| Default pilot ceiling | 50 queries / 100 estimated Tavily credits |
| Live queries searched / processed | 0 / 0 |
| Retrieved / retained / downloaded sources | 0 / 0 / 0 |
| Claims / RAG chunks / evidence-covered queries | 0 / 0 / 0 |
| Search/extraction failures | 0 attempts; two preflight blockers |
| Estimated credits / budget-accounted credits | 0 / 0 |
| Provider-reported usage | Not available; no provider request made |
| Verified model tag | None; installed models could not be queried |
| Requested model preference | `qwen3.5:35b-a3b`, subject to installed-tag verification |
| Tests | 20 passed; all offline with synthetic fixtures |
| Corpus structure/provenance audit | Passed for initialized empty corpus; no live citation accuracy claim |

## Exact blockers

- No TAVILY_API_KEY or TAVILY_API_KEYS in environment or selected .env file.
- Ollama /api/tags unreachable or invalid at http://localhost:11434: URLError.

No `ollama` executable or manifests were found at the checked standard user/system locations. No model was downloaded. Optional `openpyxl` and `pypdf` readers are not installed; they are not required for the supplied TXT inventory.

## Files added or updated

- `scripts/research_tariffs.py`: standalone retrieval, extraction, budget ledger, exports and resume.
- `scripts/audit_tariff_corpus.py`: read-only provenance checks.
- `tests/test_research_tariffs.py`: 20 regression tests, including simulated full execution and resume.
- `data/tariffs/queries.txt`: unchanged copy of all 510 supplied numbered queries.
- `docs/tariff_research_brief.md`: unchanged copy of the supplied implementation requirements.
- `docs/tariff_workflow.md`: configuration, evidence limitations, verified Tavily documentation and execution commands.
- `docs/tariff_run_status.md`: this execution record.
- `requirements-tariffs.txt`: optional XLSX and PDF readers.
- `.env.example`, `.gitignore`, `README.md`: tariff configuration/help and generated-bytecode ignore rule.

The existing GNEM scripts and data remain unchanged. Changes are local and uncommitted; no push or merge was performed.

## Outputs and continuation

- `outputs/tariffs/dry-run/`: complete normalized inventory, initialized SQLite store and no-cost dry-run summaries.
- `outputs/tariffs/pilot/`: normalized inventory, SQLite store, configuration, preflight blockers, empty evidence exports, findings statuses, `summary.json` and `audit.json`.

After configuring Tavily credentials through the environment or an ignored `.env`, and making the installed Qwen 35B Ollama server available:

```bash
python3 scripts/research_tariffs.py --out outputs/tariffs/pilot
```

For another existing local configuration, append `--env-file /path/to/config.env`; for another local/LAN Ollama server append `--ollama-url http://HOST:11434`. Endpoint/model changes are allowed before the first live request. The original research date stays 2026-09-08 when resuming; use a new output directory for a newly dated research run.

To explicitly extend this run to all 510 queries with a cumulative credit ceiling covering basic searches and up to two retries per query, after accepting that budget:

```bash
python3 scripts/research_tariffs.py --out outputs/tariffs/pilot \
  --max-queries 510 --max-credits 1530 --retry-failed
```

That full-bank command was not executed. Paid extraction remains off. See [the workflow documentation](tariff_workflow.md) for output schemas, limitations and other settings.
