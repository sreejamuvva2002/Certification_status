# 6. Patent-family landscape

> **This is a technical prior-art map, not a legal analysis.** No conclusion about
> freedom to operate, infringement, validity or patentability is expressed or
> implied, and none should be inferred. Those determinations require
> claim-by-claim review by qualified patent counsel, including a search of
> unexamined applications that this review could not access.

## 6.1 Retrieval and its limits

Patent discovery ran through site-restricted web search after Google Patents'
search endpoint blocked this IP; full documents, including complete claim text
and priority/family tables, were retrieved through an independent crawler.
Metadata was extracted from those documents and grounded against them.

Three limits are carried into the table and should be read with it:

* **Families are clustered heuristically** on title, assignee and priority date.
  INPADOC family data was not available, so the family column reports the members
  **observed**, not an authoritative family definition.
* **Legal status is not reported.** Google Patents' own status field carries an
  explicit disclaimer that it is not a legal conclusion, and no independent source
  (EPO OPS, PatentsView) was reachable. A column of unverified statuses would
  invite exactly the misreading this section warns against.
* **Only published documents are visible.** Applications not yet published are, by
  definition, absent — and in a commercially active field, that is a material gap.

## 6.2 Prior-art map — the shape of the field

Retrieved families cluster into five groups:

**A. 1-MCP/cyclodextrin complexes and their articles.** The core, and the most
consolidated. Patents originally prosecuted by Cellresin Technologies now list
**Verdant Technologies LLC** as current assignee — the company that also sells
HarvestHold Fresh. AgroFresh holds the foundational complex claim (`US6017849A`,
1998, cited on the SmartFresh InBox label) and film/coating claims. This group
contains the closest art to the recommended architecture.

**B. Release-control of volatiles from polymer matrices, fibres, films and
sheets.** Broader than 1-MCP but frequently reciting it, including Chinese
families explicitly covering ripening-inhibitor release from polymers, fibres,
films, sheets or packaging.

**C. 1-MCP formulations and generators.** Powders, liquids, tablets, generators —
the delivery chemistry rather than the packaging article.

**D. Essential-oil and antimicrobial active packaging**, including
cyclodextrin-encapsulated oils. Heavily crowded and largely independent of the
1-MCP art.

**E. Ethylene management generally** — absorbers, scavengers, modified atmosphere.
Adjacent context rather than direct prior art.

The proposed concept sits in the **intersection of A and B**, which is the most
densely occupied region of the map.

## 6.3 Claim-element matrix

Elements of the proposed concept against where each is already disclosed:

| Element | Disclosure status | Where |
|---|---|---|
| 1-MCP complexed with α-cyclodextrin | **Extensively disclosed** | Cellresin family; Chinese families; commercial products (SmartFresh, AnsiP-G, EasyFresh) |
| Cyclodextrin composition **coated on a substrate** | **Extensively disclosed** | `US10212931B2`; `US20210331990A1` |
| Second substrate over the coating (laminate) | **Disclosed** | `US10212931B2` claim 1 |
| Moisture/humidity as release trigger | **Extensively disclosed** | Across group A and B; intrinsic to α-CD complexes |
| Paper / sheet / insert format | **Extensively disclosed** + **commercial** | Group B; HarvestHold Fresh |
| Label / sticker format | **Disclosed** + **commercial** | Vidre+ |
| Delayed / differential / sequential release | **Disclosed** | `US20210331990A1`; commercially claimed by Vidre+ |
| Essential oil + ethylene inhibitor together | **Disclosed in a different form** | Cao et al. (2024) in the literature; group D patents |
| CNC-stabilised Pickering emulsion packaging | **Disclosed in a different material system** | Group D; not combined with 1-MCP in retrieved art |
| Coated substrate + 1-MCP/α-CD clathrate coating | **Already claimed** | `US20210331990A1` (Verdant, 2020-04-27) |
| Film containing a cyclopropene/cyclodextrin complex | **Already claimed** | `US8603524B2` (AgroFresh, 2007) |
| Coatings/films for vapour-phase 1-MCP release | **Already claimed** | `PH12016500070A1` (AgroFresh, 2013) |
| 1-MCP carrier **with optional essential oils** | **Already claimed** | `US20190037839A1` (Hazel, 2016) |
| **Specified RH activation threshold with a defined release window** | **Uncertain — requires further searching** | Not found in retrieved art; absence is weak evidence |
| **Defined coat weight (g·m⁻²) tied to delivered dose** | **Uncertain — requires further searching** | Not found in retrieved art |
| **Dose reproducibility across package volume / produce mass** | **Uncertain — requires further searching** | Not found in retrieved art |

## 6.4 Novelty-risk classification

Per the brief's requested categories:

| Feature | Classification |
|---|---|
| 1-MCP/CD on paper | **Already extensively disclosed** |
| Humidity trigger | **Already extensively disclosed** |
| Insert / label / sachet format | **Already extensively disclosed** — and commercial |
| Delayed-onset release | **High patent-overlap risk** |
| Two-stage / sequential release | **High patent-overlap risk** |
| Bilayer with a moisture-control topcoat | **High patent-overlap risk** — approaches the `US10212931B2` laminate |
| Spatial separation of 1-MCP and essential oil | **Disclosed but not well demonstrated** |
| CNC Pickering + 1-MCP in one article | **Disclosed only in a different material system** |
| Low-temperature / water-free manufacture | **Disclosed but not well demonstrated** — Cao et al. use it; the quantitative retention relationship is not reported |
| Defined binder:cyclodextrin ratio | **Uncertain — requires further searching** |
| Defined coat weight tied to dose | **Potentially differentiating** |
| Specified RH threshold + release window | **Potentially differentiating** |
| Dose control across variable package volume | **Potentially differentiating** |
| Repulpable paper-based design | **Disclosed but not well demonstrated** |

## 6.5 Design-around analysis (technical, not legal)

* **The laminate design-around is not sufficient on its own.** Avoiding the
  *second substrate* of `US10212931B2` does nothing about `US20210331990A1`
  (Verdant, 2020-04-27), which claims a coated substrate whose coating consists
  essentially of a 1-MCP clathrate of α-cyclodextrin — no second substrate
  required. Any design-around must clear that claim first.
* **Claim a specification and a method, not an article.** The article space is
  occupied. A method of achieving a specified headspace concentration by selecting
  coat weight and binder to a defined RH threshold is a different kind of claim.
* **Do not build the differentiator on delay.** It is commercially claimed and
  separately titled in a published application.
* **Keep the essential oil out of v1**, which also keeps the disclosure clear of
  the crowded group D art.

## 6.6 White-space analysis

The credible white space is not a material or a format. It is **quantitative
specification**: threshold, coat weight, delivered dose, reproducibility.

Its weakness must be stated plainly: this is an *absence in retrieved, published*
art. Incumbents plausibly hold this data internally, and unpublished applications
were not searchable. A white space defined by what companies have not published
is the weakest kind, and should be verified by a professional search before any
resource is committed on the strength of it.

## 6.7 The table

<!-- TABLE: patents -->
