# Case Management Update — Implementation Decisions

## Main page

- **Average Score removed:** a queue-wide mean does not identify urgency, SLA exposure, or workload and can conceal a small number of critical cases. It was replaced by the count of active investigations, which directly supports staffing and triage.
- **Investigations scope:** implemented as a read-only filtered case list with the same search, column filters, sorting, and Business Folder links as the main queue. Workflow mutation was deliberately excluded because no approved assignment/disposition write API was provided.
- **Column filters:** implemented as an expandable filter row. Filters combine with AND logic. Categorical, text, numeric-range, and date-range controls are used according to the column data type.
- **Colour scheme:** blue `#2563EB` is the application primary on a white background. Semantic risk colours remain green/orange/red. Statuses include both icons and text, so meaning does not rely on colour.
- **Closed status:** HANA `CLOSED_*` values are normalised to `closed`. A resolver or a closed outcome maps to “Closed – Resolved by team”; an explicit timeout or SLA breach without a resolver maps to “Closed – Auto-timeout.”

## Business Folder

- **Baseline:** defined as the entity's historical average transaction amount from `TRANSACTION_BASELINES`. The amount ratio is current amount divided by that baseline and is displayed to exactly two decimals.
- **Beneficial ownership:** names, percentages, PEP/sanctions flags, nationality, and residence come from `COMPANY_BENEFICIAL_OWNERS`. The source schema has no ownership-chain/relationship-structure field, so entries are labelled “Direct beneficial owner” rather than inventing a hierarchy.
- **Activity chart:** implemented as a combined 12-month chart: transaction amount line, transaction-count bars, and current risk overlay. `TRANSACTION_RISK_SCORES` is an invalidated HANA view, so historical risk snapshots are unavailable; the current validated score is shown as a reference line rather than fabricated history.
- **Actionable insights:** the button calls the existing governed SAP AI Core GPT-4o explanation flow with the alert, entity, score factors, evidence, and retrieved policy context. It returns a structured action list with loading, error, model, and timestamp states.
- **Annex:** implemented as an accessible slide-out glossary covering threshold breach, baseline, amount ratio, risk breakdown, beneficial owners, and risk intelligence.
