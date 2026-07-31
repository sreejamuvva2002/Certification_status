# 13. Commodity selection and produce-validation experiment

## 13.1 Commodity ranking

Candidates ranked against the brief's criteria: ethylene sensitivity, documented
1-MCP response, typical package humidity, respiration rate, commercial loss,
decay relevance, package size, availability, experiment duration, ease of
measuring effects, risk of adverse 1-MCP responses, and industrial value.

| Rank | Commodity | Case for | Case against |
|---|---|---|---|
| 1 | **Tomato** | Textbook climacteric; large, unambiguous, *fast* 1-MCP response; year-round availability; cheap; effects visible in days; firmness and colour both easy to quantify | Lower per-unit value; decay pressure less commercially central |
| 2 | **Peach / nectarine** | High commercial loss; strong industry pull; brown rot (*Monilinia*) makes the antimicrobial arm meaningful; **directly comparable to Cao et al. (2024)** | Seasonal; risk of internal breakdown/mealiness confounding results; 1-MCP response more variable |
| 3 | Banana | Dramatic, easily staged ripening response | Chilling-sensitive; supply chain hard to replicate in a lab |
| 4 | Avocado | High value; strong 1-MCP literature | Long, variable ripening; harder to score |
| 5 | Apple / pear | The commercial home of 1-MCP; excellent literature | Long experiments (months); **incumbent-dominated**; risk of superficial scald/disorder confounds |
| 6 | Kiwifruit | InBox is registered for it in CA | Slow; specialised |
| 7 | Mango / papaya | Commercially important | Availability and variability outside producing regions |
| 8 | Plum | Reasonable model | Less distinct endpoints |

**Primary: tomato.** Not because it is the most commercially valuable, but
because it is the fastest, cheapest, most reproducible way to answer the question
that gates everything — *does this insert deliver an effective, reproducible
1-MCP dose into a real package?* A commodity with a slow, variable response would
confound a delivery-system failure with a physiological one. Pick the commodity
that makes the delivery system's behaviour easiest to see.

**Secondary: peach.** Adds commercial relevance, the decay pressure that makes
the optional antimicrobial arm worth testing, and — importantly — direct
comparability with the closest prior art.

**Explicitly not first: apple.** It is where 1-MCP lives commercially, which is
exactly why it is the wrong first experiment: months-long trials against an
entrenched incumbent, before the delivery system is even characterised.

## 13.2 Experimental parameters

Values below are the *structure* of the design. Absolute figures (dose,
temperature, RH, duration) must be set from the commodity's postharvest
literature and from the release data of Section 11, not chosen here.

| Parameter | Tomato (primary) | Peach (secondary) |
|---|---|---|
| Cultivar | One determinate cultivar, single source | One freestone cultivar |
| Maturity at treatment | Mature green to breaker — **before the ethylene climacteric**, or 1-MCP cannot act | Commercial harvest maturity |
| Package | Vented corrugated carton or sealed chamber of measured volume | Standard tray/carton |
| Produce mass | Fixed per replicate; recorded individually | Fixed per replicate |
| Headspace volume | **Measured, not assumed** | Measured |
| Storage temperature | Above chilling threshold for tomato | Commercial cold-chain temperature |
| RH | Measured continuously, logged | Measured continuously |
| Treatment duration | Set from release curve | Set from release curve |
| Target 1-MCP dose | From published effective dose for the commodity | From published effective dose |
| Target organism (peach arm) | — | *Monilinia fructicola* |

## 13.3 Treatment groups

All eight groups from the brief, each earning its place:

| # | Group | Question it answers |
|---|---|---|
| 1 | Untreated produce | Baseline ripening |
| 2 | Blank substrate (uncoated paper) | Does the paper itself do anything (moisture buffering)? |
| 3 | Matrix-only (binder-coated, no active) | Does the binder alone affect the package? |
| 4 | **1-MCP insert** | The primary test |
| 5 | Essential-oil-only insert | Isolates antimicrobial effect (peach arm) |
| 6 | Dual-active insert | Tests interaction — **only meaningful against 4 and 5** |
| 7 | Commercial benchmark | Are we better than what exists? |
| 8 | Conventional gaseous 1-MCP | Positive control: does the commodity respond at all? |

Groups 2 and 3 are the ones most often dropped and most often needed: without
them, a moisture-buffering or barrier effect of the insert is indistinguishable
from 1-MCP action.

**Group 8 is non-negotiable.** If the fruit does not respond to a conventional
1-MCP treatment, the experiment cannot interpret a null result from the insert —
a delivery failure and an unresponsive fruit batch look identical.

**Group 7 caveat:** commercial products are sold under label restrictions.
Confirm that comparative use is legally permissible before planning it, and
document the product, lot and use rate.

## 13.4 Measurements

**Delivery (the part unique to this project):** headspace 1-MCP by GC at
intervals; RH and temperature logged continuously; residual 1-MCP in the spent
insert; mass balance.

**Physiology:** ethylene production rate; respiration rate (CO₂).

**Quality:** firmness (instrumental, consistent probe/geometry); weight loss;
colour (instrumental L\*a\*b\*, not visual); soluble solids; titratable acidity; pH.

**Decay and microbiology:** decay incidence and severity on a defined scale;
microbial load; for peach, inoculated challenge with the target organism.

**Sensory:** off-odour screening on every arm; a triangle test for any
essential-oil arm. **If sensory testing involves human panellists, ethics
approval and informed consent are required, and treated fruit must be confirmed
safe for consumption before any tasting — for a pesticide-regulated active this
is a genuine constraint, not a formality.** Where that is not feasible, restrict
to instrumental and trained-assessor odour evaluation and say so.

**Disorders:** internal breakdown, mealiness, chilling injury where relevant —
1-MCP can *cause* disorders in some commodities, and a project that measures only
firmness will miss the harm it does.

## 13.5 Design and analysis

* **Randomised complete block**, blocking on the real nuisance factors: position
  within the storage room (temperature and airflow gradients are not negligible)
  and fruit source lot.
* **Experimental unit is the package, not the fruit.** Fruit within a package
  share a headspace and are not independent. Treating individual fruit as
  replicates inflates n and is the most common statistical error in this
  literature. Use package means, or a mixed model with package as a random
  effect.
* At least 4 replicate packages per treatment per sampling time; destructive
  sampling means replicates must be planned per timepoint, not reused.
* Analysis: mixed-effects model for repeated measures; ANOVA with an appropriate
  post-hoc test for single timepoints; survival/ordinal methods for decay
  incidence rather than treating percentages as normal.
* **Pre-register the primary endpoint** (proposed: firmness retention at the
  commercial end-of-shelf-life point) before unblinding. With ~15 measured
  variables, something will be significant by chance.

**Screening design first, response surface later.** A factorial or RSM design
over binder × coat weight × loading is premature until the release programme
(Section 11) shows which factors actually move the response. Use a simple
screening design first; escalate only if the factors interact.
