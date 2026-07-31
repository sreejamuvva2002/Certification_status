"""Retry, truncation detection, and concurrency over the local LLM.

Adds three things `llm_client.chat` lacks and this workload needs:

  * Retries. One bad JSON response should not lose a paper.
  * A truncation canary. This is the important one. If the server ever serves
    the model with a small context window, a long document is silently cut and
    every field comes back "not stated" — which then grounds perfectly, because
    the model genuinely never saw the text. That failure is invisible without a
    check, so every document call appends an end marker the model must echo
    back. A mismatch raises rather than returning plausible emptiness.
  * A modest thread pool. Ollama serialises unless OLLAMA_NUM_PARALLEL is set,
    and long-context requests are memory-hungry, so the default is deliberately
    low.
"""
from __future__ import annotations

import os
import random
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import llm_client  # noqa: E402

_PRINT_LOCK = threading.Lock()


class TruncationError(RuntimeError):
    """The model did not see the whole document."""


def log(msg: str) -> None:
    with _PRINT_LOCK:
        print(msg, flush=True)


def make_canary() -> str:
    return f"{random.randrange(16 ** 8):08x}"


def with_canary(document: str) -> tuple[str, str]:
    canary = make_canary()
    return f"{document}\n\n[DOC-END-MARKER: {canary}]", canary


# Thinking models spend most of their latency on a hidden reasoning pass. On a
# screening decision that is pure waste: measured here, 6.7s and 640 completion
# tokens with reasoning versus 0.6s and 30 tokens without, for the same verdict.
# Extraction keeps reasoning on — reading 25 fields out of a full paper is
# exactly the kind of work it helps with.
FAST = {"reasoning_effort": "none"}


def ask_json(system: str, user: str, *, model: str | None = None, canary: str | None = None,
             retries: int = 2, timeout: float = 900.0, temperature: float = 0.0,
             extra: dict | None = None) -> dict:
    """One JSON call with retries and optional truncation check."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            messages = [{"role": "system", "content": system},
                        {"role": "user", "content": user}]
            if attempt:
                messages.append({
                    "role": "system",
                    "content": "Your previous reply was not valid JSON. Reply with a single "
                               "JSON object and nothing else — no prose, no code fences.",
                })
            raw = llm_client.chat(messages, model=model, temperature=temperature,
                                  timeout=timeout, extra=extra)
            data = llm_client.extract_json(raw)
            if canary:
                echoed = str(data.get("doc_end_marker") or "")
                if canary not in echoed and canary not in raw:
                    raise TruncationError(
                        f"end marker {canary} not echoed (got {echoed!r}) — the model did not "
                        f"receive the whole document; refusing the extraction")
            return data
        except TruncationError:
            raise  # never retry: retrying cannot make the context bigger
        except Exception as e:
            last = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after {retries + 1} attempts: {last}")


def map_concurrent(fn, items: list, workers: int = 2, label: str = "",
                   sink=None) -> list:
    """Run `fn` over `items`, optionally persisting each result as it lands.

    `sink` is called with every successful result the moment it is produced,
    from the worker thread. It must be safe to call concurrently —
    store.append_jsonl is, because it holds a module-level write lock.

    Persisting incrementally rather than at the end is the difference between a
    long run that resumes and one that loses everything to a single crash. That
    resumability is the point of the staged design, so results are never held
    in memory until the end.
    """
    if not items:
        return []

    total = len(items)
    done = {"n": 0}

    def run_one(item):
        try:
            res = fn(item)
        except Exception as e:  # a failure becomes a record, never a crash
            res = {"__error__": str(e)}
        if sink is not None and isinstance(res, dict) and "__error__" not in res:
            try:
                sink(res)
            except Exception as e:
                log(f"  ! sink failed: {e}")
        done["n"] += 1
        if label and (done["n"] % 5 == 0 or done["n"] == total):
            log(f"  [{label}] {done['n']}/{total}")
        return res

    if workers <= 1:
        return [run_one(item) for item in items]

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run_one, items))


def ping() -> bool:
    return llm_client.ping()


def model_name(override: str | None = None) -> str:
    return override or os.environ.get("LLM_MODEL") or llm_client.DEFAULT_MODEL
