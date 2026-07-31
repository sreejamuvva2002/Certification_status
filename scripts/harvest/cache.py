"""Single chokepoint for every outbound HTTP request: cache, pacing, retry.

Every network call in this pipeline goes through `fetch()`. That buys three
things at once:

  * A disk cache, so a re-run costs nothing. The certification pipeline has no
    cache and re-pays for every query on every run; at this pipeline's volume
    (thousands of requests, some of them metered Tavily credits) that would be
    the dominant cost.
  * Per-host pacing. Google Patents soft-blocked this IP after ~6 rapid probes
    during planning and stayed blocked through four rounds of backoff, so
    politeness here is not optional.
  * A typed error taxonomy. A query that ran and returned nothing ("empty") is
    a FINDING; a query that never ran ("blocked", "timeout") is a FAILURE.
    Collapsing those two would silently turn a dead endpoint into "no such
    literature exists", which is the exact failure this whole report must avoid.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# Query params that must not affect the cache key: rotating a Tavily key or
# changing the polite-pool contact address should never cause a cache miss.
VOLATILE_PARAMS = {"mailto", "email", "api_key", "apikey", "key", "token", "_"}

OK_CODES = {"ok", "empty"}
FAILURE_CODES = {
    "http_error", "rate_limited", "blocked", "timeout",
    "parse_error", "key_exhausted", "not_found",
}
SOURCE_CODES = OK_CODES | FAILURE_CODES

RETRY_STATUSES = {429, 500, 502, 503, 504}
GZIP_THRESHOLD = 64 * 1024

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Minimum seconds between requests per host. Google Patents is deliberately
# slow and single-threaded — losing that endpoint ends the patent track.
HOST_INTERVALS = {
    "patents.google.com": 2.5,
    "api.openalex.org": 0.2,
    "api.crossref.org": 0.35,
    "doi.org": 0.35,
    "www.ebi.ac.uk": 0.34,
    "api.unpaywall.org": 0.2,
    "api.tavily.com": 1.0,
}
DEFAULT_INTERVAL = 0.5


class _Pacer:
    """Per-host rate limiter. Jittered so parallel workers don't sync up."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}

    def wait(self, host: str) -> None:
        interval = HOST_INTERVALS.get(host, DEFAULT_INTERVAL)
        with self._lock:
            now = time.monotonic()
            due = self._next.get(host, 0.0)
            sleep_for = max(0.0, due - now)
            self._next[host] = max(now, due) + interval + random.uniform(0, interval * 0.4)
        if sleep_for > 0:
            time.sleep(sleep_for)


_PACER = _Pacer()
_INDEX_LOCK = threading.Lock()


def cache_key(method: str, url: str, body: str | None, source: str) -> str:
    scheme, netloc, path, qs, _ = urllib.parse.urlsplit(url)
    params = sorted(
        (k, v) for k, v in urllib.parse.parse_qsl(qs, keep_blank_values=True)
        if k.lower() not in VOLATILE_PARAMS
    )
    canon = json.dumps(
        {"m": method.upper(), "u": f"{scheme}://{netloc}{path}", "q": params,
         "b": body or "", "s": source},
        sort_keys=True,
    )
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()


class HttpCache:
    def __init__(self, root: str) -> None:
        self.root = root
        self.index = os.path.join(root, "INDEX.jsonl")
        os.makedirs(root, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def _path(self, source: str, key: str, gz: bool) -> str:
        return os.path.join(self.root, source, key[:2], key + (".json.gz" if gz else ".json"))

    def read(self, source: str, key: str, ttl_days: float | None) -> dict | None:
        for gz in (False, True):
            path = self._path(source, key, gz)
            if not os.path.exists(path):
                continue
            try:
                opener = gzip.open if gz else open
                with opener(path, "rt", encoding="utf-8") as fh:
                    env = json.load(fh)
            except Exception:
                return None  # corrupt entry: treat as a miss, it will be rewritten
            if ttl_days is not None:
                age_days = (time.time() - env.get("fetched_at", 0)) / 86400.0
                if age_days > ttl_days:
                    return None
            self.hits += 1
            return env
        return None

    def write(self, env: dict) -> None:
        body = env.get("body") or ""
        gz = len(body) > GZIP_THRESHOLD
        path = self._path(env["source"], env["key"], gz)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        opener = gzip.open if gz else open
        with opener(tmp, "wt", encoding="utf-8") as fh:
            json.dump(env, fh)
        os.replace(tmp, path)  # atomic: a killed run never leaves a half entry
        with _INDEX_LOCK, open(self.index, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "key": env["key"], "source": env["source"], "url": env["url"],
                "code": env["code"], "status": env["status"],
                "bytes": len(body), "fetched_at": env["fetched_at"],
            }) + "\n")

    def stats(self) -> str:
        total = self.hits + self.misses
        pct = (100.0 * self.hits / total) if total else 0.0
        return f"cache {self.hits} hit / {self.misses} miss ({pct:.0f}% hit)"


_CACHE: HttpCache | None = None


def init_cache(root: str) -> HttpCache:
    global _CACHE
    _CACHE = HttpCache(root)
    return _CACHE


def get_cache() -> HttpCache | None:
    return _CACHE


def _classify(status: int) -> str:
    if status == 200:
        return "ok"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    if status in (401, 402, 403):
        return "blocked"
    return "http_error"


def fetch(url: str, *, source: str, method: str = "GET", body: bytes | None = None,
          headers: dict | None = None, timeout: float = 45.0, retries: int = 3,
          backoff: float = 2.0, ttl_days: float | None = None,
          use_cache: bool = True, refresh: bool = False, binary: bool = False) -> dict:
    """Fetch a URL through the cache. Never raises for HTTP-level problems.

    Returns {"code", "status", "body", "cached", "url", "error"} where `code`
    is one of SOURCE_CODES.

    `binary=True` is required for PDFs and other non-text payloads: the default
    path decodes the response as UTF-8, which silently mangles binary data
    beyond recovery. Binary bodies are base64-encoded for storage and returned
    as bytes in "raw".
    """
    key = cache_key(method, url, body.decode("utf-8", "ignore") if body else None, source)
    cache = get_cache()

    if cache is not None and use_cache and not refresh:
        env = cache.read(source, key, ttl_days)
        if env is not None:
            out = {"code": env["code"], "status": env["status"], "body": env["body"],
                   "cached": True, "url": url, "error": None, "raw": b""}
            if env.get("binary"):
                out["raw"] = base64.b64decode(env["body"])
                out["body"] = ""
            return out
    if cache is not None:
        cache.misses += 1

    host = urllib.parse.urlsplit(url).netloc
    hdrs = {"User-Agent": DEFAULT_UA, "Accept-Language": "en-US,en;q=0.9"}
    hdrs.update(headers or {})

    status, code, text, err = 0, "http_error", "", None
    raw_bytes = b""
    for attempt in range(retries + 1):
        _PACER.wait(host)
        try:
            req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                status = resp.status
                if binary:
                    raw_bytes = raw
                    text = base64.b64encode(raw).decode("ascii")
                else:
                    text = raw.decode("utf-8", "ignore")
                code = "ok"
            break
        except urllib.error.HTTPError as e:
            status = e.code
            code = _classify(e.code)
            err = f"HTTP {e.code}"
            try:
                text = e.read().decode("utf-8", "ignore")
            except Exception:
                text = ""
            if e.code not in RETRY_STATUSES or attempt == retries:
                break
            retry_after = e.headers.get("Retry-After") if e.headers else None
            wait = float(retry_after) if (retry_after or "").isdigit() else backoff ** attempt
        except Exception as e:  # timeouts, connection resets, DNS
            status, code, err = 0, "timeout", str(e)
            if attempt == retries:
                break
            wait = backoff ** attempt
        time.sleep(min(wait, 60.0) * random.uniform(0.75, 1.25))

    env = {"key": key, "source": source, "url": url, "method": method,
           "fetched_at": time.time(), "status": status, "code": code, "body": text,
           "binary": binary}

    # Cache successes and hard 404s (negative caching, short TTL). Never cache a
    # transport failure: a 503 is not an answer about the world.
    if cache is not None and use_cache and code in ("ok", "not_found"):
        cache.write(env)

    return {"code": code, "status": status, "body": "" if binary else text,
            "raw": raw_bytes, "cached": False, "url": url, "error": err}


def fetch_json(url: str, **kw) -> dict:
    """fetch() + JSON parse. Parse failure becomes code='parse_error'."""
    res = fetch(url, **kw)
    if res["code"] != "ok":
        res["data"] = None
        return res
    try:
        res["data"] = json.loads(res["body"])
    except Exception as e:
        res["data"] = None
        res["code"] = "parse_error"
        res["error"] = f"json: {e}"
    return res
