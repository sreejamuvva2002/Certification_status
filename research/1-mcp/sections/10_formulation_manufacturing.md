# 10. Preparation method and manufacturing feasibility

## 10.1 The constraint that selects the process

The payload is discharged by water and degraded by heat. So process selection is
dominated by one question: **how much water and heat does the 1-MCP complex see,
and for how long?**

Cao et al. (2024) reached the same conclusion independently and built their
coated paper by a **water-free method** for exactly this reason. That is a
literature-anchored precedent for a low-moisture route, not a preference.

## 10.2 Method comparison

| Method | Max temp | Water/solvent exposure | Expected 1-MCP loss | Line speed | Uniformity | Capital | Industrial analogue | Verdict |
|---|---|---|---|---|---|---|---|---|
| Solvent casting (lab) | low | **high, prolonged** | **high** | n/a | poor | trivial | **none** | Reject as a commercial route |
| Knife/blade coating | low | medium | medium | low–med | medium | low | yes | Lab only |
| **Meyer-rod coating** | low | medium | medium | low | **good, metered** | low | **yes → slot-die** | **Recommended lab method** |
| Spray coating | low | high (atomised) | high | med | medium | medium | yes | Poor: maximises water contact area |
| Dip coating | low | **very high** | **very high** | low | poor | low | limited | Reject |
| Flexographic printing | low | medium | medium | **high** | good | high | yes | Viable at scale; good for patterned coatings |
| Gravure coating | low | medium | medium | **high** | **excellent** | high | yes | Viable at scale |
| **Slot-die coating** | low | medium | medium | high | **excellent, precise coat weight** | high | yes | **Recommended scale-up route** |
| Extrusion coating | **high (>200 °C)** | none | **near-total** | high | good | high | yes | **Reject: thermal destruction** |
| Lamination | medium | none | low | high | good | high | yes | Only if a bilayer proves necessary — and see the patent concern |
| Adhesive transfer | low | low | low | high | good | medium | yes | Interesting for label formats |

## 10.3 Recommended path

**Laboratory: Meyer-rod (wire-wound bar) coating.**

Chosen specifically because it has a **direct industrial analogue**. A Meyer rod
meters coat weight by wire diameter, so lab work is expressed in the same units
(g·m⁻²) that a production slot-die is set to. The brief warns against selecting
solvent casting as the final commercial method; the deeper problem with casting
is that it produces data in units nobody can scale — a cast film's thickness is
not a coat-weight specification.

**Pilot and production: slot-die coating**, with gravure or flexo as alternatives
where patterned coverage is wanted.

**Drying: ambient to mildly warm, forced air.** Minimise both peak temperature
and residence time. Treat drying as a controlled variable and measure retained
1-MCP as a function of it — that relationship is itself a candidate result worth
protecting (Section 17).

## 10.4 Binder screen (the actual experiment)

Three binders, in ascending order of water exposure:

| Binder | Carrier | 1-MCP retention risk | Cost | Note |
|---|---|---|---|---|
| Shellac / ethanolic | ethanol | **lowest** | medium | Genuinely water-free; requires solvent handling and recovery |
| PEG | melt or minimal water | low | low | **Literature-anchored**: used by Cao et al. specifically to moderate 1-MCP release |
| Water-based latex / HPMC | water | **highest** | lowest | Cheapest and most standard; the retention risk the design is trying to avoid |

Run all three. The expected result — that retention rises as water falls — is
worth *quantifying*, because a measured retention-versus-water-content
relationship is more useful (and more patentable) than a formulation that merely
works.

## 10.5 Worker exposure and solvent recovery

An ethanolic route needs solvent recovery and explosion-proof drying at scale;
this is routine in converting but is a real capital consideration. The complex
must be handled as a pesticide product throughout (Section 14). Dust control
matters when handling dry complex powder.

## 10.6 Scale-up gate

The transition that must be demonstrated in Phase 5 is **lab Meyer-rod → pilot
slot-die at the same coat weight**, with release curves compared directly. If
pilot-coated material does not reproduce lab release behaviour, the formulation
is not manufacturable and the project stops there (FMEA FM17). Because both
methods are specified in g·m⁻², that comparison is meaningful — which is the
whole reason for choosing Meyer rod over casting at the start.
