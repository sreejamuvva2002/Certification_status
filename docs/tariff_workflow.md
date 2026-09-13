# Georgia EV tariff evidence workflow

This is an independent entry point on branch `Tariffs-data`. It does not change the
GNEM certification or location pipelines. The original research requirements are in
[tariff_research_brief.md](tariff_research_brief.md), and the original numbered bank is
[data/tariffs/queries.txt](../data/tariffs/queries.txt): **510 inputs, 510 unique queries,
0 exact duplicates** after case/whitespace normalization. Similar queries are retained.

## Run or resume

Python 3.10+ is required. TXT, Markdown lists, CSV, HTTP retrieval, Ollama calls and
SQLite use the standard library. For XLSX, readable PDFs, and article-text extraction, install the reader dependencies:

```bash
python3 -m pip install -r requirements-tariffs.txt
```

Set `TAVILY_API_KEY` or comma-separated `TAVILY_API_KEYS` in the environment or the
repository's ignored `.env`. An alternative file can be selected with `--env-file`.
Do not put credentials in commands, query files, or tracked configuration. `.env`
loading supports literal assignments and quoted values, without shell expansion.

Ollama endpoint precedence is `--ollama-url`, `OLLAMA_HOST`, `LLM_BASE_URL`, then
`http://localhost:11434`. A trailing `/v1` is removed for native Ollama API calls.
Only local/private network endpoints are accepted. `/api/tags` must confirm an
installed Qwen 35B tag. The preferred tag is `qwen3.5:35b-a3b`; otherwise one uniquely
matching installed Qwen 35B tag can be selected. Use `--model` to resolve ambiguity.
No model is downloaded and no smaller or remote paid model is substituted.
`TARIFF_MODEL` or `LLM_MODEL` is reused only when it specifies Qwen 35B.

```bash
# Offline inventory and output initialization; makes no search/model requests.
python3 scripts/research_tariffs.py --dry-run --out outputs/tariffs/dry-run

# Default pilot: first 50 original queries, cumulative 100 estimated-credit ceiling.
# Re-run this exact command to resume cached successful work.
python3 scripts/research_tariffs.py --out outputs/tariffs/pilot

# Resume failed operations too, after correcting their cause.
python3 scripts/research_tariffs.py --out outputs/tariffs/pilot --retry-failed

# On a configured LAN Ollama server, before any live requests have been made:
python3 scripts/research_tariffs.py --out outputs/tariffs/pilot \
  --ollama-url http://OLLAMA_HOST:11434 --model qwen3.5:35b-a3b

# Explicitly authorize extending the SAME run to the entire 510-query baseline.
# 510 basic searches + up to two attempts per failed search = at most 1530 credits.
# Existing reservations count toward this total. Paid extract stays OFF.
python3 scripts/research_tariffs.py --out outputs/tariffs/pilot \
  --max-queries 510 --max-credits 1530 --retry-failed

# Verify persisted evidence and answer citation paths, without network calls.
python3 scripts/audit_tariff_corpus.py outputs/tariffs/pilot
```

The full-bank command is documented for explicit authorization; it was **not run**.
More than 50 queries requires an explicit credit ceiling covering at least the baseline
searches. Retry and extraction headroom should be added. A cumulative cap can still
stop the run before completion. `--max-queries` is a cumulative ceiling, not a fresh allowance on each resume.
By default it selects a bank prefix. `--query-ids-file` instead selects original IDs
in file order, rejects duplicate/unknown IDs, and must include every query already
attempted in the same run. Original duplicate query text is not silently skipped.

The September 9 pilot uses `data/tariffs/pilot_query_ids.txt`: 50 original queries
covering regional automotive, metals, batteries/minerals, PCBs, displays and official
trade sources. Resume this pilot with:

```bash
PYTHONDONTWRITEBYTECODE=1 outputs/tariffs/runtime-venv/bin/python scripts/research_tariffs.py \
  --out outputs/tariffs/pilot-2026-09-09 \
  --query-ids-file data/tariffs/pilot_query_ids.txt \
  --max-queries 50 --max-credits 100 --retry-failed
```

Append `--export-only` for an offline metadata/export refresh. When explicitly
authorizing the full bank, omit `--query-ids-file` and set both `--max-queries 510`
and the chosen cumulative `--max-credits`; cached pilot searches remain reusable.

`--search-depth basic|advanced`, `--max-results 1..20`, `--concurrency 1..8`,
`--keep-per-query`, `--min-relevance`, `--paid-extract off|basic|advanced`, timeouts,
retry bounds and generation/chunk limits are configurable. Query expansion is disabled
and no generated follow-up query is submitted. Searches run in bounded batches;
Qwen and document processing are sequential. Defaults retain up to three candidates
per query and use basic searches with eight results.

## Multiple Tavily keys and automatic switching

Set a comma-separated list in the ignored `.env` file:

```dotenv
TAVILY_API_KEYS=your_first_key,your_second_key,your_third_key
```

`TAVILY_API_KEYS` takes precedence over `TAVILY_API_KEY`; duplicate entries are
removed. The workflow uses the first available key and keeps using it until a
quota/payment refusal (HTTP 402, 432, 433) or invalid credential (401). It then
retries the same operation with the next available key. Ordinary 400/403 errors
remain terminal. Search and optional Extract use the same pool.

The working key and unavailable-key states persist across queries and restarts.
Only hashed key identifiers are recorded in `tavily_key_state.jsonl`,
`request_keys.jsonl` and `key_rotation_events.jsonl`; raw keys are never written
to those files. In-flight requests can still finish after another worker marks
a key unavailable. Every outgoing attempt reserves credits against the same
run-wide ceiling, including failed attempts and failovers. Key switching does
not increase that ceiling. The 1530-credit example above covers baseline searches
and transient retries; quota failovers can require additional headroom, or the
run will stop at that same ceiling.

HTTP 429 preserves the provider's Retry-After deadline for both the operation
and key. Other workers skip a cooling key. When all keys are exhausted the run
saves its checkpoint and stops. If all usable keys are cooling, affected queries
are resumable failures without additional outgoing requests.

After replenishing a quota or correcting credentials, explicitly re-enable keys:

```bash
python3 scripts/research_tariffs.py --out outputs/tariffs/pilot \
  --reset-tavily-keys --retry-failed
```

This clears exhausted/invalid marks for configured keys, preserves active
Retry-After deadlines and leaves the accumulated credit ledger intact. Newly
added keys are automatically eligible without a reset. Completed queries stay cached.

Tavily exposes separate key and account limits through its
[usage endpoint](https://docs.tavily.com/documentation/api-reference/endpoint/usage).
Switching keys does not remove account-level limits; the next key must have
available quota. See the official [rate-limit guidance](https://docs.tavily.com/documentation/rate-limits)
for Retry-After behavior. Rotation was tested offline with simulated provider responses. The live pilot
used the first configured key; no live quota failover was needed.

## Checking current balances

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/check_tavily_usage.py
```

This reads each configured key through Tavily's `/usage` endpoint and writes
`outputs/tariffs/credit-check/keys.json`, `summary.json` and `report.md` with key
numbers/hashes, balances and credit estimates. It sends no search requests and
never writes API keys into its reports. A failed or rate-limited usage check is
recorded as unknown, not zero balance. The endpoint does not expose account IDs,
so adding per-key balances is not proof of an independent pooled credit total.

## Integration and pricing verification

The existing equivalent of the requested historical automation is
`scripts/check_certifications.py:TavilyBackend`. It uses Tavily's HTTP API directly;
there is no installed Tavily SDK or `tavily_ev_automation.answer_50_queries` in this
checkout. The new workflow reuses its endpoint, HTTP request identity and HTML reader.
The HTML reader falls back to the existing helper if Trafilatura is unavailable; the live pilot uses Trafilatura to remove navigation. It uses native Ollama instead of changing `llm_client.py`, to record generation limits,
structured JSON mode and the installed model identity.

Official documentation checked on **2026-09-08**:

- [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search):
  basic search costs one credit; advanced costs two. Search accepts at most 20 results.
  This implementation sets `auto_parameters=false` and requests `include_usage=true`.
  `include_answer` defaults to false; when enabled, its result is stored separately.
- [Tavily Extract API](https://docs.tavily.com/documentation/api-reference/endpoint/extract):
  basic extraction bills one credit per five successful URLs, advanced bills two.
  Reported extraction usage can be zero before a five-URL billing threshold is reached.
- [Credits and pricing](https://docs.tavily.com/documentation/api-credits): failed URL
  extractions are not billed. The local estimate intentionally retains conservative
  reservations for unsuccessful/unknown attempts instead of assuming a refund.

Every search attempt reserves one/two credits **before** its network request. Optional
extract requests reserve one/two credits per single URL, a conservative whole-block
ceiling rather than a fractional estimate. Usage has separate estimated, provider
reported and budget-accounted totals. Missing provider usage is null, never a claimed
zero. Budget accounting uses the larger of each reservation and reported charge.
The ledger includes attempts whose responses were lost or whose process was interrupted.
Cached successes do not consume credits again. Do not delete the SQLite ledger to resume.

## Evidence and outputs

All run artifacts are under `outputs/tariffs/<run>/`, already ignored by Git:

| Artifact | Purpose |
| --- | --- |
| `queries.jsonl`, `queries.csv`, `input_summary.json` | Original text and IDs, labels, duplicates, input rows |
| `raw_tavily/*.json` | Credential-free parameters and raw response for every request attempt |
| `tavily_answers.jsonl` | Provider answer, kept separate from local Qwen output |
| `candidates.jsonl`, `candidates.csv`, `query_sources.jsonl` | Every search candidate, score, rejection reason and query-source mapping |
| `documents/`, `text/`, `documents.jsonl` | Downloaded HTML/PDF, readable text, failures, timestamps and hashes |
| `chunks.jsonl` | RAG-ready overlapping chunks, character offsets, query IDs and all source aliases |
| `claims.jsonl`, `claims.csv`, `rejected_claims.jsonl` | Atomic evidence, grounded fields, quotes, facilities, dates and provenance |
| `answers/*.json`, `answers.jsonl` | Qwen-selected cited evidence and explicit limitations |
| `findings.md` | Findings grouped by sector and query geography, including unprocessed queries |
| `corpus.sqlite` | Authoritative records and transactional request/budget ledger |
| `config.json`, `preflight.json`, `summary.json` | Configuration, verified model metadata, blockers, coverage and usage |
| `query_state.jsonl`, `extractions.jsonl`, `failures.jsonl`, `cooldowns.jsonl` | Resume state, per-chunk completion, failures and Retry-After deadlines |

SQLite's `records(kind,id,body)` stores JSON objects keyed by type and stable ID;
`requests` stores all reservations and outcomes. Model requests/responses are in
`records` with `kind='model_calls'`, including Ollama token/timing metadata when supplied.
`chunks.jsonl` can be indexed by a RAG consumer without reconstructing provenance.

Canonical URLs remove fragments and tracking parameters but preserve meaningful
parameters, path case, and scheme. Identical content shares a text blob and canonical
chunk IDs; each source URL and each query relationship is preserved. A single run
retains one document snapshot per canonical URL. Use a new output directory to refresh
sources or change search settings, chunking, research date, or an already-used model.
A process lock prevents simultaneous runs against one directory. SQLite plus per-step
caching allow interruption recovery; successful extraction work survives query failures.

The direct fetcher rejects private/non-HTTP source URLs and private redirects, bounds
file size and timeouts, and falls back to Tavily extraction only when enabled. Otherwise
unreadable pages become explicitly labeled search-snippet evidence. PDF extraction needs
`pypdf`; scanned PDFs have no OCR support. Source pages are untrusted model input.

Qwen assesses candidate relevance. A domain-based credibility ranking prioritizes official
trade sources, then official regional/business sources, then disclosures; unfamiliar
publishers retain an explicit unverified-source label. This ranking is a heuristic,
not an independent authentication of every publisher.

Each claim has a verbatim excerpt and null unsupported fields. Populated fields require
an exact value and supporting excerpt in the cited chunk. Unsupported optional fields
are suppressed and audited individually; the grounded claim is retained. An unsupported
main excerpt still rejects the whole claim. Export wording alone does not establish
country of origin. Chunk extraction requests up to five relevant atomic claims with
concise excerpts to prevent generation truncation; complete chunks remain available
for RAG, and extraction records flag when that claim cap may have limited coverage. Qwen then selects claim IDs for
query answers; rendered factual statements are those verified excerpts, so free-form
model prose cannot introduce uncited facts. Conflicts reference both claims. Semantic
entailment and legal interpretation still require review; lexical validation alone does
not establish them. Queries without selected evidence are `insufficient_evidence`.

Geographic query labels are routing hints, not facility verification. A confirmed
Southeast Georgia facility requires source-supported company, facility, Georgia state,
and a qualifying city/county. Facility IDs include location, preserving separate plants.
The GNEM company seed sheet is not used as evidence and is not modified. Seed product,
EV relevance and supplier labels are therefore not presumed correct or validated by this run.

Policy wording, announcement/publication/effective/expiration dates, origin/export/destination,
HTS/Chapter 99 codes and stacking conditions are stored separately. Historical/future
measures remain evidence. Source-reported status does **not** become a verified current
legal status: `policy_status_as_of` remains `uncertain`, with current applicability flagged
for review. ISO effective dates receive a historical/future comparison against the run date;
other date wording is preserved without guessing. No combined duties are calculated.

## Validation and execution record

```bash
python3 -m unittest discover -s tests -v
```

Offline fixtures exercise parsing, budget concurrency, retries and cooldowns, document
hash deduplication, excerpt/field/citation rejection, model selection, full mocked flow,
and resume without new search charges. Mock fixtures are synthetic, confined to temporary
directories, and never written into the research corpus. See
[tariff_run_status.md](tariff_run_status.md) for this environment's actual execution results.

## Live refinement and evidence rebuild

The September 9 live smoke run identified navigation noise, unsupported optional
fields causing valid excerpts to be discarded, and overly long model responses.
Readable HTML now uses Trafilatura, optional fields are suppressed individually,
and chunk responses are bounded to five relevant claims. Original source files
and previous derived records remain available for audit.

To rebuild derived evidence after improving extraction, while retaining cached
Tavily searches and the cumulative credit ledger:

```bash
outputs/tariffs/runtime-venv/bin/python scripts/research_tariffs.py \
  --out outputs/tariffs/pilot-2026-09-09 --max-queries 50 --max-credits 100 \
  --query-ids-file data/tariffs/pilot_query_ids.txt \
  --rebuild-evidence --retry-failed
```

Use `--rebuild-evidence` only when intentionally regenerating derived data. It archives
records and answer files under `revisions/`, refreshes readable text from saved
HTML, and reprocesses claims and answers. It does not erase paid request history.
Ordinary continuation omits that flag. The live runtime's installed package
versions are recorded in `runtime-packages.txt` beside the run artifacts.

## Local model output constraints

Following the September 9 pilot, local Qwen requests now supply a task-specific JSON
schema through Ollama's `format` parameter. Extraction requires a claims array with
at most five entries; synthesis limits citations to supplied IDs and limitation codes
to the supported set. Existing verbatim quote and field-support checks still apply.
Historical invalid responses remain in the corpus, while retries reuse successful
searches, downloaded sources and completed extraction checkpoints. This follows
[Ollama structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs),
checked September 9, 2026.

The full-bank recovery additionally bounds field values/excerpts to 300/600 characters,
and synthesis to 20 selected claim IDs, with at most five conflict groups of two to
five distinct IDs. All extracted claims remain in the corpus; these limits constrain
model response size. Answers hitting the selection ceiling with additional claims
flag incomplete coverage.

Long standalone PDF dot leaders are removed from model input only, to avoid observed
repetition loops. Original stored text, chunks, offsets and hashes remain unchanged;
all extracted quotations are validated against those originals. Explicitly incomplete
Ollama responses are rejected. Completed query batches skip intermediate exports on
resume; a final export is always produced.

Candidate assessments use an object keyed by every original candidate ID, preventing
the model from repeating one candidate while omitting another. The validator also
accepts historical list-form assessments, with full coverage checks. Repeated valid
answer citations and identical conflict groups are normalized to one occurrence;
unknown citations and invalid source scores remain errors. Raw model responses are
preserved separately from normalized answers.

## Cached-only quality audit and targeted terms

The completed 510-query run is preserved in `outputs/tariffs/pilot-2026-09-09`.
Audit outputs and corrections go to the separate directory
`outputs/tariffs/quality-audit-v1-2026-09-10`; do not run `--rebuild-evidence` on
the original corpus for this audit.

```bash
outputs/tariffs/runtime-venv/bin/python scripts/audit_tariff_quality.py
outputs/tariffs/runtime-venv/bin/python scripts/finalize_tariff_quality_audit.py
```

The first command reads the original SQLite database in read-only mode, indexes
cached downloaded text, and calls only loopback Ollama. It does not load API keys,
instantiate Tavily, or download external documents. It resumes completed reviews.
The finalizer refuses to complete with missing/failed local reviews or changed
original hashes/request history. Direct assistant source reviews are recorded in
`manual_review.json`, `manual_corrections.json`, `additional_claim_corrections.json`,
`manual_cause_review.json`, and `manual_conflict_review.json`; these review inputs
must exist before finalization. They are audit judgments, not generated test fixtures.

The audit classifies the 125 original gaps and adds separately identified recovery
quotes. It does not automatically remove insufficient-evidence flags, certify
current tariff law, or turn a company/location mention into import exposure.
`claims.v1.jsonl` contains the original claim IDs and supported field corrections;
`answers.v1.jsonl` preserves source-quote statements/statuses and attaches audit
metadata. Consult `quality_report.md` and `quality_summary.json` before using them.

`data/tariffs/targeted_terms.json` supplies product/material and tariff terminology
for automotive, metals, batteries/critical minerals, PCBs/electronics, and displays.
The cached retrieval uses it; finalization builds a deduplicated
`targeted_query_drafts.csv` for unresolved queries. Drafts are **not executed**.
They retain all parent query IDs; the research runner accepts this CSV and carries
its parentage and expansion reason into query records for a future separate run.
Use a new output directory and an explicit search budget for any future crawl.
Company names in drafts come from original questions, not inferred supply links.
The original 510 queries remain the regional/sector baseline; company-specific
research requires facility/product/origin and dated policy evidence.
