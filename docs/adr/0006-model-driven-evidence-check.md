# A model-driven evidence check with model-written retries

Query 2 asks for Microsoft's current company-wide gross margin. `web_search` usually returns the Microsoft Cloud *segment* margin, which Microsoft headlines, or aggregator pages with undated figures. The executor declined to pass the segment figure off as company-wide, but nothing in the flow noticed that its evidence was weak and tried again (issue #29).

We add an **evidence check** between the executor's draft answer and the final answer. `EvidenceReviewer` makes one structured-output call through the `ChatModel` port, the same pattern as `Planner`, with its prompt in `prompts/evidence_check_prompt.txt`. The call gets the question, the plan, every tool call with the cited result the executor saw, and the draft. It returns an `EvidenceReview`: `sufficient`, plus `gaps`, each with a `requirement`, a `problem` (`missing`, `segment_not_company_wide`, `secondary_source`, `undated_or_stale`, `period_mismatch`, `other`) and `retry_guidance`. When it lists gaps, they go back to the executor as a user turn (`prompts/evidence_retry.txt`) and the tool loop continues. **The model decides the follow-up searches from what the evidence lacks, so the same check works for any company, metric or source.**

Bounds:

- At most `MAX_EVIDENCE_RETRIES = 1` check-triggered retry per question.
- Retry rounds share `MAX_TOOL_ROUNDS`. No check runs once the budget is spent, and the retry turn says how many rounds are left.
- The check is advisory. A failed API call, refusal, cut-off reply or invalid review (including `sufficient` contradicting `gaps`) is logged as a warning and the draft is returned. The check never blocks an answer.

## Considered Options

- **Tavily `include_domains` / a primary-source allow-list** (e.g. `microsoft.com`, `sec.gov`). Rejected: it hard-codes one competitor's sources, does not generalise to another company or metric, and has to be maintained by hand.
- **Fixed query templates for competitor metrics** (e.g. always search "<company> earnings release income statement"). Rejected for the same reason. A fixed recipe also cannot tell a segment figure from a company-wide one.
- **A self-critique paragraph in the system prompt.** Rejected. The executor already has the segment and primary-source rules, and still stops early. A separate call with a narrow job and a typed output can be tested, observed (`[Check] …`) and bounded.
- **Unlimited check/retry cycles.** Rejected. Cost and latency grow with each cycle, and the web may simply not hold the figure. One retry inside the existing round budget keeps the worst case at today's limits plus one model call per check.
- **Forced `tool_choice` for the review.** Not possible: `claude-sonnet-5-5` rejects a forced tool choice, so structured outputs are used, as in the Planner.

## Consequences

- Every question costs one more model call (the check), and a retry adds the extra tool rounds and executor turns it uses. Query 1 normally passes the check and answers with no extra round.
- A retry can still end without a primary source. The check can point the executor at the right *kind* of source, but only the web search tool decides what comes back. In the #29 live runs, Tavily (finance topic, 5 snippets) did not return Microsoft's own release or 10-Q income statement. The honest-gap rule in the system prompt still applies to the final answer.
- A retry can push a run into the round limit (`hit_round_limit`), as the first #29 run did before the review prompt was narrowed to one gap per fact.
- Revisit if the check's guidance keeps failing for lack of page content. A page-fetch tool would let the executor read a release the search only links to, and that fix belongs in the tools, not in a source list.
