"""Evidence harvest for the 1-MCP humidity-responsive packaging report.

Retrieval-first by design: bibliographic identifiers come from OpenAlex, Crossref,
Europe PMC and Google Patents, and the local LLM is only ever asked to extract
from text that was actually retrieved. Every extracted value is then checked
against that text by harvest/grounding.py before it can reach a table cell, so a
value the model invented cannot ship.

Stages run in order and each is independently resumable — a failed extraction
never forces a re-harvest, and everything fetched is cached on disk.

    python3 scripts/run_harvest.py all                 # full run
    python3 scripts/run_harvest.py all --limit 5       # smoke test
    python3 scripts/run_harvest.py screen extract      # named stages
    python3 scripts/run_harvest.py --cache-stats

Env: LLM_BASE_URL, LLM_MODEL, LLM_API_KEY, TAVILY_API_KEYS, CONTACT_EMAIL.
"""
from __future__ import annotations

import argparse
import os
import sys
from argparse import RawDescriptionHelpFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PKG_ROOT = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(PKG_ROOT, "outputs", "1mcp")

STAGES = ["queries", "harvest", "normalize", "screen", "acquire", "extract", "ground",
          "pat-harvest", "pat-normalize", "pat-screen", "pat-detail", "pat-extract",
          "pat-ground", "verify", "emit"]


def load_env() -> None:
    """Read .env without adding a dependency, as the other scripts here do."""
    path = os.path.join(PKG_ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=RawDescriptionHelpFormatter)
    ap.add_argument("stages", nargs="*", default=["all"],
                    help=f"stages to run: all, or any of {', '.join(STAGES)}")
    ap.add_argument("--out", default=DEFAULT_OUT, help="artifact directory")
    ap.add_argument("--cache-dir", default=None, help="default: <out>/cache")
    ap.add_argument("--model", default=None, help="override LLM_MODEL")
    ap.add_argument("--limit", type=int, default=None, help="cap new items per stage")
    ap.add_argument("--workers", type=int, default=4, help="HTTP workers")
    ap.add_argument("--llm-workers", type=int, default=2, help="concurrent LLM calls")
    ap.add_argument("--pages", type=int, default=2, help="pages per search query")
    ap.add_argument("--per-page", type=int, default=100)
    ap.add_argument("--max-works", type=int, default=700,
                    help="cap works sent to screening, best-scoring first")
    ap.add_argument("--n-originals", type=int, default=60,
                    help="original papers to extract (over-selects vs the 40 minimum)")
    ap.add_argument("--n-reviews", type=int, default=22,
                    help="reviews to extract (over-selects vs the 15 minimum)")
    ap.add_argument("--n-patents", type=int, default=40,
                    help="patent families to extract in detail, most relevant first")
    ap.add_argument("--fast-extract", action="store_true",
                    help="skip the model's reasoning pass during extraction (faster, less accurate)")
    ap.add_argument("--e2-passes", type=int, default=2,
                    help="extraction passes on the release block (recall, not consensus)")
    ap.add_argument("--pdf-drop", default=None,
                    help="folder of user-supplied PDFs to ingest at full-text depth")
    ap.add_argument("--fresh", action="store_true", help="discard prior stage outputs")
    ap.add_argument("--refresh", action="store_true", help="bypass cache reads")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--cache-stats", action="store_true")
    ap.add_argument("--max-failure-rate", type=float, default=0.30)
    ap.add_argument("--health-after", type=int, default=12)
    args = ap.parse_args()

    from harvest import cache, emit, patents, sources, stages, store, verify

    out_dir = os.path.abspath(args.out)
    store.ensure_dir(out_dir)
    cache_dir = args.cache_dir or os.path.join(out_dir, "cache")
    c = cache.init_cache(cache_dir)

    if args.cache_stats:
        idx = store.read_jsonl(c.index)
        by_src: dict[str, int] = {}
        total = 0
        for r in idx:
            by_src[r["source"]] = by_src.get(r["source"], 0) + 1
            total += r.get("bytes", 0)
        print(f"cache dir: {cache_dir}")
        print(f"entries: {len(idx)}  bytes: {total / 1e6:.1f} MB")
        for k, v in sorted(by_src.items(), key=lambda x: -x[1]):
            print(f"  {k:<12} {v}")
        return 0

    want = STAGES if "all" in args.stages else args.stages
    for s in want:
        if s not in STAGES:
            print(f"unknown stage {s!r}; choose from {', '.join(STAGES)}", file=sys.stderr)
            return 2

    if args.fresh:
        for name in os.listdir(out_dir):
            if name[:2].isdigit() and name.endswith(".jsonl"):
                store.truncate(os.path.join(out_dir, name))
        print("  --fresh: cleared stage artifacts (cache kept)")

    needs_llm = any(s in want for s in
                    ("screen", "extract", "pat-screen", "pat-extract"))
    from harvest import llmpool
    model = llmpool.model_name(args.model)
    if needs_llm:
        if not llmpool.ping():
            print(f"LLM not reachable at {os.environ.get('LLM_BASE_URL')} — start Ollama "
                  f"or pass only non-LLM stages.", file=sys.stderr)
            return 2
        print(f"  model: {model}")

    srcs = sources.available(["openalex", "crossref", "epmc", "unpaywall",
                              "tavily", "gpatents"])
    print(f"  sources: {', '.join(sorted(srcs))}")
    print(f"  out: {out_dir}")

    ran = []
    try:
        for s in want:
            print(f"\n=== {s} ===")
            if s == "queries":
                stages.stage_queries(out_dir)
            elif s == "harvest":
                stages.stage_harvest(out_dir, srcs, pages=args.pages, per_page=args.per_page,
                                     max_failure_rate=args.max_failure_rate,
                                     health_after=args.health_after)
            elif s == "normalize":
                stages.stage_normalize(out_dir, max_works=args.max_works)
            elif s == "screen":
                stages.stage_screen(out_dir, model, workers=args.llm_workers, limit=args.limit)
            elif s == "acquire":
                stages.stage_acquire(out_dir, srcs, drop_dir=args.pdf_drop,
                                     workers=args.workers, limit=args.limit)
            elif s == "extract":
                stages.stage_extract(out_dir, model, workers=args.llm_workers,
                                     limit=args.limit, e2_passes=args.e2_passes,
                                     n_originals=args.n_originals, n_reviews=args.n_reviews,
                                     fast=args.fast_extract)
            elif s == "ground":
                stages.stage_ground(out_dir, srcs)
            elif s == "pat-harvest":
                patents.stage_pat_harvest(out_dir, srcs, pages=args.pages)
            elif s == "pat-normalize":
                patents.stage_pat_normalize(out_dir)
            elif s == "pat-screen":
                patents.stage_pat_screen(out_dir, model, workers=args.llm_workers,
                                         limit=args.limit)
            elif s == "pat-detail":
                patents.stage_pat_detail(out_dir, srcs, workers=args.llm_workers,
                                         limit=args.limit)
            elif s == "pat-extract":
                patents.stage_pat_extract(out_dir, model, workers=args.llm_workers,
                                          limit=args.limit, n_families=args.n_patents)
            elif s == "pat-ground":
                patents.stage_pat_ground(out_dir)
            elif s == "verify":
                verify.stage_verify(out_dir, srcs)
            elif s == "emit":
                emit.stage_emit(out_dir)
            ran.append(s)
    except KeyboardInterrupt:
        print("\n  interrupted — completed stages are on disk and will resume", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"\n  stage failed: {e}", file=sys.stderr)
        print(f"  completed: {', '.join(ran) or 'none'}", file=sys.stderr)
        return 1

    print(f"\n  done: {', '.join(ran)}")
    print(f"  {c.stats()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
