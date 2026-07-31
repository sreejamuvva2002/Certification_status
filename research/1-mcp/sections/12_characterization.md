# 12. Characterisation programme

Split by what actually gates a decision. The most common failure in this
literature is a full materials-characterisation battery on a system whose release
behaviour was never measured properly — FTIR, XRD, SEM, TGA and tensile data on a
film nobody quantified the headspace of.

## 12.1 Essential for proof of concept (Phases 1–3)

| Test | What decision it gates | Why essential |
|---|---|---|
| **Retained 1-MCP after coating and drying** | Go/no-go on the process (FMEA FM01) | If the payload does not survive manufacture, nothing else matters |
| **Headspace 1-MCP by GC over time** | The entire differentiator | The primary measurement; everything else is context |
| **Coat weight (gravimetric, g·m⁻²)** | Dose specification | The manufacturing parameter that maps to release; no retrieved source reports it |
| **Water-vapour permeability of the coating** | Binder selection | The actual release-control mechanism |
| **Water uptake / moisture sorption** | Trigger design | Defines the activation threshold |
| **Storage stability of retained payload** | Commercial viability (FM02) | Gates the product independently of performance |
| **Mass balance (released + residual)** | Data integrity | Without it, "82 % released" is one number, not a measurement |
| **Blank-substrate GC** | Analytical validity | Excludes binder/paper volatiles masquerading as signal |

That is eight tests, and only two require instrumentation beyond a GC and a
balance.

## 12.2 Valuable but deferrable (Phase 4+)

* **DSC / TGA** — thermal stability of the complex; informs the drying window.
  Useful once a binder is chosen.
* **SEM, surface and cross-section** — coating continuity and penetration into
  the paper; explains anomalous release rather than predicting it.
* **FTIR / XRD** — confirm the inclusion complex survived processing. Genuinely
  useful *if* retention is poor and the cause is unclear; premature before that.
* **Contact angle, Cobb value** — surface energy and water absorbency of the base
  paper; matters for coating quality.
* **Coating adhesion, folding resistance** — converting robustness.
* **Air permeability, optical properties** — largely cosmetic for an insert.
* **Tensile strength, elongation, modulus** — **low priority for this
  architecture.** An insert carries no load. These belong to a standalone-film
  product, which is not what is recommended. Measure them only if the insert is
  physically failing in handling.

## 12.3 Only if the essential oil is reinstated (Phase 4+)

Droplet size, Pickering-emulsion stability, zeta potential, and emulsion
creaming/coalescence on storage. **All of these are deferred with the emulsion
itself** (Section 7.2) — they characterise a component the recommended design
does not contain. Listing them now would be characterising a decision already
made against.

If an oil is reinstated as a separate layer using a β-CD inclusion powder (as Cao
et al. did) rather than an emulsion, most of this list is unnecessary.

## 12.4 What to measure that others have not

The prior art gap is not in materials characterisation — that literature is well
served. It is in **dose and reproducibility**:

* Coat weight versus release rate, as a designed relationship.
* Release fraction versus RH, resolved finely enough to show whether a threshold
  exists.
* Replicate-to-replicate coefficient of variation in delivered headspace
  concentration — reported, not omitted.
* Delivered concentration across a deliberately varied package volume and fruit
  mass.
* Retained payload versus drying condition and versus storage time.

These are cheap measurements that no retrieved source reports, and they are
precisely the evidence the proposed differentiator requires.
