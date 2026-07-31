"""Open-access full-text acquisition.

Order of preference: Europe PMC JATS XML (cleanest, keeps section structure) →
OA PDF via Unpaywall/OpenAlex → OA landing page via Tavily extract → user-supplied
PDFs from a drop folder.

Only openly licensed copies are fetched. Paywalled papers stay at abstract
depth and every cell they produce is labelled `abstract_only`, which is the
honest outcome: of the 25 most relevant papers on this topic, measured during
planning, only 4 were open access and 2 had a directly fetchable PDF. Most
process detail — drying temperature, loading, coat weight, package volume —
simply is not in an abstract, and the table shows that rather than papering
over it.

PDF text uses the `pdftotext` binary when present rather than adding a Python
PDF dependency; the repo is stdlib-only plus openpyxl by design.
"""
from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import tempfile

from . import cache

MIN_FULLTEXT_CHARS = 3000  # below this it is a landing page, not a paper


def _strip_xml(xml: str) -> str:
    """JATS/HTML → readable text, keeping section headings as anchors."""
    if not xml:
        return ""
    text = re.sub(r"<(script|style|ref-list|back)\b.*?</\1>", " ", xml,
                  flags=re.DOTALL | re.IGNORECASE)
    # Preserve structure the extractor benefits from knowing about.
    text = re.sub(r"<title[^>]*>(.*?)</title>", r"\n\n## \1\n", text,
                  flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<(p|sec|abstract|table-wrap|caption|td|tr)\b[^>]*>", "\n", text,
                  flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _pdf_to_text(data: bytes) -> str:
    if not shutil.which("pdftotext"):
        return ""
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp.write(data)
        tmp.close()
        out = subprocess.run(["pdftotext", "-q", "-layout", tmp.name, "-"],
                             capture_output=True, timeout=120)
        return out.stdout.decode("utf-8", "ignore")
    except Exception:
        return ""
    finally:
        os.unlink(tmp.name)


def looks_like_prose(text: str) -> bool:
    """Guard against binary or scanned-image junk being accepted as a paper.

    A PDF that is really a scanned image yields megabytes of noise from
    pdftotext. That noise passes a length check, so without this gate it would
    be handed to the extractor as though it were the paper — and every field
    would come back "not stated", which is indistinguishable from a genuine
    omission. Cheap structural checks catch it.
    """
    if len(text) < MIN_FULLTEXT_CHARS:
        return False
    sample = text[:20000]
    printable = sum(1 for ch in sample if ch.isprintable() or ch in "\n\r\t")
    if printable / max(1, len(sample)) < 0.90:
        return False
    letters = sum(1 for ch in sample if ch.isalpha())
    if letters / max(1, len(sample)) < 0.55:
        return False
    low = sample.lower()
    common = sum(1 for w in (" the ", " and ", " of ", " was ", " were ", " with ",
                             " for ", " that ", " this ") if w in low)
    return common >= 4


def _fetch_pdf_text(url: str) -> str:
    res = cache.fetch(url, source="fulltext", ttl_days=None, timeout=90, binary=True)
    if res["code"] != "ok":
        return ""
    raw = res.get("raw") or b""
    if not raw:
        return ""
    if raw[:5] == b"%PDF-":
        return _pdf_to_text(raw)
    text = raw.decode("utf-8", "ignore")
    return _strip_xml(text) if "<" in text[:400] else text


def acquire(rec: dict, epmc, unpaywall, tavily, drop_dir: str | None = None) -> dict:
    """Return {'text', 'source', 'chars'}; text is '' when nothing open was found."""
    doi = rec.get("doi") or ""
    work = rec.get("work_id") or ""

    # 1. User-supplied PDF wins: it is the deepest evidence available.
    if drop_dir and os.path.isdir(drop_dir):
        slug = re.sub(r"[^\w.-]", "_", doi or work)
        for name in os.listdir(drop_dir):
            stem = os.path.splitext(name)[0]
            if not name.lower().endswith(".pdf"):
                continue
            if stem == slug or (doi and stem.replace("_", "/") in doi):
                with open(os.path.join(drop_dir, name), "rb") as fh:
                    text = _pdf_to_text(fh.read())
                if looks_like_prose(text):
                    return {"text": text, "source": f"user_pdf:{name}", "chars": len(text)}

    # 2. Europe PMC JATS.
    pmcid = rec.get("pmcid") or ""
    if pmcid and epmc is not None:
        xml = epmc.full_text(pmcid)
        text = _strip_xml(xml)
        if looks_like_prose(text):
            return {"text": text, "source": f"epmc_jats:{pmcid}", "chars": len(text)}

    # 3. OA PDF already known, or looked up via Unpaywall.
    pdf_url = rec.get("pdf_url") or ""
    landing = rec.get("oa_url") or ""
    if not pdf_url and doi and unpaywall is not None:
        info = unpaywall.best_oa(doi)
        if info and info.get("is_oa"):
            pdf_url = info.get("pdf_url") or ""
            landing = landing or info.get("landing_url") or ""
    if pdf_url:
        text = _fetch_pdf_text(pdf_url)
        if looks_like_prose(text):
            return {"text": text, "source": f"oa_pdf:{pdf_url[:80]}", "chars": len(text)}

    # 4. OA landing page through Tavily's crawler.
    if landing and tavily is not None:
        text = tavily.extract(landing)
        if looks_like_prose(text):
            return {"text": text, "source": f"oa_html:{landing[:80]}", "chars": len(text)}

    return {"text": "", "source": "", "chars": 0}


def evidence_for(rec: dict, full_text: str) -> tuple[str, str, bool]:
    """Return (evidence_text, level_if_found, has_full_text).

    The abstract is always appended so a quote found only in the abstract still
    grounds when full text was also retrieved.
    """
    abstract = (rec.get("abstract") or "").strip()
    title = (rec.get("title") or "").strip()
    if full_text and looks_like_prose(full_text):
        return (f"{title}\n\n{abstract}\n\n{full_text}", "full_text_verified", True)
    return (f"{title}\n\n{abstract}", "abstract_only", False)
