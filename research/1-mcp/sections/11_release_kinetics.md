# 11. Release-kinetics protocol

The differentiator proposed in Section 9 is a measurement claim, so this protocol
*is* the invention's evidence base rather than a supporting detail. It is also
the clearest gap in the closest prior art: Cao et al. (2024) followed release
gravimetrically and report no kinetic model and no headspace 1-MCP concentration.

## 11.1 Analytical method

**Detector: GC-FID.** 1-MCP (C₄H₆, MW 54.09) is a small hydrocarbon; FID is
sensitive, linear over several decades, cheap to run, and is what the postharvest
literature uses. GC-MS is worth one confirmatory run to prove peak identity
against the α-CD blank, then FID for throughput.

**Calibration is the hard part and must not be improvised.** 1-MCP is a gas
supplied as a complex; there is no bottled liquid standard. Generate standards by
releasing a *weighed* mass of complex into a sealed vessel of known volume with
excess water, assume complete release (verify by exhaustive re-extraction of the
spent complex), and construct a multi-point curve by dilution. Every calibration
must carry its own mass balance. Report LOD and LOQ, determined from the
calibration curve, not assumed.

**Sampling losses are a first-order error, not a detail.** Each headspace draw
removes gas from a closed system. Either (a) use individual sacrificial vials —
one vial per timepoint, destructively sampled, which eliminates the problem
entirely and is strongly preferred — or (b) correct explicitly for cumulative
withdrawal and state the correction. Repeated sampling of one vial without
correction produces a decay curve that is partly an artefact of sampling.

## 11.2 Test system

* Sealed glass vials or jars of accurately known volume; gas-tight septa.
* Insert area scaled to headspace volume so that area-to-volume ratio is a
  controlled variable, not an accident of vial size. Report it explicitly
  (cm²·L⁻¹) — this is what makes results transferable to a real package.
* RH controlled by saturated salt solutions in a separate well within the vessel,
  physically isolated from the insert so liquid water never contacts the coating.
* Leak testing before every run; blank vials (paper + binder, no complex) on
  every run to exclude co-eluting volatiles from the binder or the paper itself.

**Produce-free tests first.** Fruit respires, transpires and absorbs 1-MCP, so a
produce-containing vessel confounds release with uptake. Establish the release
curve in a clean system, then validate in the presence of fruit.

## 11.3 Condition matrix

RH and temperature levels must be justified against the commodity and package
(Section 13), not chosen for roundness. The *structure* of the matrix:

| RH level | Rationale |
|---|---|
| Low | Storage/transport condition. Tests shelf stability before activation — the product must **not** release here. |
| Intermediate | Partial activation; locates the threshold. |
| Typical produce-package RH | The design point. |
| Near-saturation | Condensation risk; tests worst-case dumping. |

| Temperature level | Rationale |
|---|---|
| Refrigerated | Normal cold-chain storage for the chosen commodity. |
| Cool-chain interruption | The realistic abuse case; a product that dumps its payload during a transport excursion is unsafe to sell. |
| Ambient / retail | Terminal market conditions. |

Saturated-salt RH values are themselves temperature-dependent, so the achieved RH
must be measured and reported at each temperature rather than taken from a table
at 25 °C.

## 11.4 Models — and the trap to avoid

Fit only physically defensible models, and report the *physics*, not just the R².
Several of these models are near-collinear over short time windows, so a good fit
is weak evidence for a mechanism.

| Model | Equation | Parameters mean | Appropriate when | Limitation here |
|---|---|---|---|---|
| Zero-order | Mt/M∞ = k·t | constant rate | a maintained reservoir at constant activity | rarely true once the complex depletes |
| First-order | Mt/M∞ = 1 − e^(−k·t) | k = rate constant | release proportional to remaining load | assumes no diffusion barrier — i.e. assumes away the binder |
| Higuchi | Mt/M∞ = k·√t | matrix diffusion | planar matrix, constant D | derived for dissolved drug in a matrix; a gas from a hydrated lattice is a different physics |
| Korsmeyer–Peppas | Mt/M∞ = k·tⁿ | n diagnoses mechanism | first 60 % of release | **n is only interpretable for the geometry it was derived for**; quoting n without stating geometry is meaningless |
| Weibull | Mt/M∞ = 1 − e^(−((t−T)/a)^b) | T = lag, a = scale, b = shape | empirical shape fitting, **including a lag time** | empirical — b is not a mechanism |
| Peppas–Sahlin | Mt/M∞ = k₁tᵐ + k₂t²ᵐ | splits Fickian vs relaxation | swelling-controlled systems | needs dense early data |
| Dual-resistance | series resistances | separates hydration from diffusion | two-step control | more parameters than short curves support |
| Arrhenius | k = A·e^(−Ea/RT) | Ea | temperature dependence of k | only valid if mechanism is unchanged across T — check before applying |

**The honest recommendation is Weibull as the primary descriptive model**,
because the quantity this product is actually claiming — a *lag* before onset —
is an explicit parameter (T) rather than something inferred. Korsmeyer–Peppas
should be fitted over the first 60 % as a mechanism diagnostic, with geometry
stated. Arrhenius applies to the temperature series only after confirming the
mechanism does not change between refrigerated and ambient.

Do not force a model. "No fitted model described these data" is a publishable and
honest result, and is better evidence of unusual behaviour — which is what a
patent application would want — than a forced fit.

## 11.5 Performance targets

Targets are stated as the shape of the required result. Absolute values must be
set against the commodity's known effective 1-MCP dose, which comes from the
postharvest literature, not from this protocol.

| Metric | Target shape | Why it matters |
|---|---|---|
| Lag time at low RH | Long — no meaningful release | Shelf stability; the core commercial requirement |
| Lag time at package RH | Short and reproducible | Treatment must start when the package closes |
| Time to effective headspace concentration | Well inside the treatment window | Efficacy |
| Duration above effective concentration | Spans the intended treatment period | Efficacy |
| Maximum headspace concentration | Below any level causing off-flavour or disorder | Safety and quality |
| Total fractional release | High and, above all, **reproducible** | Dose control |
| Residual 1-MCP in spent insert | Measured, not assumed | Mass balance; disposal |
| Replicate CV | Low | **The differentiator stands or falls here** |
| RH sensitivity (∂release/∂RH) | Sharp at threshold, flat above | This is what "humidity-triggered" has to mean quantitatively |
| Temperature sensitivity | Modest across the cold chain | Robustness to excursions |

**Mass balance closes the argument.** Report released + residual + unaccounted for
every run. A study that reports "82 % released" without accounting for the other
18 % has not measured release; it has measured one number.

## 11.6 Pre-activation storage stability

Run in parallel from day one, because it gates commercial viability independently
of everything above: inserts stored in the intended protective overwrap at
realistic warehouse conditions, assayed for retained 1-MCP at intervals, against
unwrapped controls.

If retained payload falls materially over a few weeks in the overwrap, the
product does not have a route to market in that form, and that should be known
early rather than after formulation optimisation.
