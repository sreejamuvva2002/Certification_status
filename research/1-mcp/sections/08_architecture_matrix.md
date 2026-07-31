# 8. Architecture comparison

Six architectures were scored 1–5 against 20 criteria. Scores and the full
weighting rationale are in `assets/architecture_matrix.csv`; the scoring script
is reproducible from that file.

## 8.1 Weighting assumptions

Weights are 1–3 and reflect a single principle stated in the brief: **prioritise
a working, inexpensive, scalable design over novelty or material complexity.**

**Weight 3 (project-critical)** — scientific feasibility; patent-overlap risk;
1-MCP retention through manufacture; trigger reliability; dose controllability;
shelf stability before activation; regulatory difficulty; roll-to-roll
compatibility; industrial scalability.

These are the criteria on which the project *fails outright* rather than
performs poorly. 1-MCP retention through manufacture is weighted 3 because the
payload is a gas held in a moisture-labile complex: any aqueous or heated step
risks discharging it before the product ships. Patent-overlap risk is weighted 3
because Cellresin/Kimberly-Clark hold coated-substrate and laminate claims in
precisely this space.

**Weight 2 (materially important)** — novelty potential; ingredient count; step
count; food-contact safety; sensory risk; raw-material cost; equipment
availability; recyclability; time to prototype.

Novelty is deliberately weight 2, not 3. The brief is explicit that an
architecture should not be recommended because it sounds innovative.

**Weight 1 (secondary)** — antimicrobial performance; mechanical performance.
The essential oil is optional in the brief, and the product is an insert, not a
load-bearing package.

Criteria phrased as risks are scored so that **5 is always good** (e.g.
"patent-overlap risk, 5 = low risk"), so higher totals are uniformly better.

## 8.2 Results

| Architecture | Weighted | /100 | Unweighted /100 |
|---|---|---|---|
| **C — paper / paperboard insert** | **206 / 235** | **87.7** | 87.0 |
| D — label, patch or patterned coating | 181 / 235 | 77.0 | 76.0 |
| E — coated absorbent pad | 172 / 235 | 73.2 | 72.0 |
| B — bilayer coating | 148 / 235 | 63.0 | 63.0 |
| F — compartmentalised dual-active insert | 125 / 235 | 53.2 | 54.0 |
| A — single homogeneous chitosan/CNC film | 102 / 235 | 43.4 | 45.0 |

**The ranking is unchanged when all weights are set to 1.** The conclusion is
therefore not an artefact of the weighting scheme — a sensitivity check worth
stating explicitly, because weighted scoring otherwise invites the suspicion that
the weights were chosen to produce the answer.

## 8.3 Why the proposed starting materials score worst

Architecture A — a chitosan/CNC film carrying both a 1-MCP/cyclodextrin complex
and a CNC-stabilised essential-oil Pickering emulsion — is the combination the
brief starts from, and it finishes last. The reasons are specific, not aesthetic:

* **1-MCP retention through manufacture scores 1.** Aqueous casting exposes a
  moisture-labile inclusion complex to bulk water, which is the one condition
  known to discharge it. Cao et al. (2024) chose a *water-free* route precisely
  to avoid this, and they state the reason plainly: 1-MCP-α-CD is "sensitive to
  high moisture, which may result in the complete release of 1-MCP gas in a short
  period of time."
* **Shelf stability before activation scores 1** for the same reason: chitosan is
  hygroscopic, so the matrix that carries the complex also draws the water that
  triggers it.
* **Ingredient and step counts are the worst of the six.** Chitosan, CNC, acid,
  plasticiser, cyclodextrin complex, essential oil, and a separately prepared
  Pickering emulsion — each an input to source, qualify, cost and defend.
* **Novelty potential scores only 2.** Adding materials to an already-published
  concept does not create protectable novelty; it creates a more complicated
  version of the prior art.

Architecture F (compartmentalised dual-active) scores second-worst for related
reasons: it is the most complex to build, the slowest to prototype, and its
headline feature — sequential or differential release — collides directly with
`US20210331990A1`, a published application titled for differential release of
1-MCP.

## 8.4 Why C wins

Architecture C — a low-cost paper or paperboard insert carrying a 1-MCP coating,
with the antimicrobial deferred — wins because it scores well on every criterion
weighted 3:

* **Retention (5):** a non-aqueous or low-moisture coating on paper, dried at
  ambient or mildly warm temperature, never immerses the complex in bulk water.
* **Roll-to-roll compatibility (5) and scalability (5):** paper coating is a
  mature converting operation. No new capital equipment is implied.
* **Regulatory difficulty (4):** an insert need not contact the fruit, which
  materially simplifies the food-contact position relative to a direct coating.
* **Recyclability (5):** a paper-based, repulpable insert is a real and
  defensible sustainability claim rather than a marketing one.
* **Cost (5) and time to prototype (5):** fewest materials, fewest steps.

Its weakest score is patent-overlap risk (3), and that is the honest concern:
`US10212931B2` claims a cyclodextrin composition coated on a substrate with a
second substrate over it. A single-layer coated insert is not that laminate, but
the neighbourhood is occupied and the distinction must be drawn deliberately
rather than assumed.

D (label/patch) is close behind and scores *higher* than C on dose
controllability (5 vs 4), because a fixed-area patch meters dose per package
directly. It loses on patent crowding among slow-release label technologies and
on adhesive compatibility with a moisture-triggered system.

## 8.5 What the matrix does not settle

Scores are informed judgements against retrieved evidence, not measurements.
Three in particular should be revisited once data exists:

* **Trigger reliability** for E (coated pad) is scored 5 on the reasoning that a
  pad already sits in the condensate path. If pads prove to over-wet locally and
  dump the payload, that score is wrong and E collapses.
* **Patent-overlap risk** for every architecture is a technical impression, not a
  legal opinion.
* **Dose controllability** distinguishes C from D by one point, and that single
  point is the difference between the primary and backup recommendation. It is
  the first thing an experiment should test.
