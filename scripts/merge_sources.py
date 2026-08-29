"""Load every certification result set into one canonical shape.

Three origins feed the merge:

  llm_a       notes.md, first JSON array — 692 rows, all 205 records
  llm_b       notes.md, remaining 16 arrays — 461 rows in batches of ten, records 1-150 only
  run1/run2*  outputs/run2_gapfill/certifications_normalized.csv — the pipeline's own result,
              already canonicalised and carrying scope_bucket / is_winner

notes.md rows arrive as raw certification strings ("IATF 16949:2016", "ISO/TS 16949 & ISO
14001"), so they go through the same explode + canonicalise path as the pipeline data. If a
string cannot be mapped the loader raises: a silent miss here would put the same standard in
two different buckets and quietly break every count downstream.

Import this from the merge/verify scripts; running it directly prints a load report.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import normalize_certs as nc  # noqa: E402

NOTES = PKG_ROOT / "outputs" / "run2_gapfill" / "notes.md"
NORMALIZED = PKG_ROOT / "outputs" / "run2_gapfill" / "certifications_normalized.csv"

# Fields carried through the merge, in the shape the final records use.
FIELDS = ("record_no", "company", "georgia_location", "certification", "canonical_id",
          "family", "domain", "scope", "certification_body", "reference_no", "issue_date",
          "expiry_date", "cert_status", "facility_status", "source_type", "source_url",
          "evidence_quote", "confidence", "notes")


def _blocks(path: Path) -> list:
    """Every top-level JSON value in a file that also contains prose/fences/blank padding."""
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    text = "\n".join(l for l in lines if not l.strip().startswith("```"))
    dec, i, out = json.JSONDecoder(), 0, []
    while i < len(text):
        while i < len(text) and text[i] not in "[{":
            i += 1
        if i >= len(text):
            break
        val, i = dec.raw_decode(text, i)
        out.append(val)
    return out


def _s(v) -> str:
    return "" if v is None else str(v).strip()


RECONSTRUCTION = PKG_ROOT / "outputs" / "run2_gapfill" / \
    "notes_llm_rows_partial_reconstruction.jsonl"


def _load_reconstruction() -> list[dict]:
    """Fallback source for the LLM rows when notes.md no longer holds the pasted arrays.

    notes.md was overwritten in error; this file rebuilds the certification rows from what
    the merge had already retained. It is LOSSY — 670 of the original 1,153 objects, some
    quotes truncated at 600 chars, and none of the absence rows ("none identified",
    "no EV/battery standard identified") survive. Re-paste the original into notes.md and
    this fallback stops being used.
    """
    if not RECONSTRUCTION.exists():
        return []
    rows, unmapped = [], []
    for line in RECONSTRUCTION.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        for token in nc.explode(_s(o.get("certification"))):
            hit = nc.canonicalise(token)
            if not hit:
                unmapped.append(token)
                continue
            cid, fam, dom, _n = hit
            rows.append({
                "origin": o["origin"], "record_no": str(o.get("record_no", "")),
                "company": _s(o.get("company")),
                "georgia_location": _s(o.get("georgia_location")),
                "certification": _s(o.get("certification")),
                "canonical_id": cid, "family": fam, "domain": dom,
                **{k: _s(o.get(k)) for k in
                   ("scope", "certification_body", "reference_no", "issue_date", "expiry_date",
                    "cert_status", "facility_status", "source_type", "source_url",
                    "evidence_quote", "confidence", "notes")},
            })
    if unmapped:
        raise SystemExit("unmapped strings in the reconstruction: " +
                         ", ".join(sorted(set(unmapped))))
    print(f"[merge_sources] notes.md holds no JSON arrays; using the LOSSY reconstruction "
          f"({len(rows)} rows). Re-paste the original to restore full fidelity.",
          file=sys.stderr)
    return rows


def load_notes(path: Path = NOTES) -> list[dict]:
    """notes.md -> flat rows tagged origin llm_a / llm_b, one row per canonical standard."""
    blocks = [b for b in _blocks(path) if isinstance(b, list) and b]
    if not blocks:
        return _load_reconstruction()
    tagged = [(o, "llm_a") for o in blocks[0]]
    for b in blocks[1:]:
        tagged += [(o, "llm_b") for o in b]

    rows, unmapped = [], []
    for o, origin in tagged:
        raw = _s(o.get("certification"))
        for token in nc.explode(raw):
            if any(__import__("re").fullmatch(p, token, __import__("re").IGNORECASE)
                   for p in nc.IGNORE_FRAGMENTS):
                continue
            hit = nc.canonicalise(token)
            if not hit:
                unmapped.append(token)
                continue
            cid, fam, dom, _note = hit
            rows.append({
                "origin": origin,
                "record_no": str(o.get("record_no", "")),
                "company": _s(o.get("company")),
                "georgia_location": _s(o.get("georgia_location")),
                "certification": raw,
                "canonical_id": cid, "family": fam, "domain": dom,
                "scope": _s(o.get("scope")),
                "certification_body": _s(o.get("certification_body")),
                "reference_no": _s(o.get("reference_no")),
                "issue_date": _s(o.get("issue_date")),
                "expiry_date": _s(o.get("expiry_date")),
                "cert_status": _s(o.get("cert_status")),
                "facility_status": _s(o.get("facility_status")),
                "source_type": _s(o.get("source_type")),
                "source_url": _s(o.get("source_url")),
                "evidence_quote": _s(o.get("evidence_quote")),
                "confidence": _s(o.get("confidence")),
                "notes": _s(o.get("notes")),
            })
    if unmapped:
        raise SystemExit("unmapped certification strings in notes.md — add to "
                         "normalize_certs.ALIASES:\n  " +
                         "\n  ".join(sorted(set(unmapped))))
    return rows


def load_pipeline(path: Path = NORMALIZED) -> list[dict]:
    """The pipeline's own normalised rows, tagged by which pass produced them."""
    origin_of = {"run1": "run1", "A": "run2_passA", "B": "run2_passB", "C": "run2_passC",
                 "E": "run2_passE"}
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "origin": origin_of.get(r["source_run"], r["source_run"]),
                "record_no": r["record_no"], "company": r["company"],
                "georgia_location": r["location"],
                "certification": r["raw_certification"],
                "canonical_id": r["canonical_id"], "family": r["family"],
                "domain": r["domain"], "scope": r["scope"],
                "certification_body": r["certification_body"],
                "reference_no": r["reference_no"], "issue_date": r["issue_date"],
                "expiry_date": r["expiry_date"], "cert_status": r["cert_status"],
                "facility_status": r["facility_status"], "source_type": r["source_type"],
                "source_url": r["source_url"], "evidence_quote": r["evidence_quote"],
                "confidence": r["confidence"], "notes": r["notes"],
            })
    return rows


def load_all() -> list[dict]:
    return load_notes() + load_pipeline()


def main() -> None:
    import collections
    rows = load_all()
    by = collections.Counter(r["origin"] for r in rows)
    print("rows by origin:")
    for k, v in by.most_common():
        recs = len({r["record_no"] for r in rows if r["origin"] == k})
        print(f"  {k:12s} {v:5d} rows  {recs:4d} records")
    real = [r for r in rows if not r["canonical_id"].startswith("__")]
    print(f"\ntotal {len(rows)} rows ({len(real)} certifications, "
          f"{len(rows) - len(real)} absence records)")
    print(f"distinct canonical standards: {len({r['canonical_id'] for r in real})}")
    print(f"distinct (record, standard) pairs: "
          f"{len({(r['record_no'], r['canonical_id']) for r in real})}")
    urls = {r["source_url"] for r in rows if r["source_url"].startswith("http")}
    print(f"distinct http(s) URLs: {len(urls)}")


if __name__ == "__main__":
    main()
