# No XBRL fact-lookup tool

The Filing is inline XBRL: every figure in the financial statements is tagged with a concept, period, dimensions, unit and scale. A `get_financial_fact` tool reading those tags would return exact figures and expose segment relationships directly. We do not build it; figures come from table Passages, and arithmetic goes through the `calculate` tool.

The tags are harder to use than they look. The same figure is tagged many times — in the statements, the notes, MD&A, prior-year comparatives and segment roll-ups — so the tool would need canonical-fact selection, decoding of context, scale and sign, and a mapping from the user's wording to a concept ("net sales" is `RevenueFromContractWithCustomerExcludingAssessedTax`). That does not fit the assignment's 3–4 hour budget, and a half-done version returns confidently wrong numbers, which is worse than none.

## Considered Options

- **Full fact tool with label matching** — deferred: the concept-mapping and fact-selection work above.
- **XBRL concepts as Table Card metadata** — deferred: improves table retrieval without a separate tool, but still needs the concept mapping.

## Consequences

- Numeric accuracy rests on how faithfully tables are rendered into Passages (column headers, periods, units).
- Revisit if a wrong figure is traced to column or period confusion in a rendered table.
