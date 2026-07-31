# 9. Recommended architecture

## 9.1 Primary recommendation — Architecture C·1: single-layer 1-MCP coated paper insert

**Format.** A rectangular coated-paper insert, placed in the package but not
required to contact the fruit, sized to the package by area.

**Layer structure.**

| Layer | Function |
|---|---|
| Protective overwrap (removed at packing) | Keeps the insert below its activation humidity until use. **This is a component of the product, not packaging** — the shelf-stability problem is otherwise unsolved. |
| Coating (one layer, one side) | Binder + 1-MCP/α-cyclodextrin complex. The binder sets how fast water reaches the complex; the complex holds the payload. |
| Paper / paperboard base | Structure, repulpability, coat-weight control. |

**Deliberate omissions, and why each is a decision rather than an oversight:**

* **No essential oil in v1.** Section 12 sets out the case; briefly, it adds a
  sensory risk on peach and apple, a second regulatory conversation, a possible
  competition for cyclodextrin cavities, and — critically — it does not fix the
  problem the product exists to solve. Establish 1-MCP dose control first. The
  brief explicitly asks that this option be tested rather than assumed.
* **No chitosan.** It is hygroscopic, which is exactly wrong for a payload
  discharged by moisture, and it requires acidic processing. Its antimicrobial
  contribution is not needed in a non-contact insert.
* **No CNC and no Pickering emulsion.** With no oil phase to stabilise, a
  Pickering emulsion has nothing to do. CNC's tortuosity benefit is real but is
  a solution to a problem (barrier control) that coat weight and binder choice
  address more cheaply.
* **No bilayer in v1.** A moisture-control topcoat is the first upgrade if — and
  only if — single-layer release proves too fast. It is Architecture B, held in
  reserve.

This reduces the brief's seven starting materials to **three**: paper, binder,
1-MCP/α-CD complex.

## 9.2 Composition — proposed starting ranges

**These are experimental starting points, not literature-established values.**
They are hypotheses for a screening design, and are labelled as such. Where the
literature does anchor a number, it is marked.

| Parameter | Proposed starting range | Basis |
|---|---|---|
| Base paper grammage | 80–200 g·m⁻² | Proposed. Spans label stock to light board. |
| Coat weight (dry) | 4–20 g·m⁻² | **Proposed.** No retrieved source reports coat weight for a 1-MCP paper — this is itself a gap worth owning. |
| 1-MCP/α-CD complex in dry coating | 10–40 % w/w | Proposed. |
| Binder in dry coating | 60–90 % w/w | Proposed. |
| Nominal 1-MCP payload | 0.5–5 mg per insert | Proposed, back-calculated from the dose logic below. |
| Drying temperature | ambient–50 °C | Constrained: the payload is heat- and moisture-labile. Cao et al. (2024) adopted a water-free route for this reason. |

**Binder candidates, in the order they should be screened:**

1. **PEG** — a literature-anchored choice: Cao et al. (2024) used polyethylene
   glycol specifically to moderate 1-MCP release from α-CD. Starting with the
   published solution is the fastest route to a working baseline.
2. **Shellac or an ethanolic system** — enables a genuinely water-free coating,
   protecting the payload during manufacture.
3. **Water-based latex / HPMC** — cheapest and most industrially standard, but
   introduces the water the design is trying to avoid. Screen it, but expect it
   to be the retention risk.

**Dose logic.** 1-MCP is dosed to headspace concentration, not to insert mass:

```
required 1-MCP mass (µg) = C_target (µL·L⁻¹) × V_headspace (L) × ρ  ×  1/f_release
```

where `ρ` converts µL to µg for 1-MCP (MW 54.09) at the storage temperature, and
`f_release` is the measured fraction released within the treatment window. The
whole point of the release-kinetics programme (Section 11) is to measure
`f_release` so this equation stops being a guess. Commodity-specific target
concentrations `C_target` come from the postharvest literature, not from this
formula.

## 9.3 Trigger and diffusion pathway

Water vapour from fruit respiration raises package RH; vapour permeates the
binder; the α-CD complex hydrates; the lattice releases 1-MCP; the gas diffuses
back out through the coating into the headspace.

**Release rate is therefore controlled by the binder's water-vapour permeability
and the coat weight — not by the cyclodextrin.** That is the design lever, and
it is the one this project can actually specify. It is also why coat weight is
worth measuring precisely: it is a manufacturing parameter that maps directly
onto a release parameter, and no retrieved source reports it.

## 9.3a The format itself is not novel — and that is fine

Commercial review (Section 5) establishes that **Verdant Technologies'
HarvestHold Fresh is a 1-MCP sheet applied inside the box at packing**, sold
since late 2021 with an EPA label expansion. In commercial substance that is this
architecture.

This does not invalidate the recommendation — it corroborates it. The format wins
the matrix because it is the cheapest, most scalable and most regulatorily
tractable option, which is exactly why an incumbent already sells it. But the
format must be presented as **the right engineering choice, not as an invention**.
Any disclosure that describes "a 1-MCP-coated paper insert" as novel will meet
HarvestHold immediately.

The consequence is that the differentiator has to move down a level of
abstraction — from *what the product is* to *what it is specified to do*.

## 9.4 Proposed technical differentiator

> A coated-paper 1-MCP insert with a **specified humidity activation threshold
> and release window**, achieved by binder selection and a defined coat weight,
> delivering a **reproducible headspace 1-MCP concentration** across a stated
> range of package volumes and fruit masses — demonstrated by headspace GC
> quantification in µL·L⁻¹ and a fitted release model.

This is deliberately a claim about **dose control and measurement**, not about
materials or format, because both are taken (Sections 2 and 5). It is testable,
it is what a commercial user actually needs, and it is the gap visible in the
closest prior art — Cao et al. (2024) report no kinetic model, no GC
quantification of 1-MCP, no coat weight, and no defined activation threshold.

**Honest assessment of its strength.** This is a *weak-to-moderate*
differentiator, and it should be described that way to a technology-transfer
office rather than oversold. Its weaknesses:

* Delayed and gradual release is already claimed commercially by Fresh Inset
  (Vidre+), so "controlled release" alone is not available.
* The gap identified is an absence in *public* material. Incumbents may hold the
  same data internally and in unpublished or unexamined applications.
* A specification range can often be designed around by choosing a different
  binder or threshold.

Its strength is that it is the one thing in this space that is **demonstrable
with a modest lab programme** and that a buyer would actually pay for:
reproducible dose across real, variable packages. If the data show sharp
threshold behaviour and low replicate variance where incumbents show neither,
that is a genuine result — and if they do not, that is a clear signal to stop.

**Principal patent-overlap concern — and it is severe.**

> `US20210331990A1` (Verdant Technologies, priority 2020-04-27) claims *"A coated
> substrate comprising a coating disposed on a substrate surface, the coating
> consisting essentially of a 1-methylcyclopropene clathrate of α-cyclodextrin."*

That is this architecture. Substrate, coating, 1-MCP/α-CD — with **no second
substrate required**, so the "we are a single layer, not a laminate" distinction
that would separate this design from Kimberly-Clark's `US10212931B2` does not
help here.

The position is worse than a single document suggests. AgroFresh's `US8603524B2`
(2007) claims a film containing a cyclopropene/cyclodextrin complex in a
water-soluble polymer; `PH12016500070A1` (2013) claims coatings and films for
vapour-phase 1-MCP release; and the Cellresin estate now sits with Verdant, the
company selling the commercial 1-MCP sheet.

**This must be put to patent counsel before any formulation work begins, not
after.** The honest reading is that the *article* — a paper coated with 1-MCP/α-CD
— is not available as an invention, and quite possibly not available to practise
without a licence. What may remain is a **method and specification** claim
(Section 9.4), and even that needs professional clearance. A project that spends
a year optimising coat weight before asking this question is spending it badly.

## 9.5 Backup — simplest thing that could work

**Architecture C·0: 1-MCP/α-CD complex adsorbed onto uncoated absorbent paper,
no binder, protective sachet until use.**

Two materials. It exists to answer one question quickly: does a paper-borne
complex release measurable 1-MCP into a package headspace at realistic RH, at
all? If C·0 releases everything in the first hour, that is the strongest possible
evidence that binder control is the whole invention — which is useful, and cheap
to learn.

## 9.6 High-risk / high-reward — Architecture E·1

**A condensate-managing coated pad that releases 1-MCP only when local moisture
exceeds a threshold**, marrying an existing commodity product (absorbent produce
pads) with the active.

The reward is a genuinely differentiated function: the pad *manages* the
condensation that would otherwise cause both decay and premature release, and
uses it as the trigger. The risk is that the same wetness that makes the trigger
reliable makes it uncontrollable — local saturation could dump the payload in
minutes. It scored 4/5 on trigger reliability but that score is the least
evidence-backed in the matrix (Section 8.5), and it should not be pursued until
C has produced a release curve to compare against.
