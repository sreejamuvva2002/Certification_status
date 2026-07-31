# 7. Scientific compatibility assessment

The brief asks a specific question: should 1-MCP and an essential oil sit in the
same layer, in separate layers, or should the oil be omitted at first? And does
the CNC-stabilised Pickering emulsion add genuine functional value or just
complexity?

## 7.1 The governing physical conflict

Everything else follows from one asymmetry:

**The 1-MCP/α-cyclodextrin complex is discharged by water.** That is its release
mechanism — it is not a side effect to be engineered around, it is the product's
operating principle. Cao et al. (2024) state it directly from their own
measurements:

> "1-MCP-α-CD is sensitive to high moisture, which may result in the complete
> release of 1-MCP gas in a short period of time."

**Therefore every processing step that introduces water is a step that partially
discharges the product before it ships.** This single fact disqualifies most of
the proposed starting formulation.

| Proposed element | Interaction with that fact |
|---|---|
| Aqueous film casting | Immerses the complex in bulk water — the maximal-release condition |
| Chitosan matrix | Hygroscopic; draws in the very water that triggers release, in storage as well as in use |
| Chitosan processing | Requires acidic aqueous solution (typically acetic acid) — water plus a reactive environment |
| CNC-stabilised Pickering emulsion | An **oil-in-water** emulsion: its continuous phase is water |
| Drying to remove that water | Heat, applied to a thermally labile complex, for a prolonged period |

The Pickering emulsion is the sharpest case. Its whole function is to stabilise
an oil phase *in water*. Adding it to a formulation whose central engineering
problem is excluding water is working directly against the design intent.

## 7.2 Does the Pickering emulsion earn its place?

Assessed on its merits rather than dismissed:

**Genuine benefits, which are real:** it stabilises a volatile oil without
surfactants, reduces oil coalescence, can slow essential-oil release, and CNC can
improve film mechanics and tortuosity.

**Costs in this specific application:**

* It requires an aqueous continuous phase (Section 7.1).
* It adds two materials (CNC, oil) and at least two process steps
  (emulsification, then stabilisation) before coating.
* It requires its own stability programme — droplet size, zeta potential,
  creaming, coalescence on storage — none of which relates to 1-MCP performance.
* CNC at commercial scale is expensive relative to the alternatives, and this
  application does not need its distinctive properties.
* It complicates drying, regulatory review, and the patent position (CNC
  Pickering active-packaging films are themselves a crowded area).

**Verdict: not justified in v1.** The emulsion solves a problem — delivering an
essential oil in a stable aqueous coating — that the product does not have if the
essential oil is deferred. It is a well-engineered answer to the wrong question.
It should be reconsidered only if (a) the antimicrobial function proves necessary,
**and** (b) a water-based coating proves acceptable for 1-MCP retention, **and**
(c) simpler oil-delivery routes (oil/β-CD inclusion powder, as Cao et al. used)
prove inadequate.

Note that Cao et al. achieved the dual-active coated paper **without** a Pickering
emulsion, by using a separate β-CD inclusion for carvacrol. That is the simpler
precedent, and it works.

## 7.3 Same layer or separate layers?

If an essential oil is used at all, four mechanisms argue against co-locating it
with the 1-MCP complex:

1. **Cavity competition.** Cyclodextrin inclusion is competitive. Thymol,
   carvacrol and eugenol are all well-documented cyclodextrin guests. A free oil
   molecule adjacent to a loaded 1-MCP/α-CD complex is a plausible displacement
   risk. α-CD's small cavity affords partial protection — it fits 1-MCP well and
   bulky phenolics poorly — but the risk is real enough not to design into v1
   without data. *This is a mechanistic argument; no retrieved study measured
   direct displacement of 1-MCP by an essential oil, which is itself a gap.*
2. **Partitioning into the oil phase.** 1-MCP is a small non-polar hydrocarbon.
   A lipophilic oil domain in the same layer is a sink it can dissolve into,
   attenuating headspace delivery — the quantity the product is sold on.
3. **Divergent release requirements.** Antimicrobial action wants early, sustained
   vapour output. Ethylene inhibition wants a controlled dose delivered inside a
   defined window. Optimising one layer for both compromises both.
4. **Plasticisation.** Essential oils commonly increase film free volume and
   water-vapour permeability. In this system that directly accelerates 1-MCP
   release — a coupled failure where the antimicrobial degrades the primary
   function.

**If both actives are required: separate layers, oil on the outside, 1-MCP
underneath.** That keeps the oil away from the complex and puts the antimicrobial
nearer the headspace. This is Architecture B, and it carries its own patent
concern (Section 9.4).

## 7.4 Is chitosan's antimicrobial contribution sufficient?

Chitosan is genuinely antimicrobial, but by **contact**, requiring protonation at
acidic pH. In a **non-contact insert** there is no contact and no wet acidic
interface, so the mechanism cannot operate. Chitosan therefore contributes
essentially nothing antimicrobial in the recommended architecture, while
contributing hygroscopicity that actively harms it.

This is a clean argument for omitting chitosan — not on cost, but on mechanism.

## 7.5 Does the essential oil justify its complexity at all?

Costs: sensory taint risk on peach and apple at effective vapour doses; a second
regulatory conversation; oxidation and volatility during drying and storage;
batch-to-batch variability in a natural product; accelerated 1-MCP release via
plasticisation; and additional patent crowding.

Benefit: decay control, which for stone fruit (brown rot, *Monilinia*) is
commercially significant — Cao et al. demonstrated activity against *Monilinia
fructicola*.

**Recommendation: omit in v1, keep as a planned v2 module.** The brief explicitly
asks that this be tested rather than assumed, and the evidence supports omission:
the antimicrobial does not address the project's central unsolved problem
(reproducible 1-MCP dose control), while adding the sensory and regulatory risks
most likely to kill a produce product. Establish the 1-MCP system, then add the
oil as a separate layer with its own evidence — including a sensory panel before
any scale-up.

## 7.6 Summary of material decisions

| Material | v1 | Reason |
|---|---|---|
| 1-MCP/α-CD complex | **Keep** | The active; α-CD's small cavity is also the best protection against guest competition |
| Paper / paperboard | **Keep** | Cheap, repulpable, coatable on existing lines |
| Binder (PEG, shellac, or latex) | **Keep** | The actual release-control lever |
| Chitosan | **Drop** | Hygroscopic; acidic processing; antimicrobial mechanism inoperative in a non-contact insert |
| CNC | **Drop** | Solves a problem the simplified design does not have; expensive at scale |
| Pickering emulsion | **Drop** | Requires the aqueous phase the design exists to avoid |
| Essential oil | **Defer to v2** | Real benefit, but wrong problem first, and carries the highest sensory/regulatory risk |

Seven materials become three. Every removal is justified by a mechanism, not by
preference.
