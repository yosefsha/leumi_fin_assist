# Financial Research Assistant

A command-line AI agent that answers questions about Apple Inc. from Apple's FY2025 Form 10-K
(the **Filing**) and live web search. It plans its approach, calls tools (hybrid retrieval over
the Filing, Tavily web search, an exact calculator), checks its evidence before answering, and
cites every claim to a Section Path and
page of the Filing or to a dated web source.

It is built for the two test queries of the assignment ([`docs/TASKS.md`](docs/TASKS.md)):

1. *"What are Apple's top 3 risk factors mentioned in their latest 10-K, and what percentage of
   total revenue did they spend on R&D?"*
2. *"How does Apple's gross margin compare to Microsoft's current gross margin, and what reasons
   does Apple cite in their 10-K for any margin pressure?"*

```
$ finassist
Financial Research Assistant — Apple 10-K (FY2025) + web search
Try one of these, or type your own question:
  1) What are Apple's top 3 risk factors mentioned in their latest 10-K, and what percentage of total revenue did they spend on R&D?
  2) How does Apple's gross margin compare to Microsoft's current gross margin, and what reasons does Apple cite in their 10-K for any margin pressure?
  …
  6) By what percentage did Apple's Services net sales grow from fiscal 2024 to fiscal 2025?
Type a number, a question, 'help' to show this list again, or 'exit' to quit.
> 1
Question: What are Apple's top 3 risk factors mentioned in their latest 10-K, and what percentage of total revenue did they spend on R&D?
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
[Check] evidence sufficient

**Note on "top 3":** Apple's 10-K does not rank its risk factors by importance. …
…
- Calculation: $34,550M / $416,161M × 100 = **about 8.30%**.

Sources:
[1] 10-K FY2025 — Item 1A > Macroeconomic and Industry Risks > The Company's operations and performance depend significantly on global and regional economic conditions …, p. 5
…
[4] 10-K FY2025 — Item 8 > CONSOLIDATED STATEMENTS OF OPERATIONS, p. 29
```

## Contents

1. [Setup](#setup)
2. [Running the agent](#running-the-agent)
3. [How to run the test queries](#how-to-run-the-test-queries)
4. [Example outputs](#example-outputs)
5. [Architecture overview](#architecture-overview)
6. [Technical specification](#technical-specification)
7. [Dependencies](#dependencies)
8. [Bonus features implemented](#bonus-features-implemented)
9. [Known limitations](#known-limitations)
10. [Future work](#future-work)
11. [Project structure](#project-structure)
12. [Decision records](#decision-records)
13. [Development workflow](#development-workflow)

---

## Setup

Requirements: **Python 3.12** (the code uses 3.12 syntax), an
[Anthropic API key](https://console.anthropic.com/) and a [Tavily API key](https://tavily.com/)
(the free tier gives 1,000 searches a month). About 1 GB of disk for the dependencies, the
embedding model and the index.

1. **Clone the repository.**

   ```bash
   git clone https://github.com/yosefsha/leumi_fin_assist.git
   cd leumi_fin_assist
   ```

2. **Create a Python 3.12 virtual environment, install the dependencies and the `finassist`
   command.**

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   pip install -e .                   # installs the finassist command into the venv
   ```

   If `python3.12` is not found, [uv](https://docs.astral.sh/uv/) fetches a 3.12 interpreter for you:

   ```bash
   uv venv --python 3.12 .venv
   source .venv/bin/activate
   uv pip install -r requirements.txt
   uv pip install -e .
   ```

   Install it **editable** (`-e`): the command runs the code in `src/` and reads `prompts/`,
   `data/` and `.env` from this checkout, so it works from any directory while the venv is
   active. `pip install -e .` alone also installs the dependencies (it reads
   `requirements.txt`). Without the install, `python src/main.py` takes the same arguments.

3. **The Filing is already in the repository**: `data/apple_10k_2025.htm`, Apple's 10-K for the
   fiscal year ended September 27, 2025 (accession `0000320193-25-000079`, filed 2025-10-31).
   It was downloaded from Apple's
   [SEC EDGAR page](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193)
   (filing index:
   [`000032019325000079`](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/),
   document `aapl-20250927.htm`). Nothing to download. To use another 10-K, see
   `FILING_PATH` and `FILING_FISCAL_YEAR` under [Configuration](#configuration).

4. **Add your API keys.**

   ```bash
   cp .env.example .env
   # edit .env and set ANTHROPIC_API_KEY and TAVILY_API_KEY
   ```

   Every other setting has a working default. Real environment variables override `.env`.

5. **Run it.**

   ```bash
   finassist                  # or: python src/main.py
   ```

   The **first run** downloads the embedding model (`BAAI/bge-small-en-v1.5`, about 130 MB) into
   `.index/models` and builds the Filing index in `.index/chroma` (about 20 s of embedding on a
   laptop CPU). Later runs reuse both and skip the build, unless the Filing, the embedding model
   or the index format changes.

   During the download, stderr shows Hugging Face progress bars and a warning about
   unauthenticated requests (`HF_TOKEN`); both are harmless. If the download stalls, disable
   Hugging Face's Xet transfer and retry; CI does the same:

   ```bash
   HF_HUB_DISABLE_XET=1 finassist
   ```

---

## Running the agent

```bash
finassist                            # interactive prompt with a menu of suggested questions
finassist "QUESTION"                 # answer one question, then exit
finassist 2                          # run suggested question 2, then exit
finassist --quiet "QUESTION"         # stdout gets only the answer and its Sources
finassist --rebuild-index            # rebuild the Filing index first, even if current
finassist --help                     # usage, examples and the numbered suggested questions
```

`python src/main.py` is equivalent and takes the same arguments (`python src/main.py "QUESTION"`,
`python src/main.py 1`), as does the original `--query QUESTION` form, which stays as an alias:
`python src/main.py --query "QUESTION"` is the form [`docs/TASKS.md`](docs/TASKS.md) shows.

- **Interactive mode** prints a title, the numbered suggested questions (from
  [`prompts/suggested_questions.txt`](prompts/suggested_questions.txt)) and a `> ` prompt. Type
  a number to run that suggestion (the question is echoed as `Question: …` first), or type your
  own question. `help` or `?` lists the suggestions again; a number with no suggestion gets a
  one-line message. `exit`, `quit`, Ctrl-D, or Ctrl-C at the prompt leaves (exit status 0).
  Blank lines are ignored. Ctrl-C **while a question is running** cancels that question
  (`[Cancelled]`) and returns to the prompt.
- **A single question** comes as the argument (`finassist "QUESTION"`) or with `--query`. An
  argument that is only a number runs that suggested question (`finassist 1`); a number with
  no suggestion is a usage error (exit status 2).
- **Each answer** is preceded by `[Agent processing...]`, the `[Plan]`, and one `[Tool: …]` line
  per tool call as it runs (`[Tool error: … — reason]` for a failed call; `calculate` shows its
  result). A `[Check] …` line reports the evidence check on the draft answer: `evidence
  sufficient`, or `<n> gap(s): <requirement> — <problem> → retrying` when the agent goes back
  for more evidence. Then the answer and a numbered **Sources** list.
- **`--quiet`** drops the progress line, plan, trace and `[Check]` lines. stdout then carries
  only answers and Sources; the menu, the prompt, the `Question: …` echo, notes and errors go
  to stderr.
- **Logs** go to stderr at `LOG_LEVEL` (default `INFO`). Third-party libraries are only shown
  at WARNING and above unless `LOG_LEVEL=DEBUG`, which also logs token usage per model call.

Exit statuses are listed in the [CLI spec](#cli).

---

## How to run the test queries

The two test queries are suggestions 1 and 2.

**Interactively** — start `finassist` and type `1` or `2` at the `> ` prompt (or paste either
query).

**One at a time:**

```bash
finassist 1          # Query 1: risk factors + R&D share of revenue
finassist 2          # Query 2: Apple vs Microsoft gross margin + margin pressure
```

The equivalent long forms, as [`docs/TASKS.md`](docs/TASKS.md) runs the agent (copy-paste ready):

```bash
python src/main.py --query "What are Apple's top 3 risk factors mentioned in their latest 10-K, and what percentage of total revenue did they spend on R&D?"

python src/main.py --query "How does Apple's gross margin compare to Microsoft's current gross margin, and what reasons does Apple cite in their 10-K for any margin pressure?"
```

**As automated tests** — [`tests/test_queries.py`](tests/test_queries.py) runs both queries
end to end through the real agent and checks the run's structure and figures, not its wording:

```bash
RUN_LIVE_TESTS=true pytest -m live -v -s
```

| Check | Query 1 | Query 2 |
|---|---|---|
| Tools | `search_filing` scoped to Item 8; Item 1A consulted (search or `get_passage`); `calculate` called | `search_filing` scoped to Items 8 and 7; `web_search` called |
| Sources | ≥ 3 distinct risk-factor Passages; Item 8 cited | ≥ 1 Filing Passage and ≥ 1 web source |
| Figures | R&D share of net sales within tolerance of the value computed from the parsed income statement (8.30%) | Apple gross margin within tolerance (46.9%) |

`-s` prints each run's plan, tool trace (round, tool, arguments, citation IDs), evidence checks
(with each gap's retry guidance) and full answer with Sources, even when the test passes; on failure they are in the assertion message anyway.
The two runs take one to two minutes together (66 s in the last recorded run, which included an
evidence-check retry on Query 2).

**Live tests are off by default.** Each run spends Anthropic tokens and Tavily quota, so the
`live` tests are skipped ("set RUN_LIVE_TESTS=true to run") unless `RUN_LIVE_TESTS=true` is set
in the environment or `.env`. With the switch on, a missing API key fails the test instead of
skipping it. See [ADR-0004](docs/adr/0004-hybrid-test-tiers-and-ci.md).

**Offline tests** need no keys and make no paid calls (only the one-time model download):

```bash
pip install ruff            # the linter is a development tool, not in requirements.txt
ruff check .
pytest -m "not live"        # 210 tests, about 20–70 s (most of it embedding the Filing once)
```

Plain `pytest` runs the offline tier and reports the two live tests as skipped.

**In CI** — `.github/workflows/ci.yml` installs the `finassist` command, runs `finassist --help`
from outside the project, then `ruff check .` and `pytest -m "not live"`, on every pull request
and every push to `main`. `.github/workflows/live-tests.yml` runs the live tier
only on a manual "Run workflow", or on pushes to `main` touching `src/` or `prompts/` when the
repository variable `RUN_LIVE_TESTS` is `true` (it is left unset). It uses its own
`ANTHROPIC_API_KEY` / `TAVILY_API_KEY` repository secrets.

---

## Example outputs

Full, annotated runs (plans, traces, complete answers, timings, and a run with a broken Tavily
key) are in [`docs/query-run-results.md`](docs/query-run-results.md). Excerpts, model
`claude-sonnet-5-5`:

### Query 1 — document only (13–14 s, 6 tool calls in 2 rounds)

The trace is shown at the top of this README. Answer:

```
**Note on "top 3":** Apple's 10-K does not rank its risk factors by importance. The three below are the
first three listed in Item 1A of the FY2025 10-K, in Filing order.

1. **Global and regional economic conditions.** … [1]
2. **Political events, trade disputes, geopolitical tension, natural disasters and other business
   interruptions.** … new U.S. tariffs announced beginning in the second quarter of 2025 … [2]
3. **Intense competition and rapid technological change.** … [3]

**R&D as a share of total revenue (FY2025, year ended September 27, 2025)**
- R&D expense was $34,550M [4].
- Total net sales were $416,161M [4].
- Calculation: $34,550M / $416,161M × 100 = **about 8.30%**.

Sources:
[1] 10-K FY2025 — Item 1A > Macroeconomic and Industry Risks > The Company's operations and performance
    depend significantly on global and regional economic conditions …, p. 5
[2] 10-K FY2025 — Item 1A > Macroeconomic and Industry Risks > The Company's business can be impacted by
    political events, trade and other international disputes …, p. 6
[3] 10-K FY2025 — Item 1A > Macroeconomic and Industry Risks > Global markets for the Company's products
    and services are highly competitive and subject to rapid technological change …, p. 7
[4] 10-K FY2025 — Item 8 > CONSOLIDATED STATEMENTS OF OPERATIONS, p. 29
```

### Query 2 — document + web (25–38 s, about 10 tool calls in 3–4 rounds; about 50 s with an evidence-check retry)

```
[Plan] 1) search_filing — Search Item 8 for 'total net sales' and 'gross margin' …
       2) search_filing — Search Item 7 for 'gross margin percentage' and 'products gross margin' …
       3) search_filing — Search Item 1A for 'gross margin' / 'adverse effect on gross margin' …
       4) web_search — Find Microsoft's latest reported company-wide gross margin, preferring its
          earnings release or SEC filing …
       5) calculate — Compute the gross margin percentages and the percentage-point difference.
[Tool: search_filing(item="7") "gross margin percentage products gross margin services gross margin"]
[Tool: search_filing(item="8") "total net sales gross margin cost of sales"]
[Tool: search_filing(item="1A") "adverse effect on gross margin tariffs component costs pricing pressure"]
[Tool: web_search "Microsoft fiscal year 2027 first quarter results gross margin revenue cost of revenue …"]
…
[Tool: calculate] 195201 / 416161 * 100 = 46.905…
```

```
**Apple (FY2025, year ended September 27, 2025)**
- Gross margin was $195,201M on total net sales of $416,161M [1]. That works out to 46.9%, which matches
  the 46.9% Apple reports [2].
- By segment, Products was 36.8% and Services was 75.4% [2].

**Microsoft**
- … The closest company-wide figures come from a secondary aggregator, Business Quant (date unknown) [4]:
  fiscal Q4 2026 67.20%; full fiscal year 2026 67.94% …
- These figures are not Microsoft's own filings, and they cover different periods from Apple's.

**Reasons Apple cites for margin pressure**
- Products gross margin fell from 37.2% to 36.8%, mainly from a different product mix and tariff costs … [5][2]
- Apple expects gross margins to "be subject to volatility and downward pressure" [6].
- Risk factors list pricing pressure, competition, … tariffs and trade restrictions … [7] …

Sources:
[1] 10-K FY2025 — Item 8 > CONSOLIDATED STATEMENTS OF OPERATIONS, p. 29
[2] 10-K FY2025 — Item 7 > Gross Margin, p. 24
[3] Microsoft posts 32% rise in Q1 FY27 net income to $36.6bn — https://finance.yahoo.com/… (date unknown)
[4] Microsoft (MSFT) Gross Margin (2009 - 2026) | Business Quant — https://businessquant.com/… (date unknown)
…
```

The Apple half is correct and fully cited (46.9% agrees with both the income statement and
Apple's MD&A). The Microsoft half is the known weak spot; see
[Known limitations](#known-limitations). That excerpt predates the evidence check (#29). Now the
draft answer is checked, and when the Microsoft figure is a segment, secondary or missing figure,
the agent searches again with the check's guidance:

```
[Check] 1 gap: Microsoft company-wide gross margin, latest quarter (Q1 FY2027, quarter ended
        Sept 30, 2026) — secondary_source → retrying
[Tool: web_search "Microsoft FY27 Q1 income statement total cost of revenue 10-Q September 30, 2026 …"]
…
[Tool: calculate] (45.9 + 16.6) / 92.3 * 100 = 67.71…
```

In that run the final answer computed Microsoft's company-wide margin, (92.3 − 29.7) / 92.3 =
67.8%, from revenue and cost of revenue, cross-checked it at 67.7%, and said both inputs came
from secondary sources. The three #29 runs are in
[`docs/query-run-results.md`](docs/query-run-results.md).

---

## Architecture overview

```
          finassist / python src/main.py  (cli/: options, menu + REPL or one question, trace, exit codes)
                                   │ question
                                   ▼
 ┌──────────────────────────── ResearchAgent (src/agent.py) ─────────────────────────────┐
 │ 1. Planner ── one structured-output call ──► Plan [{tool, purpose}] ──► [Plan] trace   │
 │ 2. Executor: Anthropic native tool use, ≤ 8 tool rounds, parallel calls per round       │
 │        │  ToolRegistry.dispatch(name, args) → ToolOutput(content, sources, is_error)    │
 │        ▼                                                                                │
 │  ┌──────────────┬──────────────┬──────────────┬──────────────┐                          │
 │  │search_filing │ get_passage  │  web_search  │  calculate   │                          │
 │  └──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────┘                          │
 │         │ FilingSearch │ CrossRef-    │ WebSearch-   │ ast allow-list                   │
 │         ▼              ▼ Resolver     ▼ Client       ▼ (no eval)                        │
 │  FilingIndex: dense (Chroma) + BM25 → RRF     Tavily API                                │
 │         ▲                                                                               │
 │  Index Entries / Table Cards ◄ Chunker ◄ Passages ◄ FilingParser ◄ data/*.htm           │
 │                                                                                         │
 │ 3. ToolResultCiter: each source gets [F#]/[W#] from a per-question CitationRegistry     │
 │ 4. EvidenceReviewer: draft answer + cited evidence ── one structured-output call ──►    │
 │    sufficient → answer │ gaps + retry guidance → back to 2 (once, same 8-round budget)   │
 │ 5. CitationResolver: final answer's markers validated → [1]… + Sources list             │
 └─────────────────────────────────────────────────────────────────────────────────────────┘
                                   │ AgentResult (plan, trace, evidence checks, cited answer)
                                   ▼
                       answer + Sources on stdout
```

### How tools are registered

Every tool implements the `Tool` protocol in [`src/tools/registry.py`](src/tools/registry.py):
`name`, `description`, `input_schema` (a JSON Schema generated from the tool's Pydantic argument
model) and `run(args) -> ToolOutput`. `ToolRegistry.register` checks the name against
Anthropic's rules and rejects duplicates; `definitions()` produces the Messages API `tools`
list; `dispatch(name, args)` runs a call by name (an unknown name is an error result, not an
exception).

The four tools are registered in one place, the composition root
[`src/agent_factory.py`](src/agent_factory.py): `build_tool_registry(index, web_client)` wires
`SearchFilingTool`, `GetPassageTool`, `WebSearchTool` and `CalculateTool` over their ports, and
`build_agent(settings)` opens the Filing index and injects the concrete Anthropic and Tavily
adapters. Adding a tool means one new class and one `register` line; the agent loop does not
change.

### How the agent decides which tool to use

Three stages, all driven by prompts in `prompts/`:

1. **Planning** (Bonus 3). One structured-output call returns a `Plan`: ordered `{tool,
   purpose}` steps, with `tool` constrained by the schema to a registered tool name. The planner
   prompt encodes the routing rules: facts Apple reports come from the Filing, current or
   external facts (competitors, prices) from `web_search`; reported figures are in Item 8 (search
   with the statement's line-item wording), management's explanation in Item 7, risks in
   Item 1A; "top N risk factors" means `get_passage("Item 1A")` then the first N; every
   percentage or difference goes through `calculate`.
2. **Execution**. The question and the numbered plan go to the model with all four tool
   definitions and `tool_choice: auto`. The model chooses tools itself, using the plan as
   guidance rather than a script: it may skip steps, add some (e.g. follow a "see Note 5"
   with `get_passage`), retry with different wording, or issue several independent calls in one
   turn, which run concurrently.
3. **Evidence check** ([ADR-0006](docs/adr/0006-model-driven-evidence-check.md)). When the
   model answers without calling a tool, that draft and every tool result it saw (with citation
   IDs, titles, URLs and dates) go to one structured-output call. The call returns an
   `EvidenceReview`: `sufficient`, or `gaps`, each with a `requirement`, a `problem`
   (`missing`, `segment_not_company_wide`, `secondary_source`, `undated_or_stale`,
   `period_mismatch`, `other`) and `retry_guidance`. Gaps go back to the executor as a user
   turn, and tool use resumes. The model writes the guidance (for example "find the latest
   earnings release's revenue and cost of revenue and compute the margin with `calculate`"), so
   the same check works for any company, metric or source.

### How information flows

```
data/apple_10k_2025.htm
  → FilingParser        Passages: one subsection, risk factor, Note or table each,
                        with Item, Section Path, page (197 Passages)
  → Chunker             Index Entries: ≤ 350-token excerpts prefixed with their Section Path;
                        tables become Table Cards (259 entries)
  → embed + store       fastembed bge-small (384-d) in Chroma; BM25 over the same texts
  → search_filing       dense top-50 + BM25 top-50 → Reciprocal Rank Fusion → whole Passages
  → ToolResultCiter     each Passage / web result registered → [F1], [W1] … shown to the model
  → model's answer      cites [F#]/[W#] after each claim
  → CitationResolver    unknown IDs dropped, the rest renumbered [1] … → Sources list
```

### Where prompts are stored

All prompt text lives in [`prompts/`](prompts/); code never hard-codes it.
`load_prompt(name)` reads `prompts/<name>.txt` and `render_prompt` fills `{{placeholders}}`,
failing if a placeholder and its value don't match.

| File | Role |
|---|---|
| `system_prompt.txt` | Executor rules: which source for which fact, Item scoping and query wording, "top N" risk factors, `calculate` for all arithmetic, primary vs secondary web sources and periods, segment vs company-wide metrics, citation format, how to report gaps. Placeholders `{{fiscal_year}}`, `{{today}}`. |
| `planner_prompt.txt` | The planning call: usually 2–6 steps, each naming a tool and its purpose, with the routing rules above. Placeholders `{{fiscal_year}}`, `{{today}}`, `{{tools}}`. |
| `tool_descriptions.txt` | One `## <tool>` section per tool, used as the tool's `description` for both the planner and the executor. |
| `round_limit.txt` | Appended after the 8th tool round: answer now with the evidence gathered, cite only known IDs, and name what is missing. |
| `evidence_check_prompt.txt` | The evidence check: what each gap `problem` means, which gaps not to report (wording, facts the question does not ask for, Filing facts to replace with newer ones), how to write retry guidance (company's own statements first, components plus `calculate` when a ratio is not stated, new query wording, never a segment for the company), at most three gaps, one per fact. Placeholders `{{fiscal_year}}`, `{{today}}`, `{{tools}}`. |
| `suggested_questions.txt` | The CLI's numbered suggested questions, one per line (`#` comments): the two test queries first, then a Filing-only, a web-only, a cross-reference (Note) and a calculation question. Not sent to the model. |
| `evidence_retry.txt` | The user turn that sends the gaps back: the numbered gaps with their guidance, the tool rounds left, and "write the complete answer again". Placeholders `{{gaps}}`, `{{rounds_left}}`. |

---

## Technical specification

Reference-level detail, checked against the code. Domain terms (Filing, Item, Section Path,
Passage, Index Entry, Table Card, Citation) are defined in [`CONTEXT.md`](CONTEXT.md).

### Components

| Module | Responsibility |
|---|---|
| `src/main.py` | Entry point (`main`, also the `finassist` console script): load the suggested questions → parse options → load `Settings` → configure logging → `build_agent` → `run_cli`. |
| `src/cli/` | `cli_options` (argparse), `cli_app` (`run_cli`, exit codes), `repl`, `menu` + `suggested_questions` (the numbered suggestions and the welcome screen), `question_session` (one question: progress, answer, error, Ctrl-C), `trace_printer` + `tool_call_format` (live `[Plan]` / `[Tool: …]` / `[Check] …`), `answer_printer` (answer, Sources, notes), `question_answerer` (the port the CLI needs). |
| `src/agent.py` | `ResearchAgent.answer(question) -> AgentResult`: planner, the tool-use loop, and the evidence check with its one retry. |
| `src/agent_factory.py` | Composition root: `build_agent(settings, force_rebuild, observer)`, `build_tool_registry(index, web_client)`. |
| `src/tools/` | `registry` (`Tool`, `ToolOutput`, `ToolRegistry`), `search_filing`, `get_passage`, `tavily_search` (`web_search`), `calculator` + `arithmetic` (`calculate`), `argument_errors`, `passage_json`. |
| `src/utils/` — Filing | `filing_layout`, `filing_blocks`, `html_text`, `table_renderer` (HTML → ordered text/table blocks with pages; tables → Markdown), `filing_parser` (→ Passages), `filing_items`, `passage`. |
| `src/utils/` — index | `chunker`, `text_packer`, `table_card_builder`, `index_entry`, `filing_index_loader` (reuse/rebuild, 512-token guard), `filing_index_factory`, `filing_index` (hybrid search), `bm25_retriever`, `rank_fusion`, `passage_hit`, `cross_reference_resolver`, `resolved_reference`. |
| `src/utils/` — agent | `planner`, `plan`, `evidence_reviewer`, `evidence_review` (`EvidenceReview`, `Gap`, `GapProblem`), `tool_evidence`, `citations` (`CitationRegistry`), `tool_result_citer`, `citation_format`, `cited_answer` (`CitationResolver`), `agent_result`, `agent_observer`, `prompts`, `config`, `logging_config`. |

### Ports and adapters

Everything outside the process is reached through a `typing.Protocol` with its own error types,
injected at the composition root. Tests use the in-memory fakes in `tests/fakes/`.

| Port (Protocol) | Used by | Production implementation | Test double |
|---|---|---|---|
| `ChatModel` (`utils/chat_model.py`): `generate_json`, `respond` | `Planner`, `EvidenceReviewer`, `ResearchAgent` | `AnthropicChatModel` | `ScriptedChatModel` |
| `WebSearchClient` (`utils/web_search.py`): `search` | `WebSearchTool` | `TavilyWebSearchClient` | `ScriptedWebSearchClient` |
| `FilingSearch` (`utils/filing_search.py`): `items`, `search` | `SearchFilingTool` | `FilingIndex` | the real `FilingIndex` over `InMemoryIndexStore` |
| `IndexStore` (`utils/index_store.py`): `fingerprint`, `replace`, `entries`, `nearest` | `FilingIndexLoader`, `FilingIndex` | `ChromaIndexStore` | `InMemoryIndexStore` |
| `Embedder` (`utils/embedder.py`): `embed_documents`, `embed_query` | loader, `FilingIndex` | `FastEmbedEmbedder` | `ConstantEmbedder`, `CountingEmbedder` (spy) |
| `TokenCounter` (`utils/token_counter.py`): `count_tokens` | `TextPacker`, 512-token guard | `FastEmbedEmbedder` (untruncated tokenizer) | — |
| `Tool` (`tools/registry.py`) | `ToolRegistry` | the four tools | — |
| `AgentObserver` (`utils/agent_observer.py`): `on_plan`, `on_tool_call`, `on_evidence_check` | `ResearchAgent` | `TracePrinter` (CLI) | `SilentObserver` |
| `QuestionAnswerer` (`cli/question_answerer.py`): `answer` | CLI | `ResearchAgent` | stub agents in `test_cli.py` |

### Data model

**Passage** (`utils/passage.py`, frozen) — the returnable unit.

| Field | Meaning |
|---|---|
| `passage_id` | `<item-slug>-<NNN>`, numbered per Item in Filing order: `item-1a-002`, `item-8-021`, `front-matter-001`. |
| `item` | `Front Matter`, `Item 1` … `Item 16` (incl. `1A`, `1B`, `1C`, `7A`, `9A`–`9C`). |
| `section_path` | Heading trail, e.g. `("Item 7", "Gross Margin", "Products Gross Margin")`; written `Item 7 > Gross Margin > …`. |
| `page` / `page_approximate` | Printed page from the page footer; `None` only for the unnumbered cover; `approximate` when inferred. |
| `kind` | `section` (text under one heading), `risk_factor` (one Item 1A risk factor), `note` (a whole Note to the financial statements), `table` (one table as Markdown with its caption). |
| `content` | Markdown: `## heading`, paragraphs; a table inside text is replaced by a `_[Table: <caption>]_` line, the table being its own Passage. |

The shipped Filing parses to 197 Passages: 106 sections, 51 tables, 27 risk factors, 13 Notes.

**Index Entry** (`utils/index_entry.py`) — `entry_id` (`<passage_id>#NNN`), `passage_id`,
`item`, `kind`, `page`, `text`. The text is the Section Path prefix (plus any Note sub-heading),
a blank line, then the excerpt. Text Passages are packed from whole paragraphs up to
**350 model tokens** (oversized paragraphs are split) and an entry **never crosses a heading**.
A heading-only Passage gets one entry holding its heading.

**Table Card** — the Index Entry of a table: `Table: <caption>`, `Columns: …`, `Rows: …`, no
figures (the figures stay in the Passage the search returns). A card over the budget is split
by row groups, each repeating caption and columns.

**512-token guard** — before embedding, every entry is counted with an untruncated copy of the
model's tokenizer; any entry over the model's input limit (512) raises
`IndexEntryTooLongError` instead of being silently truncated. Largest entry today: 389 tokens.

**Index storage and reuse** — under `INDEX_DIR` (default `.index/`, git-ignored): the model
cache in `models/`, a persistent Chroma collection `filing_index_entries` (cosine HNSW, vectors
supplied by the app) in `chroma/`. BM25 (`rank_bm25` Okapi; lower-cased alphanumeric tokens,
English stop-words removed) is rebuilt in memory from the stored entries at start-up. The
stored index carries a fingerprint `sha256=<Filing hash>;model=<embedding model>;format=<INDEX_FORMAT_VERSION>`.
It is **reused** when the fingerprint matches and every stored entry points to a parsed
Passage; otherwise, or with `--rebuild-index`, it is rebuilt. The fingerprint is written last,
so an interrupted build reads back as "no index".

**Search** (`FilingIndex.search(query, limit, item)`) — the query is embedded with BGE's
retrieval instruction prefix; the dense store and BM25 each return their top 50 entries
(both filtered to `item` when given); the rankings are fused with Reciprocal Rank Fusion
(k = 60); entries collapse to their Passages, keeping each Passage's best rank, until `limit`
Passages are found.

### Tool contracts

Arguments are validated with Pydantic (`extra="forbid"`, whitespace stripped; `strict` for all
but `web_search`). Every expected failure is returned as a `ToolOutput` with `is_error=True` and
a short reason, never raised; an error result carries no sources. An unexpected exception inside
a tool is caught by the agent loop and returned as `Tool <name> failed unexpectedly (<Type>)`.

| Tool | Arguments | Returns | Error results |
|---|---|---|---|
| `search_filing` | `query`: string, 1–500 chars. `item`: optional, e.g. `"1A"`, `"7"`, `"8"` (`"Item 7"`, `"item 1a"` also accepted); omit for the whole Filing. `top_k`: int 1–10, default 5. | `content`: JSON `{query, item, passages_found}` (plus `message` when nothing matched — a normal, non-error result). `sources`: the whole Passages, best first. | Invalid arguments; unknown Item (lists the valid ones); embedder or index-store failure. |
| `get_passage` | `reference`: string, 1–100 chars: `"Note 5"`, `"Item 1A"`, `"Part II, Item 7"`, or a `passage_id`; a Note or Item may carry its title (`"Note 5 – Property, …"`). Case- and whitespace-insensitive. | `sources`: the resolved Passage. `content`: JSON `{reference, related: [{passage_id, kind, page, title}]}` — the Passages nested under it (a Note's tables, an Item's subsections / risk factors), to fetch by `passage_id`. | Invalid arguments; unrecognised form; a Note or Item the Filing lacks (lists the ones it has); a Part that does not contain the Item. |
| `web_search` | `query`: string, 1–400 chars (Tavily's limit). | `content`: JSON `{query, results_found}`. `sources`: up to 5 `WebResult`s (url, title, excerpt, published date or none). | Invalid arguments; timeout twice; rejected key; rate limit / quota; bad request; other HTTP or network error; malformed response; **no results** ("No web results found for …"). |
| `calculate` | `expression`: string, 1–500 chars, e.g. `"34550 / 416161 * 100"`. | `content`: JSON `{expression, result}`. No sources (not citable). | Invalid arguments; anything outside the allow-list; division by zero; limits exceeded; non-real or non-finite result; commas in numbers (with a hint to drop thousands separators). |

`web_search` details: Tavily is called with `search_depth="advanced"`, `topic="finance"`,
`max_results=5`, `include_answer=False`, no domain filter, and a 30 s timeout per attempt. A
timed-out search is **retried once**; any other failure is not retried. Results without a URL
are dropped (a web Citation is its URL).

`calculate` details: the expression is parsed with `ast` and walked against an allow-list —
int/float literals, `+ - * / ** %`, unary `+`/`-`, parentheses, `round(x[, ndigits])`, `abs(x)`.
Names, attributes, calls to anything else, comparisons, strings and keywords are rejected before
any arithmetic runs. Limits: every literal, intermediate and result |value| ≤ 10^21; exponent
|n| ≤ 64; `round` `ndigits` an integer in −15…15. **Never `eval`/`exec`.**

### Agent loop

**Planner** (`utils/planner.py`). One `messages.create` call with `output_config.format` =
JSON Schema of `Plan` (structured outputs), the step's `tool` an `enum` of the registered tool
names. A forced `submit_plan` tool was the original design, but `claude-sonnet-5-5` rejects a
forced `tool_choice`, so structured output is used instead. A refusal, a reply cut off before
its JSON is complete, or a reply that fails validation yields an **empty plan** with a warning
(`[Plan] none — working from the question alone`); the executor proceeds. An API failure
propagates as `ChatModelError`.

**Executor** (`agent.py`).

| Rule | Value |
|---|---|
| First user turn | `<question>…</question>` plus `<plan>` (numbered steps) when the plan is non-empty |
| System prompt | `system_prompt.txt` with the Filing's fiscal year and today's date |
| Tool choice | `auto` for rounds 1–8 |
| Tool rounds | at most `MAX_TOOL_ROUNDS = 8`; after the 8th, `round_limit.txt` is appended to the tool results and the next turn is called with `tool_choice: none`, so the model must answer; `hit_round_limit` is set |
| Parallel calls | all `tool_use` blocks of one turn run concurrently (thread pool, one worker per call); results are cited and returned in call order, in one user message |
| Output limit | `max_tokens = 16000` per call; a tool call cut off by the limit raises `ChatModelError`; a cut-off final answer is returned with `answer_truncated` set |
| Retries | Anthropic SDK `max_retries = 3` (connection errors, 408, 409, 429, 5xx, with backoff) |
| Failures | API failure after retries, refusal, or a final turn with no text → `ChatModelError` with a one-line, key-free message; tool failures are `is_error` results the model works around |
| Ctrl-C | an interrupted round shuts its pool down without waiting for in-flight calls |
| Evidence check | runs on a text-only turn while tool rounds remain and no retry has been used; gaps → the `evidence_retry.txt` turn and the loop continues; at most `MAX_EVIDENCE_RETRIES = 1` per question; never after the round budget is spent |

**Evidence check** (`utils/evidence_reviewer.py`). One structured-output call
(`generate_json`, schema `EvidenceReview.json_schema()`) with `evidence_check_prompt.txt`. The
user turn holds `<question>`, `<plan>`, `<evidence>` and `<draft_answer>`. `<evidence>` has one
`<tool_call round name>` block per call, with its arguments and the cited result as the
executor saw it. `EvidenceReview` rejects a `sufficient` flag that contradicts its `gaps`. Any
failure (API error after retries, refusal, cut-off JSON, invalid review) logs a warning and
returns an `EvidenceCheck` with no review. The draft is then the answer (`[Check] unavailable —
keeping the draft answer`). The check never fails a run.

**Citations** (`citations.py`, `tool_result_citer.py`, `cited_answer.py`).

- IDs are assigned **by code**, never by the model: `F1, F2, …` for Filing Passages, `W1, W2, …`
  for web results, in the order tool results arrive.
- A **fresh `CitationRegistry` per question**, so IDs never leak between questions.
- The same Passage (by `passage_id`) or URL keeps its first ID. When a later call returns it
  again, the model sees only its header line marked `(content shown above)`.
- Model-facing headers: `[F3] Item 8 > CONSOLIDATED STATEMENTS OF OPERATIONS — p. 29 (passage_id item-8-…, table)`
  then the content; `[W1] <title> — <url> (as of <date> | date unknown)` then the excerpt.
- In the final answer, `[F1]` and grouped `[F1, W2]` markers are resolved. **Unknown IDs are
  dropped** (logged as a warning); known ones are renumbered `[1], [2], …` by first appearance.
- Sources lines: `10-K FY<year> — <Section Path>, p. <n>` (`(approx.)` if the page was
  inferred) and `<title> — <url> (as of <date> | date unknown)`. With nothing cited the CLI
  prints `Sources: none cited.`

**`AgentResult`** (`agent_result.py`, frozen): `question`, `plan`, `trace` (tuple of
`ToolCallRecord`: `round`, `name`, `args`, `output`, `is_error`, `citation_ids`), `answer`
(`CitedAnswer`: `body`, `sources`, `text`), `hit_round_limit`, `answer_truncated`,
`evidence_checks` (tuple of `EvidenceCheck`: `review` — an `EvidenceReview`, or `None` when the
check failed).

### CLI

`finassist [QUESTION | NUMBER] [--query QUESTION] [--quiet] [--rebuild-index]`

`finassist` is a console script (`[project.scripts]` in `pyproject.toml`, `main:main`) installed
by `pip install -e .`; `python src/main.py` takes the same arguments. Relative paths (`.env`,
`FILING_PATH`, `INDEX_DIR`, `prompts/`) resolve against the project root, so the command works
from any directory.

| Argument / flag | Effect |
|---|---|
| *(none)* | Interactive mode: title, numbered suggested questions, prompt `> `. At the prompt: a number runs that suggestion (echoed as `Question: …`); an out-of-range number gets one line, and the list is not re-printed; `help` / `?` lists the suggestions again; `exit` / `quit` (any case), Ctrl-D or Ctrl-C leaves; anything else is the question. |
| `QUESTION` | Answer once and exit. An empty question is a usage error. |
| `NUMBER` | Run that suggested question once (echoed as `Question: …`) and exit. A number with no suggestion is a usage error. |
| `--query QUESTION` | Alias of `QUESTION`, kept for existing scripts; a number works the same way. Giving both is a usage error. |
| `--quiet` | No progress line, plan, trace or `[Check]` lines. stdout: only answers and Sources. Menu, prompt, echo, notes and errors: stderr. |
| `--rebuild-index` | Rebuild the Filing index before starting, even if it is current. |

The suggestions come from [`prompts/suggested_questions.txt`](prompts/suggested_questions.txt);
`finassist --help` lists them with usage examples, and needs no API keys.

| Exit status | When |
|---|---|
| `0` | Answered (single question), or the interactive session was left normally. A failed or cancelled question in interactive mode returns to the prompt and does not change the status. |
| `1` | The model API failed for a single question (after retries), or the Filing index cannot be opened or built. |
| `2` | Invalid usage (argparse, including an out-of-range suggestion number) or configuration (e.g. a missing API key, an invalid `LOG_LEVEL`). |
| `130` | Ctrl-C during a single question or during start-up (index loading). |

stdout carries the menu, trace, answers and Sources; errors (`Error: …`), `[Cancelled]` and
logs always go to stderr. Two notes can follow an answer: the tool-round limit was reached, or
the answer hit the output limit.

### Configuration

Read only by `Settings` (`src/utils/config.py`) from `.env` overlaid by the process environment
(a blank environment variable does not override `.env`). Relative paths resolve against the
repository root, so the working directory does not matter. API keys are excluded from
`Settings`' repr and never appear in an error message or a log line.

| Variable | Required | Default | Validation / notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | — | Non-blank; a missing key exits 2 naming the variable. |
| `TAVILY_API_KEY` | yes | — | Non-blank; as above. |
| `ANTHROPIC_MODEL` | no | `claude-sonnet-5-5` | Any model that supports tool use and structured outputs. |
| `FILING_PATH` | no | `data/apple_10k_2025.htm` | The 10-K HTML to answer from. |
| `FILING_FISCAL_YEAR` | no | `2025` | Four-digit year, no leading zero. Written into every Filing citation as `10-K FY<year>` and into the prompts. Change it together with `FILING_PATH`. |
| `INDEX_DIR` | no | `.index` | Holds `models/` (embedding model) and `chroma/` (index). |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` (case-insensitive). |
| `RUN_LIVE_TESTS` | no | `false` | Read by the test suite only (`tests/live_switch.py`): `true` (case-insensitive) runs the `live` tests. |

### Error handling and security

- **Fail loudly at the boundary.** Configuration is validated at start-up; tool arguments are
  validated by Pydantic before any work; a malformed Tavily response is rejected by a Pydantic
  model; the index build refuses an over-long entry rather than truncating it.
- **Transport errors never leak.** Every Anthropic SDK error becomes `ChatModelError` (HTTP
  status / connection / timeout, model name); every Tavily or `requests` error becomes
  `WebSearchError` / `WebSearchTimeoutError`; Chroma, SQLite and filesystem errors become
  `IndexStoreError`; model-loading errors `EmbedderError`. Messages are one line and key-free —
  an offline test runs the real Tavily client with failing responses that contain the key and
  checks the key appears in neither logs nor tool output.
- **The model cannot fabricate sources.** It only ever sees code-assigned IDs, and markers
  without a registered source are dropped from the answer.
- **The calculator never evaluates code** (`ast` allow-list, bounded values, no `eval`/`exec`).
- **Prompt names are file stems** (`[a-z0-9_]+`), so `load_prompt` cannot read outside
  `prompts/`.
- No secrets in the repository: `.env` and `.index/` are git-ignored; CI uses repository
  secrets, which are not passed to workflows triggered from forks.

### Testing

Two tiers ([ADR-0004](docs/adr/0004-hybrid-test-tiers-and-ci.md)):

| Tier | Where | Count | Runtime | Covers |
|---|---|---|---|---|
| Offline | `tests/offline/` | 210 | ~20–70 s locally (≈ 21 s of it embedding the Filing once per session); +~10 s the first time for the model download | parser (13), hybrid index and rebuild rules (8), `calculate` incl. attack cases (25), citations (5), `web_search` incl. key-leak check (17), Anthropic adapter error mapping (9), agent loop and evidence check over a scripted model (37), CLI incl. menu, arguments and running from another directory (74), prompts and settings (10), the live switch (12) |
| Live | `tests/test_queries.py` | 2 | ~40–55 s (one agent run per query) | the two required queries end to end against Anthropic and Tavily (see [the checks above](#how-to-run-the-test-queries)) |

Fixtures in `tests/conftest.py` parse and embed the Filing once per session, caching the model
in `.index/models` like the app. CI: `ci.yml` (lint + offline, every PR and push to `main`,
model cache keyed on the model name), `live-tests.yml` (manual or repo-variable gated),
`claude-review.yml` (automated Claude PR review on every non-draft PR).

### Performance

Measured on a developer laptop (CPU only); sources in brackets.

| Operation | Time | Source |
|---|---|---|
| Index build: parse + chunk + embed 259 entries | ~21 s | PR #20, PR #22 |
| Loading a reusable index (no re-embedding) | ~0.3 s | PR #20 |
| CLI start-up to the `> ` prompt, index reused | ~1.4 s | fresh-clone check, PR for #12 |
| First run in a fresh clone: model download (~6 s) + index build (~19 s) + Query 1 | 53 s | fresh-clone check, PR for #12 |
| Query 1 end to end | 13–14 s (6 tool calls, 2 rounds) | `docs/query-run-results.md`, PR #27 |
| Query 2 end to end | 25–38 s (~10 tool calls, 3–4 rounds) | `docs/query-run-results.md`, PR #27 |
| Query 2 with an evidence-check retry | ~50 s (~15 tool calls, 6–7 rounds) | `docs/query-run-results.md`, PR for #29 |
| Live suite (both queries) | 42 s; 66 s with a Query 2 evidence-check retry | PR #27; PR for #29 |
| Evidence check | one extra model call per question; a retry adds the tool rounds and executor turns it uses (Query 2: 2–3 more rounds) | PR for #29 |
| `calculate` | < 0.5 ms per expression | PR #18 |

Cost: the evidence check adds one `generate_json` call per question. Its input is the whole
cited evidence, so it is about as large as the executor's last turn. A retry adds its own
rounds on top. Query 1 normally passes the check with no retry. Token usage per run has not
been recorded yet (the evaluation suite, #26, adds it);
`LOG_LEVEL=DEBUG` logs input/output tokens per model call.

---

## Dependencies

Minimum versions are pinned in [`requirements.txt`](requirements.txt).

| Package | Purpose | Why this one |
|---|---|---|
| `anthropic` | LLM calls: structured-output planning, native tool use | The assignment allows any provider; the native tool-use API and structured outputs remove the need for an agent framework. A hand-written loop (`src/agent.py`, under 200 lines) behind a `ChatModel` port keeps tool choice, citations and limits visible and testable; LangChain/LlamaIndex would add abstraction without adding capability here. |
| `tavily-python` | Web search | Required by the assignment; finance topic and advanced depth suit competitor figures. |
| `fastembed` | Local embeddings, `BAAI/bge-small-en-v1.5` (ONNX, 384-d, CPU) | Anthropic has no embeddings API; local embedding avoids a third key and per-token cost, and ONNX avoids pulling in torch (~2 GB). See [ADR-0002](docs/adr/0002-local-embeddings-and-passage-retrieval.md). |
| `tokenizers` | Untruncated token counts for the 512-token guard | fastembed's own count caps at 512 and would hide an over-long entry. |
| `chromadb` | Persistent local vector store | Embedded, no server, persists between runs, supports metadata filters (by Item). |
| `rank-bm25` | Keyword retrieval fused with dense search | Dense embeddings are weak at exact financial terms ("research and development expense"); BM25 recovers them (ADR-0002). |
| `beautifulsoup4`, `lxml` | Parse the Filing's inline-XBRL HTML | Robust on SEC HTML, fast parser; headings, page footers and tables are read from inline styles. No XBRL fact tool: [ADR-0003](docs/adr/0003-no-xbrl-fact-tool.md). |
| `pydantic` | Validation at boundaries: tool arguments (and their JSON Schemas), Tavily responses, the Plan | One model gives both validation and the schema the LLM sees. |
| `python-dotenv` | Load `.env` | Standard, tiny. |
| `pytest` | Both test tiers | Standard; markers separate the `live` tier. |

Development only (not in `requirements.txt`): `ruff` for linting (configured in
`pyproject.toml`). `pip install -e .` builds the `finassist` command with
`setuptools` (the `[build-system]` in `pyproject.toml`; pip fetches it), taking the dependency
list from `requirements.txt`.

---

## Bonus features implemented

All four optional bonuses from the assignment:

| Bonus | What it does | Where |
|---|---|---|
| 1. Structured table extraction | Each `<table>` becomes its own table Passage rendered as Markdown, with `$`/`%` cells merged into their figures, spacer columns dropped, and the caption kept. It is indexed through a Table Card (caption, column headers, row labels), so a search for a line item finds the table and returns the full figures with their headers. | `utils/table_renderer.py`, `utils/filing_parser.py`, `utils/table_card_builder.py` |
| 2. Page-level citations | Every Passage carries the printed page number from the Filing's page footer; every Filing source cites Section Path and page (`… > Gross Margin, p. 24`). | `utils/filing_layout.py`, `utils/citation_format.py` |
| 3. Planning step | A structured-output planning call before any tool runs, shown as `[Plan] 1) … 2) …` and passed to the executor as guidance. | `utils/planner.py`, `utils/plan.py`, `prompts/planner_prompt.txt` |
| 4. Cross-reference handling | `get_passage` follows "Note 5", "Item 1A", "Part II, Item 7" or a `passage_id`, and lists the Passages nested under the target. Text Passages mark their tables as `_[Table: …]_`, and the system prompt tells the model to follow such markers and Note references with `get_passage`. | `utils/cross_reference_resolver.py`, `tools/get_passage.py` |

---

## Known limitations

From the recorded runs in [`docs/query-run-results.md`](docs/query-run-results.md):

1. **Microsoft's company-wide gross margin still rarely comes from Microsoft itself.** The
   evidence check (ADR-0006) catches a segment, secondary or missing figure and sends the agent
   back with model-written guidance: find the earnings release or 10-Q, or find revenue and cost
   of revenue and compute the margin with `calculate`. It triggered a retry in all three #29
   Query 2 runs. In one, the retry produced a company-wide figure computed from components
   (67.8%). In another it found none and the answer named the gap. In the third, an earlier
   version of the check prompt, the retry ran into the round limit. In none of the runs did
   Tavily (finance topic, 5 snippets) return Microsoft's own release or income statement, so
   the inputs stay secondary and the answer says so. The Apple half is always correct. A
   page-fetch tool would let the model read the release it finds (Future work).

   Before and after the evidence check, 2026-11-03: Query 2 run twice from `main` before PR #30
   and twice after it, same machine and settings
   ([full comparison](docs/query-run-results.md#before-and-after-the-evidence-check-2026-11-03)):

   | | Before 1 | Before 2 | After 1 | After 2 |
   |---|---|---|---|---|
   | Microsoft web searches | 5 | 5 | 7, then `[Check]`, then 5 more | 6, then output ends |
   | Evidence check | — | — | 2 gaps (`secondary_source`, `undated_or_stale`) → retry | no result recorded |
   | Microsoft company-wide margin | not found | not found | 67.9% (FY2026), 67.2% (quarter to June 2026), aggregators, flagged secondary | — |
   | Comparison with Apple's 46.9% | none | none | about 20–21 points higher, periods flagged | — |
   | Primary Microsoft source | no | no | no | — |
   | Round limit reached | no | no | yes | — |

   The check makes the agent search harder and state the weakness of its evidence, and it can
   turn "no comparison" into an approximate, caveated one. It does not reach a primary source:
   before the check, the executor was already searching for the earnings release, 10-Q and
   cost of revenue. The bottleneck is the search tool's snippets, not the agent's reasoning.
   The saved output of After 2 ends after its second `calculate`, before the check's result.
   Errors go to stderr, which the saved file did not capture, so that run is not counted.
2. **A retry can use up the round budget.** Retry rounds share the 8-round limit. In After 1
   the first pass used most of the budget (3 Filing searches, 7 web searches and 2
   calculations) before the check, so the retry ended at the limit and the answer carried the "tool-call limit" note. It was still complete and
   cited.
3. **A search-results page can be cited.** Tavily sometimes returns a search-engine results
   URL (After 1 cited a DuckDuckGo results page for Microsoft's revenue). The citation is
   genuine but weak; the source is a list of links, not a publication.
4. **Period mismatch.** Apple's figure is its full fiscal year to September 2025; Microsoft's
   "current" figure is a later fiscal year or quarter. The agent states the mismatch but does
   not align the periods.
5. **Undated web results.** Tavily results usually have no `published_date`, so web citations
   read "date unknown".
6. **Run-to-run variation.** Query 2 has picked different Microsoft periods and sources across
   runs. The live tests assert structure and the Apple figures, not a Microsoft figure, because
   web data drifts.
7. **One Filing at a time.** The agent answers from a single 10-K (`FILING_PATH`); it cannot
   compare two years of filings. Replacing the Filing triggers a re-index automatically.
8. **"Top N" risk factors** are the first N listed in Item 1A, since the 10-K does not rank
   them; the answer says so.
9. **No token or cost accounting** yet. The evidence check adds one model call per question,
   and a retry adds more (see [Performance](#performance)).

---

## Future work

- **Evaluation suite with token accounting** (backlog issue #26): a versioned case set (the two
  queries, the segment-vs-company-wide margin trap, the "top N" caveat, a cross-reference and an
  unanswerable question) scored by deterministic checks, run by hand with
  `python src/run_evals.py`, reporting tokens per phase and comparing with a committed baseline.
- **A page-fetch tool** so the executor can read a release or 10-Q that a search result only
  links to (limitation 1). The evidence check already asks for such sources; the search
  snippets lack the income-statement tables.
- **Better retrieval recall** if needed: `bge-base-en-v1.5` is the documented upgrade
  (ADR-0002); swapping models is a re-index.
- **XBRL facts** as Table Card metadata or a fact tool, if a wrong figure is traced to table
  rendering (ADR-0003).
- **Streaming output** and prompt caching for lower latency and cost.

---

## Project structure

```
.
├── README.md                 this guide
├── CLAUDE.md                 rules for AI coding agents (branches, worktrees, PRs)
├── CONTEXT.md                domain glossary
├── requirements.txt          minimum-pinned dependencies (Python 3.12)
├── pyproject.toml            the finassist command (packaging) + ruff + pytest configuration
├── .env.example              every setting, documented
├── data/apple_10k_2025.htm   the Filing (FY2025, accession 0000320193-25-000079)
├── prompts/                  system_prompt, planner_prompt, tool_descriptions, round_limit,
│                             evidence_check_prompt, evidence_retry, suggested_questions (.txt)
├── src/
│   ├── main.py               entry point
│   ├── agent.py              ResearchAgent: planner + tool-use loop + evidence check
│   ├── agent_factory.py      composition root: build_agent, build_tool_registry
│   ├── cli/                  options, menu of suggested questions, REPL, question session,
│   │                         trace and answer printers
│   ├── tools/                Tool protocol + registry; search_filing, get_passage, web_search, calculate
│   └── utils/                config, prompts, logging; Filing parser; chunker + hybrid index;
│                             ports and adapters (Anthropic, Tavily, Chroma, fastembed);
│                             planner, evidence reviewer; citation registry, formatter and resolver
├── tests/
│   ├── conftest.py           session fixtures (parsed Filing, built index), RUN_LIVE_TESTS gate
│   ├── live_switch.py        the RUN_LIVE_TESTS switch and key checks
│   ├── fakes/                in-memory port fakes
│   ├── offline/              offline tier (210 tests)
│   └── test_queries.py       live tier: the two required queries
├── docs/
│   ├── TASKS.md              the assignment brief
│   ├── query-run-results.md  recorded runs of both queries (example outputs)
│   ├── handover.md           project status, team process, open items
│   ├── adr/                  architecture decision records 0001–0004, 0006
│   ├── coding-instructions.md, backend-python-instructions.md   code standards
├── .github/workflows/        ci.yml, live-tests.yml, claude-review.yml
├── .claude/                  Claude Code agents and skills (/implement-issue, /implement-milestone)
└── scripts/                  repo-template tooling, not part of the product
```

**How this maps to the layout in `docs/TASKS.md`:**

| TASKS.md | This repo | Why |
|---|---|---|
| `src/tools/document_qa.py` | `src/tools/search_filing.py` (hybrid search) and `src/tools/get_passage.py` (open a Section, Note or Passage by reference), on top of the parser and index in `src/utils/` | Document QA is two tools so the model can search, then follow a cross-reference ("see Note 5") directly (Bonus 4). |
| `src/tools/tavily_search.py` | `src/tools/tavily_search.py` (`web_search`) | Same file. |
| — | `src/tools/calculator.py` (`calculate`) | The assignment asks for calculations; all arithmetic goes through this tool. |
| `prompts/examples.txt` (optional) | not used | The planning step and the per-tool descriptions guide the model; few-shot examples were not needed for the two queries. |
| `data/apple_10k_2023.htm` | `data/apple_10k_2025.htm` | The latest 10-K at the time of writing (FY2025). |

## Decision records

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-cli-agent-assignment-layout-no-ci.md) | Python CLI in the assignment's folder layout. Its "no CI" part is superseded by 0004. |
| [0002](docs/adr/0002-local-embeddings-and-passage-retrieval.md) | Local fastembed embeddings + BM25 hybrid retrieval over Passages; 350-token entries; fail on > 512 tokens. |
| [0003](docs/adr/0003-no-xbrl-fact-tool.md) | No XBRL fact tool: figures come from rendered tables, arithmetic from `calculate`. |
| [0004](docs/adr/0004-hybrid-test-tiers-and-ci.md) | Two test tiers: offline tests in CI on every PR; live query tests only with `RUN_LIVE_TESTS=true`. |
| [0006](docs/adr/0006-model-driven-evidence-check.md) | A model-driven evidence check judges the draft's evidence and may send the executor back once with model-written retry guidance. |

Smaller decisions (hand-written agent loop, structured-output planner, code-assigned citation
IDs, the 8-round cap) are recorded in the bodies of issues #8 and #9.

## Development workflow

- One issue → one branch → one git worktree (`.claude/worktrees/<n>-<slug>`) → one PR into
  `main`; the primary checkout stays on a clean `main`. Full rules in [`CLAUDE.md`](CLAUDE.md).
- A PR is done when CI (`ruff check .` + offline tests) is green and the `Claude review`
  workflow has run on the latest push with every comment fixed or answered. Only a human
  merges.
- After changing `prompts/` or `ANTHROPIC_MODEL`, run the live tier and record the run in
  `docs/query-run-results.md`.
- Project status, team conventions, open items and risks for whoever picks the project up:
  [`docs/handover.md`](docs/handover.md) and the pinned tracker issue #15.
