"""The search grid, built from the concepts named in the research brief.

Two design points worth stating:

* Queries are boolean strings for OpenAlex's `title_and_abstract.search`, which
  needs explicit AND/OR. Commas are forbidden — OpenAlex reads a comma as a
  filter separator and would silently truncate the query.
* The grid deliberately includes an "analogue" band that does not mention 1-MCP
  at all (humidity-triggered release of any volatile active, CNC Pickering
  films, essential-oil packaging). Those papers are what the architecture and
  mechanism sections need; a grid anchored only on 1-MCP would miss the whole
  materials-science half of the question.
"""
from __future__ import annotations

MCP = '("1-methylcyclopropene" OR "1-MCP")'

# Literature: (band, boolean query). Bands drive screening emphasis and let the
# coverage report show which part of the question each paper answers.
LIT_GRID: list[tuple[str, str]] = [
    # --- core: 1-MCP delivery and release -------------------------------------
    ("mcp_release",    f'{MCP} AND ("controlled release" OR "sustained release" OR "slow release")'),
    ("mcp_release",    f'{MCP} AND ("delayed release" OR "release kinetics" OR "release rate")'),
    ("mcp_humidity",   f'{MCP} AND (humidity OR moisture OR "relative humidity" OR "water activity")'),
    ("mcp_humidity",   f'{MCP} AND ("moisture activated" OR "humidity triggered" OR "humidity responsive")'),
    ("mcp_carrier",    f'{MCP} AND (cyclodextrin OR "inclusion complex" OR encapsulation)'),
    ("mcp_carrier",    f'{MCP} AND ("alpha-cyclodextrin" OR "beta-cyclodextrin" OR nanosponge)'),
    ("mcp_carrier",    f'{MCP} AND ("metal-organic framework" OR MOF OR silica OR zeolite OR halloysite)'),
    ("mcp_format",     f'{MCP} AND (film OR coating OR "coated paper" OR paperboard OR packaging)'),
    ("mcp_format",     f'{MCP} AND (sachet OR label OR sticker OR patch OR insert OR liner OR pad)'),
    ("mcp_format",     f'{MCP} AND (fiber OR fibre OR electrospun OR nonwoven OR "nanofiber")'),
    ("mcp_measure",    f'{MCP} AND ("gas chromatography" OR headspace OR "GC-FID" OR "GC-MS")'),
    ("mcp_polymer",    f'{MCP} AND (chitosan OR starch OR alginate OR cellulose OR "polyvinyl alcohol")'),
    ("mcp_produce",    f'{MCP} AND (climacteric OR postharvest OR ripening OR "ethylene inhibitor")'),
    ("mcp_produce",    f'{MCP} AND (apple OR pear OR tomato OR banana OR avocado OR peach OR mango OR kiwifruit)'),
    ("mcp_produce",    f'{MCP} AND ("shelf life" OR firmness OR "quality retention" OR decay)'),
    ("mcp_combo",      f'{MCP} AND ("essential oil" OR thymol OR carvacrol OR eugenol OR antimicrobial)'),
    ("mcp_scaleup",    f'{MCP} AND (coating OR extrusion OR printing OR "roll-to-roll" OR industrial)'),
    ("mcp_stability",  f'{MCP} AND (stability OR storage OR retention OR "shelf stability" OR loss)'),

    # --- analogue band: mechanism and materials without 1-MCP -----------------
    ("humid_release",  '("humidity triggered" OR "moisture activated" OR "humidity responsive") '
                       'AND (release OR packaging OR film OR coating)'),
    ("humid_release",  '("controlled release" OR "sustained release") AND volatile '
                       'AND (packaging OR film OR coating OR sachet)'),
    ("cd_volatile",    'cyclodextrin AND ("inclusion complex" OR encapsulation) '
                       'AND (thymol OR carvacrol OR eugenol OR "essential oil") AND release'),
    ("cnc_pickering",  '("cellulose nanocrystal" OR "cellulose nanocrystals" OR nanocellulose) '
                       'AND "Pickering emulsion" AND ("essential oil" OR thymol OR carvacrol)'),
    ("cnc_pickering",  '"Pickering emulsion" AND (film OR coating) AND (antimicrobial OR "active packaging")'),
    ("chitosan_cnc",   'chitosan AND ("cellulose nanocrystal" OR nanocellulose) '
                       'AND (film OR coating) AND (antimicrobial OR mechanical OR barrier)'),
    ("eo_packaging",   '("essential oil" OR thymol OR carvacrol OR eugenol OR cinnamaldehyde) '
                       'AND "active packaging" AND (release OR "vapour phase" OR "vapor phase")'),
    ("eo_packaging",   '(thymol OR carvacrol) AND (antimicrobial OR antifungal) '
                       'AND (postharvest OR fruit OR vegetable)'),
    ("paper_coating",  '("coated paper" OR paperboard OR "cellulose film") '
                       'AND ("active packaging" OR antimicrobial OR "controlled release")'),
    ("scaleup",        '("roll-to-roll" OR "gravure coating" OR flexographic OR "slot-die" '
                       'OR "extrusion coating") AND (active OR antimicrobial OR functional) AND coating'),
    ("kinetics",       '("Korsmeyer-Peppas" OR Higuchi OR Weibull OR "release kinetics") '
                       'AND (film OR coating OR packaging) AND volatile'),
]

# Patents. Plain keyword strings — Google Patents and Tavily site: search both
# handle quoted phrases but not the OpenAlex boolean grammar.
PAT_GRID: list[tuple[str, str]] = [
    ("mcp_carrier",   '"1-methylcyclopropene" cyclodextrin'),
    ("mcp_carrier",   '"1-methylcyclopropene" inclusion complex encapsulation'),
    ("mcp_release",   '"1-methylcyclopropene" controlled release packaging'),
    ("mcp_release",   '"1-methylcyclopropene" delayed release differential release'),
    ("mcp_humidity",  '"1-methylcyclopropene" humidity moisture activated release'),
    ("mcp_format",    '"1-methylcyclopropene" film coating paper label'),
    ("mcp_format",    '"1-methylcyclopropene" sachet insert pad liner packaging'),
    ("mcp_generator", '"1-methylcyclopropene" generator release composition'),
    ("mcp_combo",     '"1-methylcyclopropene" essential oil antimicrobial'),
    ("mcp_produce",   '"1-methylcyclopropene" fruit ripening ethylene packaging'),
    ("cd_volatile",   'cyclodextrin volatile release packaging humidity'),
    ("eo_packaging",  'essential oil cyclodextrin antimicrobial packaging release'),
    ("eo_ethylene",   'ethylene inhibitor essential oil packaging fruit'),
    ("pickering",     'Pickering emulsion cellulose nanocrystal active packaging'),
    ("chitosan_cnc",  'chitosan cellulose nanocrystal antimicrobial film packaging'),
    ("bilayer",       'bilayer multilayer antimicrobial packaging controlled release volatile'),
    ("humid_release", 'moisture activated humidity responsive volatile release packaging'),
    ("rolltoroll",    'roll-to-roll coating active packaging volatile release'),
]


def literature_queries() -> list[dict]:
    return [{"query_id": f"lit-{i:03d}", "band": band, "query": q, "kind": "work"}
            for i, (band, q) in enumerate(LIT_GRID)]


def patent_queries() -> list[dict]:
    return [{"query_id": f"pat-{i:03d}", "band": band, "query": q, "kind": "patent"}
            for i, (band, q) in enumerate(PAT_GRID)]


def all_queries() -> list[dict]:
    return literature_queries() + patent_queries()
