# Company tariff research plan

The workbook has 205 populated company rows and 193 distinct names. All rows and duplicate names are preserved. Seed locations, products, EV roles, and affiliations require verification.

The reviewable [query bank](company_queries.csv) contains 406 queries: two per company plus 20 shared policy checks across automotive, metals, batteries/critical minerals, PCBs/electronics, and displays. Names and sector hints guide discovery; they do not establish exposure. [Company inventory](company_inventory.csv).

Sequence: finish local cleanup; execute the initial 20 primary-authority queries; then research every company and attach verified source quotations and unresolved gaps to each profile. Basic searches cost one credit according to [Tavily documentation](https://docs.tavily.com/documentation/api-credits), checked September 10, 2026. The proposed full-run ceiling is 500 credits including the initial 20, remaining searches and retries. Paid extraction remains off. The user explicitly approved the 500-credit cumulative ceiling on September 10, 2026. The initial 20 policy searches and all company searches share this one budget.

Each company profile will separate company-named statements, group-level context, facility evidence, sector policy, and unsupported applicability. No exact duty rate, HTS classification, origin or duty stacking is inferred from a generic product label. A searched company with no usable evidence receives an explicit gap record.
