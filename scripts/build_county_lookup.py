"""Build an authoritative Georgia city -> county lookup, cached to data/ga_city_county.json.

Source: the Wikipedia "List of municipalities in Georgia (U.S. state)" table, whose
County column cites the U.S. Census. Run once; collect_locations.py then resolves the
County field deterministically in code instead of asking the model to recall it.

A city spanning several counties is stored as "Fulton/DeKalb".

Usage:
    python scripts/build_county_lookup.py            # writes data/ga_city_county.json
    python scripts/build_county_lookup.py --show Dahlonega
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = PKG_ROOT / "data" / "ga_city_county.json"

WIKI_API = ("https://en.wikipedia.org/w/api.php?action=parse"
            "&page=List_of_municipalities_in_Georgia_(U.S._state)"
            "&prop=wikitext&format=json&formatversion=2")
UA = "gnem-location-research/1.0"

# | scope="row" ...|[[Abbeville, Georgia|Abbeville †]]||City||[[Wilcox County, Georgia|Wilcox]]||...
ROW_RE = re.compile(r'\|\s*scope="row"[^|]*\|(.+?)\|\|([^|]*)\|\|(.+?)\|\|', re.DOTALL)
LINK_RE = re.compile(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]")


def _clean(text: str) -> str:
    """Display text of a wiki link, minus templates and county-seat markers.

    Rows mark the state capital and county seats with templates inside the link text,
    e.g. [[Atlanta|Atlanta {{double-dagger|alt=State capital}}]] — strip those or the
    city key comes out unusable."""
    m = LINK_RE.search(text)
    val = m.group(1) if m else text
    val = re.sub(r"\{\{[^{}]*\}\}", " ", val)          # templates
    val = re.sub(r"[†‡*]", " ", val).replace("'''", "")  # dagger markers, bolding
    return re.sub(r"\s+", " ", val).strip()


def fetch_wikitext() -> str:
    req = urllib.request.Request(WIKI_API, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))["parse"]["wikitext"]


def parse(wikitext: str) -> dict[str, str]:
    """city (lowercase) -> county name(s), '/'-joined for multi-county municipalities."""
    out: dict[str, str] = {}
    for raw_city, _type, raw_county in ROW_RE.findall(wikitext):
        city = _clean(raw_city)
        counties = [_clean(f"[[{c}]]" if "[[" not in c else c)
                    for c in re.findall(r"\[\[[^\]]+\]\]", raw_county)]
        counties = [re.sub(r"\s+County$", "", c).strip() for c in counties if c]
        if not city or not counties:
            continue
        key = city.lower().strip()
        if key and key not in out:
            out[key] = "/".join(dict.fromkeys(counties))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--show", default=None, help="print the county for one city and exit")
    args = ap.parse_args()

    if args.show and args.out.exists():
        data = json.loads(args.out.read_text(encoding="utf-8"))
        print(f"{args.show}: {data.get(args.show.lower(), '(not found)')}")
        return

    mapping = parse(fetch_wikitext())
    if len(mapping) < 400:  # Georgia has ~535 municipalities; a short table means a parse break
        raise SystemExit(f"only parsed {len(mapping)} cities — the source table layout "
                         f"probably changed; not overwriting {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(mapping, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(mapping)} Georgia cities -> {args.out}")
    for probe in ("dahlonega", "cairo", "sylvania", "pendergrass", "lavonia"):
        print(f"  {probe:14s} -> {mapping.get(probe, '(not found)')}")


if __name__ == "__main__":
    main()
