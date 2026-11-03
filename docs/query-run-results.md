# Test query run results

This page records live runs of the two required queries from [`docs/TASKS.md`](TASKS.md), with the agent's plan, tool trace, answer and Sources, and notes on accuracy and known weaknesses. These are the "example outputs" deliverable. Re-run them after any change to `prompts/` or `ANTHROPIC_MODEL`, and add a new dated section rather than overwriting this one.

## Run context

| | |
|---|---|
| Date | 2026-11-03 |
| Code | Agent from PR #24 (merged at `b18a7e9`); CLI session from PR #25 (`feat/10-cli` at `803b205`) |
| Model | `claude-sonnet-5-5` (`ANTHROPIC_MODEL` default) |
| Filing | `data/apple_10k_2025.htm`, Apple FY2025 10-K (fiscal year ended September 27, 2025), accession 0000320193-25-000079 |
| Index | 197 Passages → 259 Index Entries, fastembed `BAAI/bge-small-en-v1.5` + BM25 (ADR-0002) |
| Web search | Tavily, `search_depth="advanced"`, `topic="finance"`, 5 results per search |
| Live runs | 9 in total: 5 through `build_agent` during #9, 4 through `python src/main.py` during #10 |

Token counts were not recorded for these runs; the planned evaluation suite adds per-run token accounting.

## Summary

| | Query 1: risk factors + R&D % | Query 2: gross margin vs Microsoft | Query 2, Tavily key invalid |
|---|---|---|---|
| Result | ✅ Correct | ⚠️ Apple half correct; Microsoft figure from a secondary source, different period | ✅ Degrades gracefully |
| Key figure | R&D 8.30% (34,550 / 416,161) | Apple 46.9% (195,201 / 416,161); Microsoft 67.94% FY2026 / 67.20% Q4 FY2026 | Apple 46.9% |
| Tools | 6 calls in 2 rounds: `get_passage` ×4, `search_filing` ×1, `calculate` ×1 | 10 calls in 4 rounds: `search_filing` ×3, `web_search` ×4, `calculate` ×3 | `search_filing` ×3, `web_search` ×2 (both failed), `calculate` ×1 |
| Time | 13 s | 25 s | 19 s |
| Sources | 4, all from the Filing | 10: 8 Filing, 2 web | 8, all from the Filing |

**Checked against the Filing** (Item 8, Consolidated Statements of Operations, p. 29): R&D $34,550M, total net sales $416,161M, gross margin $195,201M. All three match what the agent cited, and both percentages were computed with `calculate`, not by the model.

## Query 1: document-only analysis

> What are Apple's top 3 risk factors mentioned in their latest 10-K, and what percentage of total revenue did they spend on R&D?

Expected tools (TASKS.md): Document QA on Risk Factors, Document QA on R&D and total revenue. **Met**, plus `calculate` for the percentage.

### As the CLI shows it

```
$ python src/main.py
Ask a question about the filing, or type 'exit' to quit.
> What are Apple's top 3 risk factors mentioned in their latest 10-K, and what percentage of total revenue did they spend on R&D?
[Agent processing...]
[Plan] 1) get_passage — Fetch 'Item 1A' to get the outline of Apple's risk factors …
       2) get_passage — Fetch the first three risk factors from the Item 1A outline …
       3) search_filing — Search Item 8 with query 'research and development expense' and 'total net sales' …
       4) calculate — Compute R&D as a percentage of total net sales …
[Tool: get_passage "Item 1A"]
[Tool: search_filing(item="8") "research and development expense total net sales Consolidated Statements of Operations"]
[Tool: get_passage "item-1a-002"]
[Tool: get_passage "item-1a-003"]
[Tool: get_passage "item-1a-004"]
[Tool: calculate] 34550 / 416161 * 100 = 8.302075398703867
```

### Full answer (run through `build_agent`, final prompts)

```
**Note on "top 3":** Apple's 10-K does not rank its risk factors by importance. The three below are the
first three listed in Item 1A of the FY2025 10-K, in Filing order.

**First three risk factors listed (FY2025 10-K)**

1. **Global and regional economic conditions.** Sales outside the U.S. are a majority of net sales, and
   most supplier facilities are outside the U.S. Slow growth, recession, inflation, higher interest rates
   and currency swings can reduce consumer spending and demand. They can also strain suppliers and channel
   partners, and increase credit risk [1].
2. **Political events, trade disputes, geopolitical tension, natural disasters and other business
   interruptions.** A significant majority of manufacturing is done by outsourcing partners in China
   mainland, India, Japan, South Korea, Taiwan and Vietnam. Tariffs and other trade restrictions can raise
   costs, limit the availability of components and force supply-chain changes. The filing notes new U.S.
   tariffs announced beginning in the second quarter of 2025, and a Section 232 investigation into
   semiconductor imports. Natural disasters, public health issues and industrial accidents can also
   disrupt operations [2].
3. **Intense competition and rapid technological change.** Apple's markets involve aggressive price
   competition, downward pressure on gross margins and short product life cycles. Competing successfully
   requires "significant investments in R&D" that "may not achieve expected returns." Intellectual property
   protection and regulatory or litigation pressures add to the risk [3].

**R&D as a share of total revenue (FY2025, year ended September 27, 2025)**

- R&D expense was $34,550M [4].
- Total net sales were $416,161M [4].
- Calculation: $34,550M / $416,161M × 100 = **about 8.30%**.

This uses total net sales as the revenue figure, since the income statement has no separate "total
revenue" line.

Sources:
[1] 10-K FY2025 — Item 1A > Macroeconomic and Industry Risks > The Company's operations and performance
    depend significantly on global and regional economic conditions …, p. 5
[2] 10-K FY2025 — Item 1A > Macroeconomic and Industry Risks > The Company's business can be impacted by
    political events, trade and other international disputes …, p. 6
[3] 10-K FY2025 — Item 1A > Macroeconomic and Industry Risks > Global markets for the Company's products
    and services are highly competitive and subject to rapid technological change …, p. 7
[4] 10-K FY2025 — Item 8 > CONSOLIDATED STATEMENTS OF OPERATIONS, p. 29
```

### Notes

- **"Top 3" is interpreted as the first three listed in Item 1A**, with a caveat, because the 10-K doesn't rank risk factors. This is a deliberate prompt rule (#9).
- Both runs of Query 1 (`build_agent` and the CLI) used the same plan and gave the same three risks and 8.30%.
- The search uses the statement's line-item wording ("research and development expense") limited to Item 8. With a bare "research and development", the income statement doesn't rank in the top 5 (#5); the prompts steer the model to the line-item wording.

## Query 2: hybrid analysis (document + web)

> How does Apple's gross margin compare to Microsoft's current gross margin, and what reasons does Apple cite in their 10-K for any margin pressure?

Expected tools (TASKS.md): Document QA on Apple's gross margin, Document QA on MD&A, Tavily for Microsoft. **Met**, plus Item 1A for the risk factors behind margin pressure.

### Plan and trace (run through `build_agent`, final prompts)

```
PLAN:
1. search_filing — Search Item 8 for 'total net sales' and 'gross margin' (Consolidated Statements of
   Operations) for Apple's fiscal 2025 net sales and gross margin dollars.
2. search_filing — Search Item 7 for 'gross margin percentage' and 'products gross margin' for Apple's
   reported percentages and management's stated drivers.
3. search_filing — Search Item 1A for 'gross margin' / 'adverse effect on gross margin' to find risk
   factors citing margin pressure.
4. web_search — Find Microsoft's latest reported company-wide gross margin, preferring Microsoft's
   earnings release or SEC filing; if the percentage isn't stated, get revenue and cost of revenue.
5. calculate — Compute the gross margin percentages and the percentage-point difference.

[round 1] search_filing {"query": "gross margin percentage products gross margin services gross margin", "item": "7"} -> F1–F5
[round 1] search_filing {"query": "total net sales gross margin cost of sales", "item": "8"} -> F6–F10
[round 1] search_filing {"query": "adverse effect on gross margin tariffs component costs pricing pressure", "item": "1A"} -> F11–F15
[round 1] web_search {"query": "Microsoft fiscal year 2027 first quarter results gross margin revenue cost of revenue September 30, 2026"} -> W1–W5
[round 2] web_search {"query": "Microsoft Q1 FY27 gross margin percentage … quarter ended September 30, 2026 income statement"} -> W6–W10
[round 2] web_search {"query": "Microsoft FY27 Q1 earnings release gross margin dollars increased cost of revenue"} -> W2, W11–W14
[round 3] web_search {"query": "Microsoft September 30, 2026 quarter gross margin 10-Q … Microsoft Cloud gross margin percentage"} -> W15, W5, W16–W18
[round 4] calculate 195201 / 416161 * 100 = 46.905…
[round 4] calculate 46.9 - 67.94 = -21.04 (rounded)
[round 4] calculate 46.9 - 67.20 = -20.3 (rounded)
```

### Answer

Condensed: the risk-factor list is shortened here. The full text is in the PR #24 description.

```
Apple's gross margin is about 20 to 21 percentage points below Microsoft's. I could not find Microsoft's
gross margin for its latest quarter, so the Microsoft figures below are the most recent ones I could find.

**Apple (FY2025, year ended September 27, 2025)**
- Gross margin was $195,201M on total net sales of $416,161M [1]. That works out to 46.9%, which matches
  the 46.9% Apple reports [2].
- By segment, Products was 36.8% and Services was 75.4% [2]. Total gross margin was 46.2% in FY2024 [2].

**Microsoft**
- Microsoft's latest quarter is fiscal Q1 2027 (quarter ended September 30, 2026). Revenue was $92.3B and
  operating income was $45.9B [3]. The sources I found did not give cost of revenue or gross margin for
  that quarter.
- The closest company-wide figures come from a secondary aggregator, Business Quant (date unknown) [4]:
  fiscal Q4 2026 67.20%; full fiscal year 2026 67.94%; fiscal year 2025 68.82%.
- These figures are not Microsoft's own filings, and they cover different periods from Apple's.

**Comparison**
- Apple's 46.9% is 21.04 points below Microsoft's FY2026 67.94%, and 20.3 points below fiscal Q4 2026's 67.20%.
- Apple's Services margin of 75.4% is higher than Microsoft's company-wide margin; its hardware-heavy
  Products margin of 36.8% pulls the total down.

**Reasons Apple cites for margin pressure**
- Products gross margin fell from 37.2% to 36.8%, mainly from a different product mix and tariff costs,
  partly offset by other favorable costs [5][2].
- Services margin rose to 75.4% on mix, partly offset by higher costs [6].
- Apple expects gross margins to "be subject to volatility and downward pressure" [6].
- Risk factors list pricing pressure, competition, weak demand, short product life cycles, supply
  shortages, component/manufacturing/content costs, quality and warranty costs, mix shifts, foreign
  exchange, inflation, tariffs and trade restrictions, and lower-margin new products [7]; plus new U.S.
  tariffs from Q2 2025 [8], single-source components [9] and currency risk [10].

Sources:
[1] 10-K FY2025 — Item 8 > CONSOLIDATED STATEMENTS OF OPERATIONS, p. 29
[2] 10-K FY2025 — Item 7 > Gross Margin, p. 24
[3] Microsoft posts 32% rise in Q1 FY27 net income to $36.6bn —
    https://finance.yahoo.com/news/microsoft-posts-32-rise-q1-082820492.html (date unknown)
[4] Microsoft (MSFT) Gross Margin (2009 - 2026) | Business Quant —
    https://businessquant.com/metrics/msft/gross-margin-growth-5y (date unknown)
[5] 10-K FY2025 — Item 7 > Gross Margin > Products Gross Margin, p. 24
[6] 10-K FY2025 — Item 7 > Gross Margin > Services Gross Margin, p. 24
[7] 10-K FY2025 — Item 1A > Financial Risks > The Company's net sales and gross margins are subject to
    volatility and downward pressure due to a variety of factors., p. 15
[8] 10-K FY2025 — Item 1A > Macroeconomic and Industry Risks > … political events, trade and other
    international disputes …, p. 6
[9] 10-K FY2025 — Item 1A > Business Risks > … obtain components in sufficient quantities …, p. 8
[10] 10-K FY2025 — Item 1A > Financial Risks > … changes in the value of the U.S. dollar …, p. 15
```

The CLI run of the same query (PR #25) took a similar route: Items 8, 7 and 1A, five web searches, then `calculate 195201 / 416161 * 100` and `67 - 46.9`. It reported Microsoft at 67% for fiscal Q4 2026, citing a Yahoo Finance article and Microsoft's own FY2026 Q4 earnings-call page, again flagged as a different period from Apple's.

### Notes

- **The Apple half is correct and fully cited**: 46.9% agrees with both the income statement and Apple's own MD&A figure.
- **The Microsoft half is the weak spot.** Tavily never returned Microsoft's investor-relations release or 10-Q for the latest quarter, so the figure comes from an aggregator. The agent labels it as secondary, gives its period and says "date unknown". This follows the prompt rules from #9, but the answer is less authoritative than it should be.
- **The periods differ**: Apple's full fiscal year to September 2025 against Microsoft's FY2026 or a single quarter. The agent states this, but a reader comparing "current" margins should note the mismatch.
- **An earlier run was wrong.** The first Query 2 run during #9 reported Microsoft Cloud's 66% *segment* margin as Microsoft's gross margin. The prompts were fixed (commit `51dc883`: don't treat a segment margin as company-wide; compute from revenue and cost of revenue if needed), and the runs above come after that fix. Nothing guards against this regressing apart from re-running; the planned evaluation suite has it as a trap case.
- Web results from Tavily usually have no `published_date`, so web citations read "date unknown".

## Query 2 with an invalid Tavily key

Run with `TAVILY_API_KEY=tvly-invalid` set in the process environment only, to check graceful degradation (#9 acceptance).

```
[round 1] search_filing … item 8 / item 7 / item 1A -> ok
[round 1] web_search "Microsoft fiscal year 2027 first quarter results …" -> ERROR: Web search failed: Tavily rejected the API key (unauthorized).
[round 2] web_search "Microsoft earnings release gross margin percentage latest quarter" -> ERROR: Web search failed: Tavily rejected the API key (unauthorized).
[round 3] calculate 195201 / 416161 * 100 = 46.9

**Short answer:** I could only find Apple's side of the comparison. Web search failed twice with an
authorization error, so I have no Microsoft gross margin figure. I haven't filled that gap from memory, so
I can't say how the two compare.

**Apple's gross margin (FY2025)** — 46.9% ($195,201M / $416,161M) [1][2]; FY2024 46.2%, FY2023 44.1%;
Products 36.8%, Services 75.4% [2].

**Microsoft's current gross margin** — missing. To finish the comparison you would need Microsoft's
company-wide revenue and cost of revenue for its latest reported period …

**Reasons Apple cites for margin pressure** — [same Item 7 and Item 1A reasons as above, 8 Filing sources]
```

The agent retried once with a different query, then answered the half it could, named the missing data and did not invent a Microsoft figure. Tool failures reached the model as `is_error` results; nothing crashed.

## Other CLI behaviour seen in the same session

- A question cancelled with Ctrl-C during the planning call printed `[Cancelled]` and returned to the prompt.
- `python src/main.py --query "<query 1>" --quiet` exited 0 and wrote only the answer and Sources to stdout; stderr held a single "Reusing the stored index: 259 Index Entries." log line.

## Known weaknesses to track

1. **Competitor figures depend on what Tavily returns.** Primary sources (IR releases, 10-Q) were not found for Microsoft's latest quarter. Options: steer queries toward `microsoft.com/investor` or `sec.gov`, or use Tavily's `include_domains` for a second, primary-sources-only search.
2. **Period alignment in comparisons.** "Current" for Microsoft and "latest 10-K" for Apple are different periods. The agent flags it but doesn't align them (for example, by comparing Apple's latest quarter).
3. **No token or cost figures** were captured for these runs.
4. **Run-to-run variation.** Query 2 picked different Microsoft periods (FY2026 vs fiscal Q4 2026) and sources between runs. Only repeated runs, as in the planned evaluation suite, can measure this.
