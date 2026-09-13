# Last successful balance observations

On September 9, 2026 at approximately 14:34 UTC, the first post-pilot usage check
returned 950 account-plan credits remaining through key 1 and 1,000 through each
of keys 2–14. Keys 15–17 returned HTTP 429 and were not refreshed. Their earlier
pre-pilot readings are preserved in `../credit-check/keys.json`.

The successful first 14 readings sum to 13,950 accessible per-key credits. This is
not a verified independent account total: the API response supplies no account ID.
Key 1 alone covers the 460 remaining basic baseline searches, before retries.

Subsequent refresh attempts were rate-limited. The latest raw check in this folder
records unknown/deferred balances rather than treating them as zero. The earlier
post-pilot observation above is preserved from the tool execution output; its raw
files in `credit-check-after-pilot` were overwritten by that directory's retry.
No credit checks submitted any searches.
