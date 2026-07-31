# 20. Complete verified references

## 20.1 What "verified" means here

Every entry below was **retrieved, not recalled**. Specifically:

* Bibliographic details — authors, year, title, journal, DOI — come from Crossref,
  OpenAlex or Europe PMC, never from a language model.
* Every DOI was **re-resolved against Crossref** during verification, and the
  returned title was checked for agreement with the stored record. Entries whose
  DOI failed to resolve, or whose title disagreed, are reported as issues in
  `outputs/1mcp/20_issues.csv` and excluded from the counts.
* Each entry is annotated with whether **full text was retrieved** or only the
  abstract was available, because that determines how much of the literature
  table that source could support.
* Patent entries carry the publication number and priority date **as stated in
  the retrieved document**. Priority dates that could not be established from the
  document are marked rather than guessed.

No reference was added by hand. If a work is not in the harvested corpus, it does
not appear — which also means this list is not a complete bibliography of the
field, but a complete list of what this review actually read.

## 20.2 Known gaps

* Four indexes named in the brief were inaccessible (Web of Science, Scopus, CAB
  Abstracts, AGRICOLA), so postharvest, extension and conference literature is
  under-represented relative to a full systematic review.
* Patent coverage rests on a single provider; unpublished applications are by
  definition absent.
* Commercial and regulatory sources cited in Sections 5 and 14 (EPA registration
  documents, product labels, company materials) are cited inline at their point
  of use rather than listed here, and company performance claims are labelled as
  claims throughout.

## 20.3 References

<!-- REFERENCES -->
