# 1-MCP evidence harvest

A retrieval-first pipeline that builds a source-verified evidence base for the
1-MCP humidity-responsive packaging report: literature (25 columns) and patent
families (19 columns), each cell traceable to a quote in a document we actually
fetched.

## The problem it solves

Ask any model for "40 papers with DOIs and their drying temperatures" and it
will produce a beautiful table of fabrications. This pipeline makes that
failure mode structurally impossible rather than merely discouraged:

1. **Identifiers never come from the model.** DOIs, years, journals, authors and
   patent numbers come from OpenAlex, Crossref, Europe PMC and Google Patents.
   The model is never given the opportunity to emit one.
2. **The model only ever sees retrieved text.** Extraction runs against a
   document already on disk, never against recall.
3. **Every value is re-checked against that text.** `grounding.py` verifies each
   asserted value independently. A value the model produced but the document
   does not contain is blanked and flagged; the row survives.

Red-team result on the grounding module: 10/10 true values grounded, 7/7
fabrications caught (wrong magnitude, number present in the wrong context,
number absent entirely, quote not in source, fabricated material, invented
number inside an appraisal).

## Two enums that carry the whole design

`evidence_level` answers *how good is our access?* and `status` answers *what
happened when we tried to ground this?*

The distinction that matters most is **`not_stated` vs `unverifiable`**:

| level | meaning |
|---|---|
| `full_text_verified` | quote located in retrieved full text |
| `abstract_only` | quote located in the abstract; full text never obtained |
| `metadata_only` | from API JSON (DOI, year, venue), not from prose |
| `not_stated` | we **hold the full text** and it does not report this — a positive finding |
| `unverifiable` | we could not obtain enough of the source to know |

Merging those last two would let "we couldn't read the paper" masquerade as
"the paper omits this", which is a fabricated claim about the literature. The
rule is enforced in `schema.resolve_missing()`, never left to the model.

## Stages

Each stage reads one artifact and writes another, and resumes from its own
output. Results are persisted as they land, so an interrupted run keeps
everything it finished.

```
queries → harvest → normalize → screen → acquire → extract → ground ┐
                                                                    ├→ verify → emit
pat-harvest → pat-normalize → pat-screen → pat-detail → pat-extract → pat-ground ┘
```

| artifact | contents |
|---|---|
| `01_hits_raw.jsonl` / `01_query_log.jsonl` | every raw hit; one log line per query with a typed result code |
| `02_works.jsonl` / `02_dropped.jsonl` | deduped works, and what the pre-filter removed and why |
| `03_screen.jsonl` | relevance decision, publication type, topical signals |
| `04_fulltext/` | open-access full text, one file per work |
| `05_extract.jsonl` | raw model output per extraction block |
| `06_lit_rows.jsonl` / `06_lit_cells.jsonl` | the 25-column table, and one row per cell with its quote |
| `15_pat_rows.jsonl` / `15_pat_cells.jsonl` | the 19-column patent table and its evidence |
| `20_verification.json` / `20_issues.csv` / `20_coverage.csv` | QA report, issue list, per-column evidence coverage |

## Usage

```bash
python3 scripts/run_harvest.py all                    # everything
python3 scripts/run_harvest.py all --limit 5          # smoke test
python3 scripts/run_harvest.py screen extract         # named stages
python3 scripts/run_harvest.py --cache-stats
python3 scripts/run_harvest.py acquire --pdf-drop ~/pdfs   # deepen with your own PDFs
```

Useful flags: `--llm-workers`, `--max-works` (cap the screening set),
`--n-originals` / `--n-reviews` (extraction budget), `--fast-extract`,
`--e2-passes`, `--fresh`, `--refresh`.

## Things learned the hard way

* **Google Patents soft-blocks by IP.** Six rapid probes were enough; four
  rounds of exponential backoff did not clear it. Discovery therefore runs
  through Tavily site-restricted search and full documents come from Tavily's
  extract endpoint, which reaches the same pages via its own crawler and returns
  ~400 k characters including complete claim text.
* **OpenAlex needs `title_and_abstract.search` with explicit AND/OR.** The bare
  `search=` parameter returned 2 000+ loosely related hits where the filtered
  form returned 61 on-topic ones.
* **Tavily's legacy `api_key`-in-body auth now returns HTTP 432.** Use the
  `Authorization: Bearer` header and rotate keys on `{401,402,403,429,432,433}`.
* **Crossref's bibliographic search returns filler for any query.** 435 of 1 570
  harvested records had no topical term at all. A free regex pre-filter removes
  them before any LLM time is spent.
* **Disable the reasoning pass for classification.** Screening took 6.7 s and
  640 completion tokens with reasoning, 0.6 s and 30 tokens without, for the
  same verdict. Extraction keeps reasoning on.
* **Verify the context window before trusting "not stated".** Ollama can serve a
  long-context model with a small window, silently truncating the document so
  every field comes back empty — and it grounds perfectly, because the model
  genuinely never saw the text. Every document call appends an end marker the
  model must echo; a mismatch raises instead of returning plausible emptiness.

## Open coverage gaps

* EPO OPS and PatentsView both require API keys we do not have, so patent data
  rests on Google Patents alone with no independent legal-status cross-check.
  Families are clustered heuristically (title + assignee + priority date);
  INPADOC family data was unavailable.
* Open-access coverage of this literature is thin — of the 25 most relevant
  papers, 4 were OA and 2 had a directly fetchable PDF. Process detail is
  usually absent from abstracts, so many cells are legitimately empty. Use
  `--pdf-drop` to deepen specific papers.
* No freedom-to-operate or patentability opinion is produced or implied.
