"""Verify that every asserted value actually occurs in the retrieved text.

This is the anti-hallucination core. The model proposes; this module disposes.
It extends the substring check used for addresses in collect_locations.py,
which is too blunt for scientific values: "2.1 mg/g" and "2.1 mg g−1" are the
same measurement and must match, while a "2.1" lifted from an unrelated
sentence must not.

Three checks run per numeric cell, all deterministic:

  1. The model's quote must be locatable in the source text (exactly, or by
     fuzzy repair back to the exact span).
  2. The magnitude must match a quantity in the text after unit canonicalisation.
  3. The matched number must sit near a keyword for that field. Without this,
     any paper containing "40" would "confirm" a drying temperature of 40 °C.

A cell that fails is blanked, flagged, and drops the row's confidence — but the
row survives, exactly as an ungrounded address does in collect_locations.py.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

from . import schema

# Unicode that scientific text uses freely and plain matching trips over.
_CHAR_MAP = {
    "−": "-", "–": "-", "—": "-", "‐": "-", "‑": "-",
    "·": " ", "⋅": " ", "×": "x", "⁄": "/",
    # The degree sign is dropped rather than spelled out: sources print "40 °C"
    # while a quote may say "40 C", and mapping ° to "deg" would make those two
    # fail to match. Dropping it lets both normalize to "40 c".
    "µ": "u", "μ": "u", "°": "",
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁻": "-", "′": "'", "“": '"', "”": '"',
    "‘": "'", "’": "'", " ": " ",
}

# Greek letters are spelled out rather than dropped. Sources print "α-CD" while a
# model routinely writes "alpha-CD"; without this the 1-MCP-carrier column — the
# single most important one in the table — would be blanked wholesale as
# ungrounded. Caught by a dry run against a real paper.
# (μ/µ stay mapped to "u" above: there they mean micro, not the letter.)
_CHAR_MAP.update({
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "θ": "theta", "λ": "lambda", "σ": "sigma", "τ": "tau", "ω": "omega",
    "Α": "alpha", "Β": "beta", "Γ": "gamma", "Δ": "delta", "Ω": "omega",
})

# (magnitude_multiplier, canonical_unit) keyed by a normalized unit token.
_UNIT_TABLE: dict[str, tuple[float, str]] = {}


def _reg(canon: str, mult: float, *forms: str) -> None:
    for f in forms:
        _UNIT_TABLE[f] = (mult, canon)


_reg("mg/g", 1.0, "mg/g", "mgg-1", "mg g-1", "mgg1", "mg/gram", "mg.g-1")
_reg("mg/g", 1e-3, "ug/g", "ug g-1", "ugg-1", "ug/gram")
_reg("mg/g", 1e3, "g/g")
_reg("degC", 1.0, "degc", "deg c", "c", "celsius", "degrees c", "degree c", "oc")
_reg("%", 1.0, "%", "percent", "pct", "wt%", "w/w%", "%w/w", "%rh", "% rh")
_reg("ppm", 1.0, "ppm", "ul/l", "ul l-1", "uL/L", "ppmv", "nl/l")
_reg("h", 1.0, "h", "hr", "hrs", "hour", "hours")
_reg("h", 24.0, "d", "day", "days")
_reg("h", 1 / 60.0, "min", "mins", "minute", "minutes")
_reg("h", 168.0, "week", "weeks", "wk")
_reg("MPa", 1.0, "mpa", "n/mm2")
_reg("MPa", 1e-3, "kpa")
_reg("mm", 1.0, "mm")
_reg("L", 1.0, "l", "liter", "litre", "liters", "litres", "dm3")
_reg("L", 1e-3, "ml", "cm3")
_reg("kg", 1.0, "kg")
_reg("kg", 1e-3, "g", "gram", "grams")
_reg("logCFU/g", 1.0, "log cfu/g", "logcfu/g", "log10 cfu/g", "log cfu g-1")
_reg("g/m2/day", 1.0, "g/m2/day", "g m-2 day-1", "g/m2 d", "g/(m2 day)", "gm-2d-1")
_reg("cm3/m2/day", 1.0, "cm3/m2/day", "cm3 m-2 day-1", "cc/m2/day")
_reg("umol/kg/h", 1.0, "umol/kg/h", "umol kg-1 h-1", "umol/kg h")
_reg("nL/g/h", 1.0, "nl/g/h", "nl g-1 h-1", "nl/gh")

_QTY_RE = re.compile(
    r"(?<![\w.])(\d{1,6}(?:[.,]\d+)?)"          # magnitude
    r"(?:\s*(?:\+/-|\+-)\s*\d+(?:[.,]\d+)?)?"    # optional tolerance
    r"\s*"
    r"([a-z%][a-z0-9%/.\- ]{0,14}?)?"            # optional unit
    r"(?![\w])"
)


def norm_text(s: str) -> str:
    """Fold unicode, case, and punctuation so scientific text compares sanely."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(_CHAR_MAP.get(ch, ch) for ch in s)
    s = s.lower()
    s = re.sub(r"[̀-ͯ]", "", s)
    s = re.sub(r"[^\w%/.\-+']", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_loose(s: str) -> str:
    """As norm_text but also drops intra-word hyphens.

    '1-methylcyclopropene' and '1 methylcyclopropene' must compare equal.
    """
    return re.sub(r"\s+", " ", norm_text(s).replace("-", " ")).strip()


def canon_unit(raw: str) -> tuple[float, str]:
    """Map a printed unit onto (multiplier, canonical unit). ('',) if unknown."""
    u = norm_text(raw).replace(" deg ", "deg").strip(" .")
    u = u.replace("^", "").replace("−", "-")
    if not u:
        return (1.0, "")
    if u in _UNIT_TABLE:
        return _UNIT_TABLE[u]
    squashed = u.replace(" ", "")
    if squashed in _UNIT_TABLE:
        return _UNIT_TABLE[squashed]
    for key in sorted(_UNIT_TABLE, key=len, reverse=True):
        if squashed.startswith(key.replace(" ", "")):
            return _UNIT_TABLE[key]
    return (1.0, "")


def parse_quantities(text: str) -> list[tuple[float, str, int]]:
    """Every (magnitude_in_canonical_units, canonical_unit, position) in text."""
    out: list[tuple[float, str, int]] = []
    norm = norm_text(text)
    for m in _QTY_RE.finditer(norm):
        try:
            mag = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        mult, unit = canon_unit(m.group(2) or "")
        out.append((mag * mult, unit, m.start()))
        if unit and mult != 1.0:
            out.append((mag, unit, m.start()))  # also keep the as-printed value
    return out


def find_span(needle: str, hay: str, min_ratio: float = 0.90) -> tuple[int, int] | None:
    """Locate `needle` in `hay` allowing for OCR/whitespace drift."""
    if not needle or not hay:
        return None
    n, h = norm_loose(needle), norm_loose(hay)
    if not n:
        return None
    idx = h.find(n)
    if idx >= 0:
        return (idx, idx + len(n))
    if len(n) < 12:
        return None
    matcher = difflib.SequenceMatcher(None, h, n, autojunk=False)
    match = matcher.find_longest_match(0, len(h), 0, len(n))
    if match.size >= max(12, int(len(n) * min_ratio)):
        return (match.a, match.a + match.size)
    return None


def quote_for_value(value: str, evidence: str, window: int = 130) -> str | None:
    """Derive a quote from the source by locating the value itself.

    Models paraphrase their quotes even when told not to, and PDF text carries
    odd spacing ("7.5*10cm"), so a quote can fail to match while the value it
    supports is plainly present. Blanking those loses real data.

    The guarantee is unchanged: the *value* must still be found in the document.
    This only re-derives the surrounding sentence from the source, so what ships
    is still the source's own wording — never the model's paraphrase.
    """
    if not value or not evidence:
        return None
    span = find_span(value, evidence, min_ratio=0.95)
    if span is None:
        return None
    norm_ev = norm_loose(evidence)
    if not norm_ev:
        return None
    ratio = len(evidence) / len(norm_ev)
    start = max(0, int(span[0] * ratio) - window)
    end = min(len(evidence), int(span[1] * ratio) + window)
    return " ".join(evidence[start:end].split())[:400] or None


def repair_quote(quote: str, evidence: str) -> str | None:
    """Return the exact source span the model's quote refers to, or None.

    Models paraphrase quotes even when told not to. Rather than reject those
    outright, we locate the span they meant and store the source's own wording,
    so what ships is always the source's text.
    """
    if not quote or not evidence:
        return None
    if quote in evidence:
        return quote
    span = find_span(quote, evidence)
    if span is None:
        return None
    # Map the normalized span back onto raw evidence proportionally, then widen
    # to sentence-ish boundaries so the stored quote reads naturally.
    norm_ev = norm_loose(evidence)
    if not norm_ev:
        return None
    ratio = len(evidence) / len(norm_ev)
    start = max(0, int(span[0] * ratio) - 40)
    end = min(len(evidence), int(span[1] * ratio) + 40)
    snippet = evidence[start:end].strip()
    return " ".join(snippet.split())[:400] or None


def context_supports(field: str, evidence: str, position: int, window: int = 140) -> bool:
    """Does a field keyword sit near the matched number?"""
    keys = schema.NUMERIC_CONTEXT.get(field)
    if not keys:
        return True
    norm = norm_text(evidence)
    lo = max(0, position - window)
    hi = min(len(norm), position + window)
    ctx = norm[lo:hi]
    return any(k in ctx for k in keys)


def grounded_number(value: str, unit: str, evidence: str, field: str) -> tuple[bool, list[str]]:
    """Magnitude + canonical unit must match a quantity in the evidence."""
    checks: list[str] = []
    wanted = parse_quantities(f"{value} {unit}".strip())
    if not wanted:
        return (False, ["no_parsable_quantity"])
    have = parse_quantities(evidence)
    if not have:
        return (False, ["evidence_has_no_quantities"])
    for mag, u, _ in wanted:
        for hmag, hu, pos in have:
            if abs(hmag - mag) > max(1e-6, abs(mag) * 0.005):
                continue
            checks.append("number_found")
            if u and hu and u != hu:
                continue
            if u and hu and u == hu:
                checks.append("unit_match")
            if not context_supports(field, evidence, pos):
                checks.append("context_reject")
                continue
            checks.append("context_ok")
            return (True, checks)
    return (False, checks or ["no_magnitude_match"])


def grounded_phrase(value: str, evidence: str) -> tuple[bool, list[str]]:
    """Substring, then token-prefix, then content-overlap — loosening in order."""
    if not value:
        return (False, ["empty"])
    n_val, n_ev = norm_loose(value), norm_loose(evidence)
    if n_val and n_val in n_ev:
        return (True, ["substring"])
    tokens = [t for t in n_val.split() if len(t) > 2]
    if not tokens:
        return (False, ["no_content_tokens"])
    if len(tokens) >= 3 and " ".join(tokens[:3]) in n_ev:
        return (True, ["token_prefix"])
    hit = sum(1 for t in tokens if t in n_ev)
    if hit / len(tokens) >= 0.8:
        return (True, [f"token_overlap:{hit}/{len(tokens)}"])
    return (False, [f"token_overlap:{hit}/{len(tokens)}"])


def _numbers_in(text: str) -> set[float]:
    return {q[0] for q in parse_quantities(text)}


def ground_cell(field: str, raw_cell: dict, evidence: str, level_if_found: str,
                mode: str, has_full_text: bool) -> dict:
    """Ground one model-proposed cell. Returns a schema cell dict."""
    value = str(raw_cell.get("value") or "").strip()
    unit = str(raw_cell.get("unit") or "").strip()
    quote = str(raw_cell.get("quote") or "").strip()
    locator = str(raw_cell.get("where") or raw_cell.get("locator") or "").strip()[:40]

    if not value or value.lower() in ("not stated", "not_stated", "none", "n/a", "na", "null"):
        level, status = schema.resolve_missing(has_full_text)
        return schema.new_cell(level=level, status=status, locator=locator)

    if mode == "metadata":
        return schema.new_cell(value=value, unit=unit, raw=value,
                               level="metadata_only", status="grounded_verbatim")

    repaired = repair_quote(quote, evidence)
    derived = False
    if repaired is None:
        # The quote missed, but the value may still be plainly in the source.
        # Re-derive the quote from the document rather than discard real data;
        # the value check below is the actual guard against fabrication.
        repaired = quote_for_value(value, evidence)
        derived = repaired is not None
    if repaired is None:
        return schema.new_cell(
            raw=value, quote="", locator=locator, level="unverifiable",
            status="ungrounded_blanked", checks=["quote_not_locatable"])

    if derived:
        checks = ["quote_derived_from_value"]
    else:
        checks = ["quote_repaired"] if repaired != quote else ["quote_exact"]
    ok = False
    status = "ungrounded_blanked"

    if mode == "numeric":
        ok, more = grounded_number(value, unit, evidence, field)
        checks += more
        status = "grounded_numeric" if ok else "ungrounded_blanked"
    elif mode == "controlled":
        allowed = schema.FIELD_ENUMS.get(field, set())
        value = schema.pick(value, allowed, "not_stated") if allowed else value
        ok = value not in ("not_stated", "")
        checks.append("enum_clamped")
        status = "grounded_controlled" if ok else "not_stated"
    elif mode == "inference":
        # The appraisal may paraphrase, but it may not introduce a number the
        # quote does not contain — that is where invented precision creeps in.
        extra = _numbers_in(value) - _numbers_in(repaired) - _numbers_in(evidence)
        ok = not extra
        checks.append("no_new_numbers" if ok else f"invented_numbers:{sorted(extra)[:3]}")
        status = "inference_from_quote" if ok else "ungrounded_blanked"
    else:  # phrase
        ok, more = grounded_phrase(value, repaired + " " + evidence)
        checks += more
        status = "grounded_verbatim" if ok else "ungrounded_blanked"

    if not ok and status == "ungrounded_blanked":
        return schema.new_cell(raw=value, quote=repaired, locator=locator,
                               level="unverifiable", status=status, checks=checks)
    if status == "not_stated":
        level, status = schema.resolve_missing(has_full_text)
        return schema.new_cell(quote=repaired, locator=locator, level=level, status=status)

    return schema.new_cell(value=value, unit=unit, raw=str(raw_cell.get("value") or ""),
                           quote=repaired, locator=locator, level=level_if_found,
                           status=status, checks=checks)


_JUNK_UNITS = {"", "n/a", "na", "not stated", "not_stated", "none", "null", "-",
               "not applicable", "unitless", "dimensionless"}


def ground_row(raw: dict, evidence: str, level_if_found: str, modes: dict[str, str],
               keys: list[str], has_full_text: bool) -> tuple[dict, dict[str, dict]]:
    """Ground a whole extracted row. Returns (flat_row, cells)."""
    cells: dict[str, dict] = {}
    flat: dict[str, str] = {}
    for key in keys:
        mode = modes.get(key, "phrase")
        raw_cell = raw.get(key)
        if not isinstance(raw_cell, dict):
            raw_cell = {"value": raw_cell} if raw_cell else {}
        cell = ground_cell(key, raw_cell, evidence, level_if_found, mode, has_full_text)
        # A unit only means anything on a numeric field. Models routinely return
        # "N/A" or "not stated" in the unit slot for text fields, which would
        # otherwise be concatenated into the value ("low N/A", "core not stated").
        if mode != "numeric" or norm_text(cell["unit"]) in _JUNK_UNITS:
            cell["unit"] = ""
        cells[key] = cell
        unit = cell["unit"]
        flat[key] = f"{cell['value']} {unit}".strip() if cell["value"] else ""
    return flat, cells
