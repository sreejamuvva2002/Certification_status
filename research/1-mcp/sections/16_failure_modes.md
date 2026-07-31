# 16. Failure modes and kill criteria

Full FMEA in `assets/fmea.csv` — 20 failure modes with cause, consequence,
detection method, mitigation, severity, likelihood, RPN, kill criterion and the
phase in which each is testable.

## 16.1 The three that dominate

All score RPN 20 (severity 5 × likelihood 4):

**FM01 — premature 1-MCP release during manufacture.** Aqueous coating or drying
heat discharges the complex before the product exists. This is the *defining*
technical risk: the release mechanism and the manufacturing hazard are the same
physics. Detection is a retention assay against charged mass. Mitigation is a
non-aqueous or low-water binder and mild drying.
*Kill: retention below 50 % of charged 1-MCP after coating and drying, with no
low-water route doing better.*

**FM02 — premature release during storage.** A product that cannot sit in a
warehouse cannot be sold, regardless of how well it performs when fresh. This
risk is frequently discovered late because storage studies take real time —
hence starting it in Phase 2, not Phase 4.
*Kill: payload loss materially degrades efficacy within a realistic warehouse
window even in the intended overwrap.*

**FM14 — patent overlap.** Cellresin/Kimberly-Clark hold coated-substrate and
laminate claims; Fresh Inset claims delayed release commercially. This risk is
unaffected by any experimental result.
*Kill: counsel finds no practicable design-around of a blocking claim.*

That two of the top three are non-experimental (FM02 is slow, FM14 is legal) is
the central scheduling message of Section 18.

## 16.2 The differentiator's own failure modes

FM05 (no engineerable RH threshold) and FM06 (dose not reproducible) deserve
separate emphasis because they do not merely degrade the product — **they delete
the reason for the project**. Everything else being fine while these fail leaves
a working insert that is indistinguishable from HarvestHold Fresh.

They are also the cheapest failures to detect: both fall out of the Phase 3
release programme, before any produce trial or scale-up spend.

## 16.3 Coupled failures

Two pairs where fixing one worsens the other, worth watching explicitly:

* **FM03 ↔ FM04.** Increasing coat weight to slow dumping can push release below
  the effective concentration. The optimum is a window, not a direction, and it
  may be narrow.
* **FM10 ↔ FM11 ↔ FM16.** The essential oil must exceed MIC in the package vapour,
  stay below the sensory threshold, and not plasticise the layer enough to
  accelerate 1-MCP release. Three constraints on one variable is the strongest
  argument for deferring the oil entirely (Section 7.5).

## 16.4 Kill criteria, consolidated

The project should **stop or be redesigned** if any of the following holds:

1. No coating route retains a usable fraction of the 1-MCP charge (Phase 1).
2. Payload cannot be held through realistic storage in the intended overwrap
   (Phase 2).
3. Release versus RH is smooth and shallow across every binder — no threshold
   exists to specify (Phase 3).
4. Delivered-dose CV stays high after optimisation — no specification can be
   written (Phase 3).
5. The insert cannot match conventional gaseous 1-MCP within cost and sensory
   limits (Phase 4).
6. Pilot-coated material does not reproduce lab release behaviour (Phase 5).
7. Counsel identifies a blocking claim with no practicable design-around
   (Phase 6).
8. Regulatory advice indicates a new registration whose cost and timeline exceed
   project resources, with no registrant partner available (Phase 1/6).

## 16.5 What "redesign" means rather than "stop"

Not every failure is terminal, and the distinction is worth stating so the
criteria are not applied mechanically:

* Failing 3 or 4 kills *the IP case* but not necessarily a useful product — it
  becomes a commodity insert competing on cost, which is a different and much
  weaker business.
* Failing 1 with a water-based binder but passing with an ethanolic one is not a
  failure at all; it is the answer.
* Failing 5 on tomato while passing on peach would indicate a commodity-fit
  problem, not a delivery-system problem.

The criteria above are written to stop *self-deception*, not to stop thinking.
