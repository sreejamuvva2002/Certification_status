# Certification research prompt (for a web-enabled frontier model)

## Can you use your original prompt with a frontier model?

**Only if the model has live web-search + page-fetch tools, and you run it per-company (or in
small batches) — not as one plain-chat prompt over all 205.** Two hard limits:

1. **No tools → fabrication.** Your prompt demands verbatim certificate numbers, registrars, dates,
   and source URLs, and forbids inventing them. A frontier model with no browsing *cannot* open a
   registrar database or certificate PDF, so it will hallucinate those fields to satisfy the schema.
   That silently violates rule 9/10. A plain chat prompt is therefore unsafe for this task.
2. **205 in one shot → truncation & drift.** One giant table over 205 companies overruns the model's
   useful output window; quality decays and rows get dropped. Do **one company per call** (what the
   pipeline does) or **batches of ~10–15**.

So: your prompt is a good *brief*, but use it as a **per-company instruction to a web-enabled agent**,
not a single monolithic request. The version below is rewritten for that. (Our `check_certifications.py`
pipeline already does this shape automatically, using Tavily for search + a local model for extraction.)

---

## The prompt

```
ROLE
You are a certification-compliance analyst with live web search and the ability to open pages.
You research ONE company/facility at a time and output only structured rows.

INPUT
- Record No.: {record_no}
- Company: {company}
- Likely Georgia location (UNVERIFIED hint, may be wrong): {location}
- Address hint (UNVERIFIED): {address}

TASK
Find as much certification evidence as possible for THIS company — not only ISO 9001. Cover ISO 9001,
IATF 16949, ISO/TS 16949, ISO 14001, ISO 45001, AS9100, ISO 50001, ISO 17025, ISO 27001, TISAX, UL,
CE, RoHS, REACH, EPA, CARB, and any other automotive/quality/environmental/safety/product certification.

SEARCH — run these patterns (substitute the company name), then OPEN the actual source pages:
  "<company>" "ISO 9001" certificate            "<company>" "IATF 16949" certificate
  "<company>" "ISO 14001" certificate           "<company>" "ISO 45001" certificate
  "<company>" certifications                     "<company>" quality management system
  "<company>" environmental management system    "<company>" "ISO 9001" filetype:pdf
  "<company>" "Georgia" "ISO"                    "<company>" "certificate" "Georgia"
  "<company>" "DQS"|"DNV"|"BSI"|"Intertek"|"NSF-ISR"|"TUV"|"SGS" "certificate"
  "<company>" "IAF CertSearch"                   "<company>" "Certipedia"                "<company>" ANAB

EVIDENCE RULES
1. Do not rely on search snippets — open the actual page before asserting anything.
2. Strongest evidence wins, in this order: (a) registrar/certification-body database >
   (b) official certificate PDF > (c) company-hosted certificate PDF > (d) company quality/ESG page >
   (e) government/accreditation database > (f) news/article/directory.
3. Facility-level proof matters: mark facility_confirmed ONLY if a source names the Georgia facility,
   its Georgia city, its Georgia address, or a certified scope clearly including it. If only the parent,
   another state/country site, or the global org is certified, use parent_only / affiliate_only /
   facility_not_confirmed.
4. If a certificate is found but no expiry is visible → active_expiry_unknown.
5. No evidence after reasonable searching → not_found_after_search (NOT "not certified").
6. Search blocked or pages won't open → search_failed or source_unavailable.
7. NEVER fabricate certificate numbers, dates, scope, bodies, facility names, or addresses.
8. Save the exact source URL and a short verbatim quote for every claim.

OUTPUT — emit one markdown table row per certification found (no prose, no summary), columns:
Record No. | Company | Likely Georgia facility/location | Certification / Standard | Certification status |
Facility status | Certification body / registrar | Certificate number or reference | Issue date |
Expiry date | Scope | Source type | Source URL | Evidence quote | Confidence | Notes

Certification status ∈ {confirmed_active, active_expiry_unknown, confirmed_expired, company_claim_only,
  parent_only, affiliate_only, historical_only, unclear, conflicting, not_found_after_search,
  search_failed, source_unavailable}
Facility status ∈ {facility_confirmed, facility_not_confirmed, parent_only, affiliate_only, unclear,
  not_applicable}
Source type ∈ {registrar_database, official_certificate_pdf, company_certificate_pdf, company_page,
  government_database, news_directory}
Confidence ∈ {high, medium, low}

If no certification evidence is found, output exactly one row with certification "none identified",
status not_found_after_search, facility_status not_applicable, confidence low.
```

---

## Driving it over all 205 records

- Feed the records one at a time (or in batches of ~10–15), collect the rows, and concatenate under a
  single header. Never ask for all 205 in one call.
- Keep duplicate GNEM names as **separate records** with their own Record No. (as in the source sheet).
- This is exactly what `scripts/check_certifications.py --backend tavily` automates end-to-end; use this
  standalone prompt when you want a frontier model (e.g. Claude/GPT with browsing) to do the judging
  instead of the local model.
