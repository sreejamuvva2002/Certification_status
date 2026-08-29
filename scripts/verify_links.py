"""Fetch and record the state of every source URL across all result sets.

"Verify the links" means two different things, and this script separates them:

  reachability  does the URL still resolve and return content? (status, redirects, type)
  support       does the evidence_quote attached to it actually appear on that page?

Only the first is done here; the text of every fetched page is cached so the merge step can
answer the second. They are separate because a live URL that no longer supports the claim is
a different problem from a dead one, and collapsing them hides which is which.

Notes on fidelity:
  * A fresh cache is used rather than run 2's page_cache, whose entries were truncated to
    4000 characters by _strip_html — a quote from further down a page would look absent.
  * PDFs are text-extracted with pdftotext, since registrar certificates are usually PDFs and
    those are exactly the sources worth checking.
  * Per-host pacing and a small thread pool: registrar sites throttle, and hammering them
    would produce failures that say more about our manners than about the link.

Resumable: URLs already recorded in link_status.json are skipped unless --recheck.

Usage:  python scripts/verify_links.py [--limit N] [--recheck]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
PKG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import check_certifications as cc  # noqa: E402  (BROWSER_UA, _strip_html)
from merge_sources import load_all  # noqa: E402

OUT_DIR = PKG_ROOT / "outputs" / "run2_gapfill"
CACHE = OUT_DIR / "verify_cache"
STATUS = OUT_DIR / "link_status.json"
MAX_BYTES = 5_000_000
HOST_INTERVAL = 2.0

_host_lock: dict[str, threading.Lock] = defaultdict(threading.Lock)
_host_last: dict[str, float] = {}
_status_lock = threading.Lock()


def _key(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()


def _extract(raw: bytes, content_type: str, path: Path) -> str:
    """Page text: pdftotext for PDFs, tag-stripping for everything else. No truncation."""
    if "pdf" in content_type.lower() or raw[:5] == b"%PDF-":
        pdf = path.with_suffix(".pdf")
        pdf.write_bytes(raw)
        try:
            out = subprocess.run(["pdftotext", "-q", str(pdf), "-"],
                                 capture_output=True, timeout=60)
            return out.stdout.decode("utf-8", errors="replace")
        except Exception:
            return ""
        finally:
            pdf.unlink(missing_ok=True)
    html = raw.decode("utf-8", errors="replace")
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html,
                  flags=re.DOTALL | re.IGNORECASE)
    import html as html_lib
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def fetch(url: str) -> dict:
    host = urlsplit(url).netloc.lower()
    with _host_lock[host]:
        wait = HOST_INTERVAL - (time.monotonic() - _host_last.get(host, -1e9))
        if wait > 0:
            time.sleep(wait)
        _host_last[host] = time.monotonic()

    rec: dict = {"url": url, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    req = urllib.request.Request(url, headers={
        "User-Agent": cc.BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read(MAX_BYTES)
            rec.update(status=resp.status, final_url=resp.url,
                       content_type=resp.headers.get("Content-Type", ""), bytes=len(raw))
            text = _extract(raw, rec["content_type"], CACHE / _key(url))
            (CACHE / f"{_key(url)}.txt").write_text(text, encoding="utf-8")
            rec["text_chars"] = len(text)
            rec["ok"] = resp.status == 200 and len(text) > 0
            rec["redirected"] = resp.url.rstrip("/") != url.rstrip("/")
    except urllib.error.HTTPError as e:
        rec.update(status=e.code, ok=False, error=f"HTTP {e.code}", text_chars=0)
    except Exception as e:
        rec.update(status=0, ok=False, error=f"{e.__class__.__name__}: {e}"[:160],
                   text_chars=0)
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--recheck", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    done = {} if args.recheck else (json.loads(STATUS.read_text()) if STATUS.exists() else {})

    urls = sorted({r["source_url"] for r in load_all()
                   if r["source_url"].startswith("http")})
    todo = [u for u in urls if u not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(urls)} distinct URLs; {len(done)} already checked; fetching {len(todo)}")

    n = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for rec in ex.map(fetch, todo):
            with _status_lock:
                done[rec["url"]] = rec
                n += 1
                if n % 25 == 0 or n == len(todo):
                    STATUS.write_text(json.dumps(done, indent=1))
                    print(f"  {n}/{len(todo)} checked")
    STATUS.write_text(json.dumps(done, indent=1))

    ok = sum(1 for r in done.values() if r.get("ok"))
    dead = sorted({r["status"] for r in done.values() if not r.get("ok")})
    print(f"\nreachable with text: {ok}/{len(done)}")
    print(f"failure statuses seen: {dead}")
    for r in sorted(done.values(), key=lambda r: str(r.get("status"))):
        if not r.get("ok"):
            print(f"  [{r.get('status')}] {r['url'][:100]}  {r.get('error', '')[:60]}")


if __name__ == "__main__":
    main()
