"""The literature stages: harvest, normalize, screen, acquire, extract, ground.

Each stage reads one artifact and writes another, and resumes by reading the id
set already in its own output. Workers fetch or call the model; the calling
thread does all the writing.
"""
from __future__ import annotations

import json
import os
import re
import time

from . import cache, fulltext, grounding, llmpool, prompts, queries, schema, sources, store

# Artifact names, in pipeline order.
A_QUERIES = "00_queries.jsonl"
A_HITS = "01_hits_raw.jsonl"
A_QLOG = "01_query_log.jsonl"
A_WORKS = "02_works.jsonl"
A_SCREEN = "03_screen.jsonl"
A_ACQUIRE = "04_acquire.jsonl"
A_FULLTEXT = "04_fulltext"
A_EXTRACT = "05_extract.jsonl"
A_ROWS = "06_lit_rows.jsonl"
A_CELLS = "06_lit_cells.jsonl"

MAX_DOC_CHARS = 400_000  # a latency choice, not a capacity limit (262k ctx verified)


def p(out_dir: str, name: str) -> str:
    return os.path.join(out_dir, name)


# --------------------------------------------------------------------------
# stage: queries
# --------------------------------------------------------------------------
def stage_queries(out_dir: str) -> int:
    qs = queries.all_queries()
    store.write_jsonl(p(out_dir, A_QUERIES), qs)
    lit = sum(1 for q in qs if q["kind"] == "work")
    print(f"  queries: {lit} literature + {len(qs) - lit} patent = {len(qs)}")
    return len(qs)


# --------------------------------------------------------------------------
# stage: harvest
# --------------------------------------------------------------------------
def stage_harvest(out_dir: str, srcs: dict, *, pages: int = 2, per_page: int = 100,
                  max_failure_rate: float = 0.30, health_after: int = 12) -> int:
    """Run the literature grid across every available scholarly source."""
    qs = [q for q in store.read_jsonl(p(out_dir, A_QUERIES)) if q["kind"] == "work"]
    done = store.done_ids(p(out_dir, A_QLOG), "run_id")
    use = [s for s in ("openalex", "epmc", "crossref") if s in srcs]
    print(f"  sources: {', '.join(use)} | {len(qs)} queries x {pages} pages")

    n_new = 0
    ran = failed = 0
    for q in qs:
        for sname in use:
            run_id = f"{q['query_id']}:{sname}"
            if run_id in done:
                continue
            src = srcs[sname]
            cursor = None
            got = 0
            code = "empty"
            for _page in range(pages):
                res = src.search(q["query"], limit=per_page, cursor=cursor)
                code = res["code"]
                if not res["success"]:
                    break
                for rec in res["records"]:
                    rec["query_id"] = q["query_id"]
                    rec["band"] = q["band"]
                    store.append_jsonl(p(out_dir, A_HITS), rec)
                    got += 1
                    n_new += 1
                cursor = res.get("next_cursor")
                if not cursor:
                    break
            ran += 1
            failed += 1 if code in cache.FAILURE_CODES else 0
            store.append_jsonl(p(out_dir, A_QLOG), {
                "run_id": run_id, "query_id": q["query_id"], "source": sname,
                "band": q["band"], "query": q["query"], "code": code,
                "records": got, "at": time.time(),
            })
            print(f"    {run_id:<24} {code:<12} {got:>4} recs")

        # A dead endpoint must stop the run, not quietly yield a thin corpus.
        if ran >= health_after and failed / ran > max_failure_rate:
            raise RuntimeError(
                f"harvest aborted: {failed}/{ran} source calls failed "
                f"(>{max_failure_rate:.0%}). Fix connectivity before continuing; "
                f"the cache keeps everything already fetched.")
    print(f"  harvested {n_new} new hit rows ({ran} calls, {failed} failed)")
    return n_new


# --------------------------------------------------------------------------
# stage: normalize / dedupe
# --------------------------------------------------------------------------
_STOP = {"the", "of", "and", "for", "with", "in", "on", "a", "an", "to", "by", "from"}


def _title_key(title: str) -> frozenset:
    toks = re.findall(r"[a-z0-9]+", (title or "").lower())
    return frozenset(t for t in toks if t not in _STOP and len(t) > 2)


# Deterministic pre-filter. Crossref's bibliographic search returns loosely
# related work for any query — measured here, 435 of 1570 harvested records had
# no topical term at all (3D bioprinting, ischemic heart disease). Screening
# those with the LLM would cost hours and decide nothing. Anchor matching is
# free, so the model only ever sees plausible candidates.
#
# The filter is deliberately generous: ONE anchor is enough. It removes
# off-topic noise, not borderline papers — those are the screener's job.
_ANCHORS = [
    r"1-methylcyclopropene", r"\b1-?mcp\b", r"cyclopropene", r"cyclodextrin",
    r"pickering", r"cellulose nanocryst", r"nanocellulose", r"\bcnc\b", r"\bcnf\b",
    r"chitosan", r"thymol", r"carvacrol", r"eugenol", r"cinnamaldehyde",
    r"essential oil", r"active packaging", r"antimicrobial packag", r"edible coating",
    r"controlled release", r"sustained release", r"slow release", r"delayed release",
    r"volatile.{0,25}release", r"release.{0,25}volatile",
    r"ethylene", r"postharvest", r"post-harvest", r"climacteric", r"ripening",
    r"humidity", r"moisture.{0,20}(release|activat|trigger)",
    r"water vapou?r permeab", r"headspace", r"shelf life", r"shelf-life",
    r"food packaging", r"modified atmosphere", r"barrier film", r"biodegradable film",
]
_ANCHOR_RE = [re.compile(a, re.I) for a in _ANCHORS]
MIN_YEAR = 2000


def anchor_score(rec: dict) -> int:
    text = f"{rec.get('title') or ''} {rec.get('abstract') or ''}"
    return sum(1 for rx in _ANCHOR_RE if rx.search(text))


def _completeness(rec: dict) -> int:
    score = 0
    score += 3 if rec.get("doi") else 0
    score += 2 if rec.get("abstract") else 0
    score += 1 if rec.get("venue") else 0
    score += 1 if rec.get("authors") else 0
    score += 1 if rec.get("pdf_url") or rec.get("oa_url") else 0
    score += 1 if rec.get("pmcid") else 0
    return score


def _merge(a: dict, b: dict) -> dict:
    """Field-by-field union, preferring the more complete record."""
    lo, hi = sorted((a, b), key=_completeness)
    out = dict(hi)
    for k, v in lo.items():
        if not out.get(k) and v:
            out[k] = v
    out["sources"] = sorted({*(a.get("sources") or [a.get("source", "")]),
                             *(b.get("sources") or [b.get("source", "")])} - {""})
    out["bands"] = sorted({*(a.get("bands") or [a.get("band", "")]),
                           *(b.get("bands") or [b.get("band", "")])} - {""})
    return out


def stage_normalize(out_dir: str, *, max_works: int | None = 700) -> int:
    hits = store.read_jsonl(p(out_dir, A_HITS))
    by_doi: dict[str, dict] = {}
    no_doi: list[dict] = []
    for rec in hits:
        rec["sources"] = [rec.get("source", "")]
        rec["bands"] = [rec.get("band", "")]
        doi = rec.get("doi") or ""
        if doi:
            by_doi[doi] = _merge(by_doi[doi], rec) if doi in by_doi else rec
        else:
            no_doi.append(rec)

    # Fold DOI-less records into a DOI'd twin when the titles match closely.
    title_index: dict[frozenset, str] = {}
    for doi, rec in by_doi.items():
        key = _title_key(rec.get("title", ""))
        if len(key) >= 4:
            title_index[key] = doi

    orphans: list[dict] = []
    for rec in no_doi:
        key = _title_key(rec.get("title", ""))
        hit = None
        if len(key) >= 4:
            for other, doi in title_index.items():
                inter = len(key & other)
                union = len(key | other)
                if union and inter / union >= 0.85:
                    hit = doi
                    break
        if hit:
            by_doi[hit] = _merge(by_doi[hit], rec)
        else:
            orphans.append(rec)

    # Dedupe the remaining DOI-less records among themselves.
    merged_orphans: dict[frozenset, dict] = {}
    for rec in orphans:
        key = _title_key(rec.get("title", ""))
        merged_orphans[key] = _merge(merged_orphans[key], rec) if key in merged_orphans else rec

    works = list(by_doi.values()) + list(merged_orphans.values())
    for w in works:
        w["work_id"] = sources.work_id(w)
        w["anchor_score"] = anchor_score(w)
        w.pop("query_id", None)
        w.pop("band", None)
    n_unique = len(works)

    dropped_year = [w for w in works if (w.get("year") or 0) < MIN_YEAR]
    works = [w for w in works if (w.get("year") or 0) >= MIN_YEAR]
    dropped_topic = [w for w in works if w["anchor_score"] == 0]
    works = [w for w in works if w["anchor_score"] > 0]

    # Most relevant first, so a --limit run screens the best candidates.
    works.sort(key=lambda w: (-w["anchor_score"], -(w.get("year") or 0), w.get("title", "")))
    capped = 0
    if max_works and len(works) > max_works:
        capped = len(works) - max_works
        works = works[:max_works]

    store.write_jsonl(p(out_dir, A_WORKS), works)
    store.write_jsonl(p(out_dir, "02_dropped.jsonl"),
                      [{"work_id": w["work_id"], "title": w.get("title", ""),
                        "year": w.get("year"), "reason": reason}
                       for reason, group in (("pre_2000", dropped_year),
                                             ("no_topical_anchor", dropped_topic))
                       for w in group])
    print(f"  {len(hits)} hits -> {n_unique} unique "
          f"({len(by_doi)} with DOI, {len(merged_orphans)} without)")
    print(f"  pre-filter dropped {len(dropped_year)} pre-{MIN_YEAR}, "
          f"{len(dropped_topic)} with no topical anchor"
          + (f", capped {capped} beyond top {max_works}" if capped else ""))
    print(f"  -> {len(works)} works to screen")
    return len(works)


# --------------------------------------------------------------------------
# stage: screen
# --------------------------------------------------------------------------
# Signals that force a work into review regardless of the model's verdict. A
# recall net, in the spirit of the uncovered-candidate check in collect_locations.
FORCE_REVIEW = [("mentions_1mcp", "controlled_release"),
                ("mentions_1mcp", "humidity_or_moisture_trigger"),
                ("mentions_1mcp", "cyclodextrin_carrier")]


def stage_screen(out_dir: str, model: str, *, workers: int = 2, limit: int | None = None) -> int:
    works = store.read_jsonl(p(out_dir, A_WORKS))
    done = store.done_ids(p(out_dir, A_SCREEN), "work_id")
    todo = [w for w in works if w["work_id"] not in done]
    if limit:
        todo = todo[:limit]
    print(f"  screening {len(todo)} works ({len(done)} already done)")

    def screen_one(w: dict) -> dict:
        user = prompts.SCREEN_USER.format(
            criteria=prompts.SCREEN_CRITERIA,
            title=w.get("title", ""), year=w.get("year", ""),
            venue=w.get("venue", ""), type=w.get("type", ""),
            abstract=(w.get("abstract") or "[no abstract available]")[:6000],
        )
        try:
            data = llmpool.ask_json(prompts.SCREEN_SYSTEM, user, model=model, timeout=300,
                                    extra=llmpool.FAST)
        except Exception as e:
            return {"work_id": w["work_id"], "decision": "maybe", "pub_type": "other",
                    "signals": {}, "screen_error": str(e)[:200], "confidence": 0.0,
                    "primary_topic": "", "exclusion_reason": ""}
        signals = data.get("signals") or {}
        decision = schema.pick(data.get("decision"), schema.SCREEN_DECISIONS, "maybe")
        for combo in FORCE_REVIEW:
            if all(signals.get(s) for s in combo) and decision == "exclude":
                decision = "maybe"
                data["exclusion_reason"] = (
                    f"model said exclude but signals {combo} present; forced to review")
                break
        return {
            "work_id": w["work_id"], "decision": decision,
            "pub_type": schema.pick(data.get("pub_type"), schema.PUB_TYPES, "other"),
            "primary_topic": str(data.get("primary_topic") or "")[:120],
            "signals": signals,
            "exclusion_reason": str(data.get("exclusion_reason") or "")[:200],
            "confidence": data.get("confidence") or 0.0,
            "screen_error": "",
        }

    results = llmpool.map_concurrent(
        screen_one, todo, workers=workers, label="screen",
        sink=lambda r: store.append_jsonl(p(out_dir, A_SCREEN), r))
    counts: dict[str, int] = {}
    for r in store.read_jsonl(p(out_dir, A_SCREEN)):
        counts[r["decision"]] = counts.get(r["decision"], 0) + 1
    print(f"  screened: {counts}")
    return len(results)


# --------------------------------------------------------------------------
# stage: acquire full text
# --------------------------------------------------------------------------
def stage_acquire(out_dir: str, srcs: dict, *, drop_dir: str | None = None,
                  workers: int = 4, limit: int | None = None) -> int:
    works = {w["work_id"]: w for w in store.read_jsonl(p(out_dir, A_WORKS))}
    screened = store.read_jsonl(p(out_dir, A_SCREEN))
    wanted = [works[s["work_id"]] for s in screened
              if s["decision"] in ("include", "maybe") and s["work_id"] in works]
    done = store.done_ids(p(out_dir, A_ACQUIRE), "work_id")
    todo = [w for w in wanted if w["work_id"] not in done]
    if limit:
        todo = todo[:limit]
    ft_dir = p(out_dir, A_FULLTEXT)
    store.ensure_dir(ft_dir)
    print(f"  acquiring full text for {len(todo)} works ({len(done)} done)")

    epmc = srcs.get("epmc")
    unpaywall = srcs.get("unpaywall")
    tavily = srcs.get("tavily")

    def acquire_one(w: dict) -> dict:
        try:
            got = fulltext.acquire(w, epmc, unpaywall, tavily, drop_dir)
        except Exception as e:
            return {"work_id": w["work_id"], "fulltext_source": "", "fulltext_chars": 0,
                    "error": str(e)[:200]}
        if got["chars"]:
            slug = re.sub(r"[^\w.-]", "_", w["work_id"])[:120]
            with open(os.path.join(ft_dir, slug + ".txt"), "w", encoding="utf-8") as fh:
                fh.write(got["text"])
        return {"work_id": w["work_id"], "fulltext_source": got["source"],
                "fulltext_chars": got["chars"], "error": ""}

    results = llmpool.map_concurrent(
        acquire_one, todo, workers=workers, label="acquire",
        sink=lambda r: store.append_jsonl(p(out_dir, A_ACQUIRE), r))
    got = sum(1 for r in results
              if isinstance(r, dict) and r.get("fulltext_chars"))
    total = store.read_jsonl(p(out_dir, A_ACQUIRE))
    have = sum(1 for r in total if r.get("fulltext_chars"))
    print(f"  full text: {have}/{len(total)} works ({100.0 * have / max(1, len(total)):.0f}%)")
    return got


def read_fulltext(out_dir: str, work_id: str) -> str:
    slug = re.sub(r"[^\w.-]", "_", work_id)[:120]
    path = os.path.join(out_dir, A_FULLTEXT, slug + ".txt")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------
# stage: extract
# --------------------------------------------------------------------------
REVIEW_TYPES = {"review", "systematic_review", "meta_analysis"}


def select_for_extraction(works: dict, screened: dict, acquired: dict,
                          n_originals: int, n_reviews: int) -> list[dict]:
    """Pick the extraction set, balancing originals against reviews.

    The brief asks for 40 original papers and 15 reviews. Taking the top N
    overall would starve the review quota, since originals dominate the corpus,
    so the two are ranked and filled separately. Papers whose full text we hold
    outrank abstract-only ones: they are the only ones that can populate the
    process-detail columns.
    """
    def rank(w: dict) -> tuple:
        wid = w["work_id"]
        has_ft = 1 if acquired.get(wid, {}).get("fulltext_chars") else 0
        included = 1 if screened.get(wid, {}).get("decision") == "include" else 0
        return (-included, -has_ft, -w.get("anchor_score", 0), -(w.get("year") or 0))

    pool = [works[wid] for wid, s in screened.items()
            if s["decision"] in ("include", "maybe") and wid in works]
    originals = sorted(
        [w for w in pool if screened[w["work_id"]].get("pub_type") not in REVIEW_TYPES],
        key=rank)[:n_originals]
    reviews = sorted(
        [w for w in pool if screened[w["work_id"]].get("pub_type") in REVIEW_TYPES],
        key=rank)[:n_reviews]

    # Interleave rather than concatenate. Extraction is slow and resumable, so a
    # run that stops early is a normal outcome — and with originals first, an
    # interrupted run would yield zero reviews and miss the brief's 15-review
    # minimum despite having done most of the work. Interleaving keeps any
    # prefix of the list balanced.
    out: list[dict] = []
    o = r = 0
    while o < len(originals) or r < len(reviews):
        for _ in range(3):
            if o < len(originals):
                out.append(originals[o])
                o += 1
        if r < len(reviews):
            out.append(reviews[r])
            r += 1
    return out


def stage_extract(out_dir: str, model: str, *, workers: int = 2, limit: int | None = None,
                  e2_passes: int = 2, n_originals: int = 60, n_reviews: int = 22,
                  fast: bool = False) -> int:
    works = {w["work_id"]: w for w in store.read_jsonl(p(out_dir, A_WORKS))}
    screened = {s["work_id"]: s for s in store.read_jsonl(p(out_dir, A_SCREEN))}
    acquired = {a["work_id"]: a for a in store.read_jsonl(p(out_dir, A_ACQUIRE))}
    # Over-select against the 40/15 minimums: grounding will blank some rows to
    # near-empty, and a shortfall is far more expensive to fix than a surplus.
    targets = select_for_extraction(works, screened, acquired, n_originals, n_reviews)
    done = store.done_ids(p(out_dir, A_EXTRACT), "work_id")
    todo = [w for w in targets if w["work_id"] not in done]
    if limit:
        todo = todo[:limit]
    n_ft = sum(1 for w in todo if acquired.get(w["work_id"], {}).get("fulltext_chars"))
    print(f"  extracting {len(todo)} works ({len(done)} done), {e2_passes} pass(es) on E2, "
          f"{n_ft} with full text")

    def extract_one(w: dict) -> dict:
        wid = w["work_id"]
        ft = read_fulltext(out_dir, wid)
        evidence, level, has_ft = fulltext.evidence_for(w, ft)
        doc, canary = llmpool.with_canary(evidence[:MAX_DOC_CHARS])
        out: dict = {"work_id": wid, "level": level, "has_full_text": has_ft,
                     "fulltext_chars": acquired.get(wid, {}).get("fulltext_chars", 0),
                     "model": model, "extracted_at": time.time(), "blocks": {}, "errors": {}}
        context = ""
        for block in ("E1", "E2", "E3", "E4"):
            # The second release-block pass is a recall net for long documents,
            # where a value can sit in a table the first pass skimmed. On an
            # abstract there is nothing for it to find, so it only costs time.
            passes = e2_passes if (block == "E2" and has_ft) else 1
            merged: dict = {}
            for _ in range(passes):
                system, user = prompts.extract_prompt(block, doc, context if block == "E4" else "")
                try:
                    data = llmpool.ask_json(system, user, model=model, canary=canary,
                                            timeout=1800,
                                            extra=llmpool.FAST if fast else None)
                except Exception as e:
                    out["errors"][block] = str(e)[:200]
                    continue
                data.pop("doc_end_marker", None)
                # Union across passes: a value found by one pass is kept.
                # Recall, not consensus — a missed field is a lost fact, while a
                # spurious one still has to survive grounding.
                for k, v in data.items():
                    if k not in merged or not _has_value(merged.get(k)):
                        merged[k] = v
            out["blocks"][block] = merged
            if block in ("E1", "E2"):
                context += json.dumps(
                    {k: (v.get("value") if isinstance(v, dict) else v)
                     for k, v in merged.items()}, ensure_ascii=False)[:1200] + "\n"
        return out

    results = llmpool.map_concurrent(
        extract_one, todo, workers=workers, label="extract",
        sink=lambda r: store.append_jsonl(p(out_dir, A_EXTRACT), r))
    n = sum(1 for r in results if isinstance(r, dict) and "__error__" not in r)
    for r in results:
        if isinstance(r, dict) and "__error__" in r:
            print(f"    ! extraction failed: {r['__error__'][:120]}")
    print(f"  extracted {n} works")
    return n


def _has_value(cell) -> bool:
    if isinstance(cell, dict):
        v = str(cell.get("value") or "").strip().lower()
        return bool(v) and v not in ("not stated", "not_stated", "none", "n/a", "null")
    return bool(cell)


# --------------------------------------------------------------------------
# stage: ground
# --------------------------------------------------------------------------
def stage_ground(out_dir: str, srcs: dict) -> int:
    works = {w["work_id"]: w for w in store.read_jsonl(p(out_dir, A_WORKS))}
    screened = {s["work_id"]: s for s in store.read_jsonl(p(out_dir, A_SCREEN))}
    acquired = {a["work_id"]: a for a in store.read_jsonl(p(out_dir, A_ACQUIRE))}
    extracted = store.read_jsonl(p(out_dir, A_EXTRACT))
    crossref = srcs.get("crossref")

    rows: list[dict] = []
    cells_long: list[dict] = []
    for ex in extracted:
        wid = ex["work_id"]
        w = works.get(wid)
        if not w:
            continue
        ft = read_fulltext(out_dir, wid)
        evidence, _lvl, has_ft = fulltext.evidence_for(w, ft)

        flat_raw: dict = {}
        for block in ("E1", "E2", "E3", "E4"):
            flat_raw.update(ex["blocks"].get(block) or {})

        row, cells = grounding.ground_row(
            flat_raw, evidence, ex["level"], schema.LIT_MODE, schema.LIT_KEYS, has_ft)

        # Columns 1-3 come from the APIs, never from the model.
        meta = w
        if crossref is not None and w.get("doi"):
            fetched = crossref.by_doi(w["doi"])
            if fetched and fetched.get("title"):
                meta = {**w, **{k: v for k, v in fetched.items() if v}}
        row["reference"] = sources.CrossrefSource.reference_string(meta)
        row["doi"] = meta.get("doi", "")
        row["pub_type"] = screened.get(wid, {}).get("pub_type", "other")
        for key, val, lvl in (("reference", row["reference"], "metadata_only"),
                              ("doi", row["doi"], "metadata_only"),
                              ("pub_type", row["pub_type"], "metadata_only")):
            cells[key] = schema.new_cell(value=val, level=lvl, status="grounded_verbatim",
                                         quote="", locator="api")

        counts = schema.cell_counts(cells)
        row.update({
            "work_id": wid, "year": meta.get("year") or "", "venue": meta.get("venue") or "",
            "authors": "; ".join(meta.get("authors") or []),
            "source": ",".join(w.get("sources") or []),
            "oa_status": w.get("oa_status", ""),
            "fulltext_source": acquired.get(wid, {}).get("fulltext_source", ""),
            "fulltext_chars": acquired.get(wid, {}).get("fulltext_chars", 0),
            "screen_decision": screened.get(wid, {}).get("decision", ""),
            "extraction_model": ex.get("model", ""), "extracted_at": ex.get("extracted_at", ""),
            **counts, "row_confidence": schema.row_confidence(cells),
        })
        rows.append(row)
        for field, cell in cells.items():
            cells_long.append({
                "work_id": wid, "doi": row["doi"], "field": field,
                "value": cell["value"], "unit": cell["unit"], "raw": cell["raw"],
                "evidence_level": cell["level"], "status": cell["status"],
                "quote": cell["quote"], "locator": cell["locator"],
                "checks": ";".join(cell["checks"]),
            })

    store.write_jsonl(p(out_dir, A_ROWS), rows)
    store.write_jsonl(p(out_dir, A_CELLS), cells_long)
    blanked = sum(1 for c in cells_long if c["status"] == "ungrounded_blanked")
    full = sum(1 for c in cells_long if c["evidence_level"] == "full_text_verified")
    print(f"  grounded {len(rows)} rows / {len(cells_long)} cells "
          f"({full} full-text-verified, {blanked} blanked as ungrounded)")
    return len(rows)
