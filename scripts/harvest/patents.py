"""Patent landscape stages.

Discovery runs through Tavily site-restricted search rather than Google Patents
directly: the XHR endpoint blocked this IP during planning after ~6 rapid
requests and stayed blocked through four rounds of exponential backoff. Google
Patents is still tried opportunistically (cached forever, paced hard) because
its JSON gives clean structured metadata, but nothing depends on it.

Full documents come from Tavily's extract endpoint, which reaches the same
pages through its own crawler — a 400k-character document including complete
claim text. Metadata (assignee, priority date, inventors) is read out of that
document by the model and then grounded against it, so it is evidenced text
rather than model recall. The publication number alone is taken deterministically
from the URL.

Families are clustered heuristically from title, assignee and priority date.
INPADOC is unavailable (EPO OPS needs a key), and the report says so.
"""
from __future__ import annotations

import hashlib
import os
import re
import time

from . import grounding, llmpool, prompts, queries, schema, store

A_PAT_HITS = "10_patent_hits.jsonl"
A_PAT_QLOG = "10_patent_qlog.jsonl"
A_FAMILIES = "11_families.jsonl"
A_PAT_SCREEN = "12_pat_screen.jsonl"
A_PAT_DOCS = "13_docs"
A_PAT_DETAIL = "13_detail.jsonl"
A_PAT_EXTRACT = "14_pat_extract.jsonl"
A_PAT_ROWS = "15_pat_rows.jsonl"
A_PAT_CELLS = "15_pat_cells.jsonl"

MAX_DOC_CHARS = 400_000
PUBNUM_RE = re.compile(r"/patent/([A-Z]{2}\d[\w]*)/")


def p(out_dir: str, name: str) -> str:
    return os.path.join(out_dir, name)


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (t or "").lower()).strip()


def _norm_assignee(a: str) -> str:
    s = (a or "").lower()
    for suffix in (" llc", " inc", " ltd", " limited", " corp", " corporation", " gmbh",
                   " co", " company", " bv", " sa", " ag", " kk", " plc", " lp", "."):
        s = s.replace(suffix, " ")
    return re.sub(r"\s+", " ", s).strip()


def stage_pat_harvest(out_dir: str, srcs: dict, *, pages: int = 3) -> int:
    """Tavily site-restricted discovery, with Google Patents tried first."""
    qs = [q for q in store.read_jsonl(p(out_dir, "00_queries.jsonl")) if q["kind"] == "patent"]
    if not qs:
        qs = queries.patent_queries()
    done = store.done_ids(p(out_dir, A_PAT_QLOG), "run_id")
    gp = srcs.get("gpatents")
    tv = srcs.get("tavily")
    n_new = 0

    for q in qs:
        # 1. Google Patents, if it will talk to us. Structured metadata is better.
        run_id = f"{q['query_id']}:gpatents"
        if gp is not None and run_id not in done:
            cursor = None
            got = 0
            code = "empty"
            for _ in range(pages):
                res = gp.search(q["query"], cursor=cursor)
                code = res["code"]
                if not res["success"]:
                    break
                for rec in res["records"]:
                    rec.update({"query_id": q["query_id"], "band": q["band"]})
                    store.append_jsonl(p(out_dir, A_PAT_HITS), rec)
                    got += 1
                    n_new += 1
                cursor = res.get("next_cursor")
                if not cursor:
                    break
            store.append_jsonl(p(out_dir, A_PAT_QLOG), {
                "run_id": run_id, "query_id": q["query_id"], "source": "gpatents",
                "query": q["query"], "code": code, "records": got, "at": time.time()})
            print(f"    {run_id:<26} {code:<12} {got:>4}")

        # 2. Tavily site: search — the dependable path.
        run_id = f"{q['query_id']}:tavily"
        if tv is not None and run_id not in done:
            got = 0
            code = "empty"
            for page_q in (f"site:patents.google.com {q['query']}",
                           f"site:patents.google.com patent {q['query']}"):
                res = tv.search(page_q, limit=20)
                code = res["code"]
                if not res["success"]:
                    break
                for rec in res["records"]:
                    m = PUBNUM_RE.search(rec.get("url", ""))
                    if not m:
                        continue
                    store.append_jsonl(p(out_dir, A_PAT_HITS), {
                        "kind": "patent", "source": "tavily",
                        "pub_number": m.group(1), "title": rec.get("title", ""),
                        "snippet": rec.get("snippet", ""), "assignee": "",
                        "inventor": "", "priority_date": "", "filing_date": "",
                        "grant_date": "", "publication_date": "",
                        "url": f"https://patents.google.com/patent/{m.group(1)}/en",
                        "query_id": q["query_id"], "band": q["band"]})
                    got += 1
                    n_new += 1
            store.append_jsonl(p(out_dir, A_PAT_QLOG), {
                "run_id": run_id, "query_id": q["query_id"], "source": "tavily",
                "query": q["query"], "code": code, "records": got, "at": time.time()})
            print(f"    {run_id:<26} {code:<12} {got:>4}")

    print(f"  patent hits: {n_new} new rows")
    return n_new


def stage_pat_normalize(out_dir: str) -> int:
    """Dedupe by publication number, then cluster into approximate families."""
    hits = store.read_jsonl(p(out_dir, A_PAT_HITS))
    by_num: dict[str, dict] = {}
    for h in hits:
        num = h.get("pub_number") or ""
        if not num:
            continue
        cur = by_num.get(num)
        if cur is None:
            h["bands"] = [h.get("band", "")]
            by_num[num] = h
        else:
            for k, v in h.items():
                if not cur.get(k) and v:
                    cur[k] = v
            cur["bands"] = sorted(set(cur.get("bands", []) + [h.get("band", "")]) - {""})

    # Cluster: same normalized title, or same assignee + priority date.
    families: dict[str, dict] = {}
    for num, rec in sorted(by_num.items()):
        tkey = _norm_title(rec.get("title", ""))
        akey = f"{_norm_assignee(rec.get('assignee',''))}|{rec.get('priority_date','')}"
        fam_key = tkey if len(tkey) > 12 else (akey if akey.strip(" |") else num)
        fam = families.get(fam_key)
        if fam is None:
            families[fam_key] = {
                # hashlib, not hash(): Python randomises string hashing per
                # process, so hash() would mint a new family_id on every run and
                # silently break resume.
                "family_id": "fam:" + hashlib.sha1(fam_key.encode()).hexdigest()[:12],
                "members": [num], "rep": rec,
                "titles": [rec.get("title", "")],
                "bands": rec.get("bands", []),
            }
        else:
            fam["members"].append(num)
            fam["bands"] = sorted(set(fam["bands"] + rec.get("bands", [])) - {""})
            # Prefer a granted document (B-kind) as the family representative.
            if re.search(r"B\d?$", num) and not re.search(r"B\d?$", fam["rep"]["pub_number"]):
                fam["rep"] = rec

    out = []
    for fam in families.values():
        rep = fam["rep"]
        out.append({
            "family_id": fam["family_id"],
            "pub_number": rep["pub_number"],
            "members": sorted(set(fam["members"])),
            "n_members": len(set(fam["members"])),
            "title": rep.get("title", ""), "assignee": rep.get("assignee", ""),
            "inventor": rep.get("inventor", ""),
            "priority_date": rep.get("priority_date", ""),
            "publication_date": rep.get("publication_date", ""),
            "snippet": rep.get("snippet", ""), "url": rep.get("url", ""),
            "bands": fam["bands"],
        })
    out.sort(key=lambda f: (f.get("priority_date") or "", f["pub_number"]))
    store.write_jsonl(p(out_dir, A_FAMILIES), out)
    print(f"  {len(hits)} hits -> {len(by_num)} publications -> {len(out)} approximate families")
    return len(out)


def stage_pat_screen(out_dir: str, model: str, *, workers: int = 2,
                     limit: int | None = None) -> int:
    fams = store.read_jsonl(p(out_dir, A_FAMILIES))
    done = store.done_ids(p(out_dir, A_PAT_SCREEN), "family_id")
    todo = [f for f in fams if f["family_id"] not in done]
    if limit:
        todo = todo[:limit]
    print(f"  screening {len(todo)} families ({len(done)} done)")

    def screen_one(f: dict) -> dict:
        user = prompts.PATENT_SCREEN_USER.format(
            pub_number=f["pub_number"], title=f.get("title", ""),
            assignee=f.get("assignee", "") or "[not shown]",
            priority_date=f.get("priority_date", "") or "[not shown]",
            snippet=(f.get("snippet") or "")[:1500])
        try:
            data = llmpool.ask_json(prompts.PATENT_SCREEN_SYSTEM, user, model=model, timeout=240,
                                    extra=llmpool.FAST)
        except Exception as e:
            return {"family_id": f["family_id"], "decision": "maybe",
                    "relevance": "adjacent", "why": "", "screen_error": str(e)[:200]}
        return {"family_id": f["family_id"],
                "decision": schema.pick(data.get("decision"), schema.SCREEN_DECISIONS, "maybe"),
                "relevance": str(data.get("relevance") or "")[:30],
                "why": str(data.get("why") or "")[:120],
                "confidence": data.get("confidence") or 0.0, "screen_error": ""}

    results = llmpool.map_concurrent(
        screen_one, todo, workers=workers, label="pat-screen",
        sink=lambda r: store.append_jsonl(p(out_dir, A_PAT_SCREEN), r))
    counts: dict[str, int] = {}
    for r in store.read_jsonl(p(out_dir, A_PAT_SCREEN)):
        counts[r["decision"]] = counts.get(r["decision"], 0) + 1
    print(f"  patent screen: {counts}")
    return len(results)


def stage_pat_detail(out_dir: str, srcs: dict, *, workers: int = 2,
                     limit: int | None = None) -> int:
    """Fetch full patent documents through Tavily."""
    fams = {f["family_id"]: f for f in store.read_jsonl(p(out_dir, A_FAMILIES))}
    screened = store.read_jsonl(p(out_dir, A_PAT_SCREEN))
    wanted = [fams[s["family_id"]] for s in screened
              if s["decision"] in ("include", "maybe") and s["family_id"] in fams]
    done = store.done_ids(p(out_dir, A_PAT_DETAIL), "family_id")
    todo = [f for f in wanted if f["family_id"] not in done]
    if limit:
        todo = todo[:limit]
    doc_dir = p(out_dir, A_PAT_DOCS)
    store.ensure_dir(doc_dir)
    tv = srcs.get("tavily")
    if tv is None:
        print("  ! tavily unavailable — cannot fetch patent documents")
        return 0
    print(f"  fetching {len(todo)} patent documents ({len(done)} done)")

    def fetch_one(f: dict) -> dict:
        url = f.get("url") or f"https://patents.google.com/patent/{f['pub_number']}/en"
        try:
            text = tv.extract(url)
        except Exception as e:
            return {"family_id": f["family_id"], "chars": 0, "error": str(e)[:200]}
        if text:
            with open(os.path.join(doc_dir, f["pub_number"] + ".txt"), "w",
                      encoding="utf-8") as fh:
                fh.write(text)
        return {"family_id": f["family_id"], "pub_number": f["pub_number"],
                "chars": len(text), "url": url, "error": ""}

    results = llmpool.map_concurrent(
        fetch_one, todo, workers=workers, label="pat-detail",
        sink=lambda r: store.append_jsonl(p(out_dir, A_PAT_DETAIL), r))
    n = sum(1 for r in results if isinstance(r, dict) and r.get("chars"))
    print(f"  fetched {n} documents with content")
    return n


def read_doc(out_dir: str, pub_number: str) -> str:
    path = os.path.join(out_dir, A_PAT_DOCS, pub_number + ".txt")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _trim_patent(text: str) -> str:
    """Keep the metadata header and the claims; drop the citation tables.

    Google Patents renders enormous "Similar Documents"/"Citations" tables that
    add no claim information and would crowd the useful text.
    """
    if len(text) <= MAX_DOC_CHARS:
        return text
    head = text[:8000]
    ci = text.find("## Claims")
    if ci < 0:
        return text[:MAX_DOC_CHARS]
    claims = text[ci:ci + 120_000]
    desc = text[8000:ci][:MAX_DOC_CHARS - len(head) - len(claims)]
    return head + desc + claims


_RELEVANCE_RANK = {"core": 0, "adjacent": 1, "background": 2, "off_topic": 3}


def stage_pat_extract(out_dir: str, model: str, *, workers: int = 2,
                      limit: int | None = None, n_families: int = 40) -> int:
    fams = {f["family_id"]: f for f in store.read_jsonl(p(out_dir, A_FAMILIES))}
    screened = {s["family_id"]: s for s in store.read_jsonl(p(out_dir, A_PAT_SCREEN))}
    detail = [d for d in store.read_jsonl(p(out_dir, A_PAT_DETAIL)) if d.get("chars")]

    # Reading a full patent costs about a minute, so extracting every fetched
    # document would take longer than the whole literature run for families the
    # screener already judged off-topic. Rank by relevance and take the most
    # relevant; the brief asks for ~30 detailed families, and the rest remain in
    # the corpus as screened-but-not-detailed.
    def rank(d: dict) -> tuple:
        s = screened.get(d["family_id"], {})
        f = fams.get(d["family_id"], {})
        return (_RELEVANCE_RANK.get(s.get("relevance", ""), 4),
                0 if s.get("decision") == "include" else 1,
                -(f.get("n_members") or 1),
                f.get("priority_date") or "9999")

    detail.sort(key=rank)
    if n_families:
        detail = detail[:n_families]
    done = store.done_ids(p(out_dir, A_PAT_EXTRACT), "family_id")
    todo = [d for d in detail if d["family_id"] not in done]
    if limit:
        todo = todo[:limit]
    n_core = sum(1 for d in todo
                 if screened.get(d["family_id"], {}).get("relevance") == "core")
    print(f"  extracting {len(todo)} patent families ({len(done)} done), {n_core} core-relevance")

    def extract_one(d: dict) -> dict:
        fam = fams.get(d["family_id"], {})
        text = read_doc(out_dir, d.get("pub_number") or fam.get("pub_number", ""))
        doc, canary = llmpool.with_canary(_trim_patent(text))
        try:
            data = llmpool.ask_json(prompts.PATENT_SYSTEM,
                                    prompts.PATENT_USER.format(document=doc),
                                    model=model, canary=canary, timeout=1200)
        except Exception as e:
            return {"family_id": d["family_id"], "error": str(e)[:200], "fields": {}}
        data.pop("doc_end_marker", None)
        return {"family_id": d["family_id"], "pub_number": d.get("pub_number", ""),
                "claims_chars": d.get("chars", 0), "model": model,
                "extracted_at": time.time(), "fields": data, "error": ""}

    results = llmpool.map_concurrent(
        extract_one, todo, workers=workers, label="pat-extract",
        sink=lambda r: store.append_jsonl(p(out_dir, A_PAT_EXTRACT), r))
    n = sum(1 for r in results if isinstance(r, dict) and "__error__" not in r)
    print(f"  extracted {n} families")
    return n


def stage_pat_ground(out_dir: str) -> int:
    fams = {f["family_id"]: f for f in store.read_jsonl(p(out_dir, A_FAMILIES))}
    extracted = store.read_jsonl(p(out_dir, A_PAT_EXTRACT))
    rows: list[dict] = []
    cells_long: list[dict] = []

    for ex in extracted:
        fid = ex["family_id"]
        fam = fams.get(fid, {})
        pubnum = ex.get("pub_number") or fam.get("pub_number", "")
        text = read_doc(out_dir, pubnum)
        if not text:
            continue
        row, cells = grounding.ground_row(
            ex.get("fields") or {}, text, "full_text_verified",
            schema.PAT_MODE, schema.PAT_KEYS, True)

        # Strip format placeholders the model sometimes echoes back alongside a
        # real value ("2016-02-19 YYYY-MM-DD"), and keep only an ISO date.
        for date_field in ("priority_date", "publication_date"):
            m = re.search(r"\d{4}-\d{2}-\d{2}", row.get(date_field) or "")
            row[date_field] = m.group(0) if m else ""
            if date_field in cells:
                cells[date_field]["value"] = row[date_field]

        # Deterministic fields: from the URL and our own clustering, not the model.
        row["family_id"] = fid
        members = fam.get("members") or [pubnum]
        row["family_members_seen"] = ", ".join(members)
        for key, val in (("family_id", fid), ("family_members_seen", row["family_members_seen"])):
            cells[key] = schema.new_cell(value=val, level="metadata_only",
                                         status="grounded_verbatim", locator="derived")
        counts = schema.cell_counts(cells)
        row.update({
            "pub_number": pubnum, "n_family_members": len(members),
            "claims_chars": ex.get("claims_chars", 0),
            "extraction_model": ex.get("model", ""), "extracted_at": ex.get("extracted_at", ""),
            "n_blanked": counts["n_blanked"],
            "row_confidence": schema.row_confidence(cells),
        })
        rows.append(row)
        for field, cell in cells.items():
            cells_long.append({
                "family_id": fid, "pub_number": pubnum, "field": field,
                "value": cell["value"], "evidence_level": cell["level"],
                "status": cell["status"], "quote": cell["quote"],
                "checks": ";".join(cell["checks"]),
            })

    rows.sort(key=lambda r: (r.get("priority_date") or "9999", r.get("pub_number", "")))
    store.write_jsonl(p(out_dir, A_PAT_ROWS), rows)
    store.write_jsonl(p(out_dir, A_PAT_CELLS), cells_long)
    blanked = sum(1 for c in cells_long if c["status"] == "ungrounded_blanked")
    print(f"  grounded {len(rows)} patent families / {len(cells_long)} cells "
          f"({blanked} blanked as ungrounded)")
    return len(rows)
