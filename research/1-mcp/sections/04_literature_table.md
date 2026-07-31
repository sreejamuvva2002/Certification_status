# 4. Peer-reviewed literature table

## 4.1 How to read this table

Twenty-five columns per the brief. Every non-empty cell is backed by a quote from
a document that was actually retrieved; the quotes are in
`tables/literature_evidence.csv`, one row per cell, with the evidence level and
the checks that were applied.

**Empty cells are not all the same thing**, and the distinction is recorded per
cell in the evidence file:

| Evidence level | Meaning |
|---|---|
| `full_text_verified` | Quote located in retrieved full text |
| `abstract_only` | Quote located in the abstract; full text was never openly available |
| `metadata_only` | From Crossref/OpenAlex (reference, DOI, publication type) |
| `not_stated` | **We hold the full text and it does not report this** — a positive finding |
| `unverifiable` | We could not obtain enough of the paper to know |

The last two are never merged. Treating "we could not read it" as "the paper
omits it" would be a fabricated claim about the literature.

**Values that failed grounding were blanked**, not published. Where the
extraction model proposed a value that could not be located in the source, the
cell is empty and flagged `ungrounded_blanked` in the evidence file, and the
row's confidence is reduced. The row survives; the unsupported value does not.

## 4.2 Coverage — the honest quality statistic

Per-column counts of each evidence level:

<!-- TABLE: coverage -->

Columns describing process detail — manufacturing temperature, 1-MCP loading,
package volume, coat weight — are sparse **by construction**. Roughly a quarter
of screened papers yielded open full text, and this information lives in methods
sections, not abstracts. The sparsity is a measurement of what is openly
publishable, not an artefact of effort.

The single highest-leverage way to densify this table is to supply PDFs for
specific papers via the pipeline's `--pdf-drop` ingest, which re-extracts them at
full-text depth without re-running anything else.

## 4.3 The table

<!-- TABLE: literature -->

## 4.4 Notes on interpretation

* **Publication type** was assigned by the screening model from title and
  abstract, then used to split originals from reviews. Crossref's own `type`
  field is unreliable for this — most reviews are typed `journal-article` — so
  the split should be spot-checked before being quoted as a count.
* **Reviews are included to map the field**, per the brief, and are **not**
  treated as evidence that an experimental result was demonstrated. Where a review
  is the only source for a claim, that claim is weaker than a table cell makes it
  look.
* **Contradictions are not reconciled.** Where sources disagree, both values
  stand with their quotes; the disagreement is information.
