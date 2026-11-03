# Financial Research Assistant

A command-line AI agent that answers questions about Apple Inc. using Apple's FY2025 10-K
filing plus live web search. It cites every claim, either to a section and page of the 10-K
or to a dated web source.

> **Handover note.** This README is written for the incoming tech lead. It explains what the
> project is for, how the code is organised, what is built and what is still planned, and how
> the team works. The user-facing README sections the assignment asks for (setup, how to run
> the test queries, example outputs) are tracked in issue #12 and will be added once the agent
> runs end to end.

---

## 1. Goal

The project is a home assignment (full brief: [`docs/TASKS.md`](docs/TASKS.md)). The agent must:

1. Parse and query Apple's 10-K (the **Filing**) through a retrieval-based Document QA tool.
2. Use **Tavily** web search for data that isn't in the Filing or has changed since it was
   filed, such as stock prices and competitors' figures.
3. Do arithmetic on financial figures exactly, not by LLM guesswork.
4. Combine the sources into one answer with **citations**, and say clearly when information is
   missing.

It is judged on two required queries:

| # | Query | Tools it should use |
|---|---|---|
| 1 | "What are Apple's top 3 risk factors … and what percentage of total revenue did they spend on R&D?" | Document QA (Item 1A), Document QA (Item 8), calculate |
| 2 | "How does Apple's gross margin compare to Microsoft's current gross margin, and what reasons does Apple cite … for margin pressure?" | Document QA (Item 8 + Item 7), web search |

All four optional bonuses are in scope: structured table extraction, page-level citations, a
planning step, and cross-reference handling (for example, following "See Note 5").

Reference figure for Query 1, from the FY2025 Filing: R&D $34,550M / net sales $416,161M ≈ **8.30%**.

---

## 2. Current status

The live progress tracker is pinned **issue #15** ("Project status & resume guide"). Read it
first, and update it after each merge. Snapshot as of 2026-11-03:

| Milestone | Issues | State |
|---|---|---|
| M1 — Foundation | #1 docs/ADRs, #2 scaffold + config + tool registry + Filing | ✅ merged |
| M2 — Document QA | #3 filing parser → #4 chunker + hybrid index → #5 `search_filing` / `get_passage` | ✅ merged |
| M3 — Web search & calc | #6 Tavily `web_search`, #7 `calculate` | ✅ merged |
| M4 — Agent & CLI | #8 citation registry, #9 planner + executor, #10 CLI | ✅ merged |
| M5 — Delivery | #21 offline test tier + CI, #11 live test queries, #12 user README | #21 merged; #11 in review; #12 last |

Critical path: **#3 → #4 → #5 → #9 → #10 → #11 → #12**. Issues #6, #7 and #8 can run in
parallel with M2.

Each issue body holds the agreed design decisions and acceptance criteria. Treat them as the
spec. Changing a decision means updating the issue (and an ADR, if it's architectural).

---

## 3. Architecture

### Target design

```
                         ┌──────────────────────── src/main.py (CLI, REPL / --query) ───────────────────────┐
 user question ────────► │                                                                                  │
                         │  src/agent.py                                                                    │
                         │   1. Planner call ── forced `submit_plan` tool ──► Plan [{tool, purpose}]        │
                         │   2. Executor loop (Anthropic native tool use, ≤ 8 rounds, parallel tool calls)  │
                         │          │                                                                       │
                         │          ▼  ToolRegistry.dispatch(name, args) → ToolOutput                       │
                         │   ┌──────────────┬───────────────┬──────────────┬─────────────┐                  │
                         │   │ search_filing│  get_passage  │  web_search  │  calculate  │                  │
                         │   └──────┬───────┴──────┬────────┴──────┬───────┴─────────────┘                  │
                         │          │              │               │                                        │
                         │          ▼              ▼               ▼                                        │
                         │   Hybrid index (Chroma dense + BM25, RRF)   Tavily API                            │
                         │          ▲                                                                       │
                         │   Index Entries ◄── chunker ◄── Passages ◄── filing parser ◄── data/*.htm        │
                         │                                                                                  │
                         │   3. CitationRegistry: tool results tagged [F1]/[W1] → validated → Sources list  │
                         └──────────────────────────────────────────────────────────────────────────────────┘
                                                   answer + plan/tool trace + Sources
```

**Information flow.** Filing HTML → **Passages** (one subsection, risk factor, note or table,
each carrying its Item, Section Path and page) → **Index Entries** (≤350-token excerpts; tables
become **Table Cards**) → hybrid search returns whole Passages → the agent cites them by ID → the
IDs are checked against the citation registry, so the model can't invent a source.

### Main design decisions

| Decision | Where |
|---|---|
| Python CLI in the assignment's folder layout | [ADR-0001](docs/adr/0001-cli-agent-assignment-layout-no-ci.md) |
| Two test tiers: offline tests + ruff in CI on every PR; live query tests only when `RUN_LIVE_TESTS=true` (default off) | [ADR-0004](docs/adr/0004-hybrid-test-tiers-and-ci.md) |
| Local embeddings (fastembed `bge-small-en-v1.5`) + BM25 hybrid retrieval over Passages; the index build fails if an entry exceeds 512 tokens instead of truncating it silently | [ADR-0002](docs/adr/0002-local-embeddings-and-passage-retrieval.md) |
| No XBRL fact-lookup tool: figures come from rendered tables, arithmetic goes through `calculate` | [ADR-0003](docs/adr/0003-no-xbrl-fact-tool.md) |
| Anthropic SDK with a hand-written agent loop, no framework (LangChain etc.), behind a `ChatModel` port | issue #9 |
| Planning step is one structured-output call (`output_config.format`) returning `Plan(steps=[{tool, purpose}])`, not a forced `submit_plan` tool: `claude-sonnet-5-5` rejects forced `tool_choice` | issue #9 |
| Tools return their Passages / web results as `ToolOutput.sources`; the agent loop registers them and shows them to the model under `[F#]`/`[W#]` before the model sees anything, so every ID the model can cite was assigned by code | issues #8, #9 |
| At most 8 tool rounds per question, parallel `tool_use` blocks run concurrently; at the cap the model gets one tool-free turn to answer with what it has and name the gaps | issue #9 |
| Citation IDs are assigned by code when tool results are returned, never by the model | issue #8 |
| `calculate` parses with `ast` against an allow-list and never uses `eval`/`exec` | issue #7 |

Domain vocabulary (Filing, Item, Section Path, Passage, Index Entry, Table Card, Citation) is
defined in [`CONTEXT.md`](CONTEXT.md). Use these terms in code, issues and reviews.

---

## 4. Repository structure

What exists today is marked ✅. The rest is planned, with the issue that adds it.

```
.
├── README.md                      ✅ this handover (user sections → #12)
├── CLAUDE.md                      ✅ rules for AI coding agents: branches, worktrees, PRs (humans follow them too)
├── CONTEXT.md                     ✅ domain glossary
├── requirements.txt               ✅ minimum-pinned dependencies (Python 3.12)
├── pyproject.toml                 ✅ ruff + pytest configuration
├── .env.example                   ✅ all settings, documented
├── data/
│   └── apple_10k_2025.htm         ✅ the Filing (FY2025, accession 0000320193-25-000079, filed 2025-10-31)
├── docs/
│   ├── TASKS.md                   ✅ the assignment brief (source of truth for scope and testing)
│   ├── adr/                       ✅ architecture decision records 0001–0004
│   ├── coding-instructions.md     ✅ design principles (SOLID, fail loudly, ports for external sources)
│   └── backend-python-instructions.md ✅ Python style rules
├── src/
│   ├── main.py                    ✅ CLI entry point: options → settings → logging → `run_cli`
│   ├── cli/
│   │   ├── cli_options.py         ✅ `--query` / `--quiet` / `--rebuild-index` (argparse)
│   │   ├── cli_app.py             ✅ `run_cli`: build the agent once, then one `--query` or the REPL; exit codes
│   │   ├── repl.py                ✅ `> ` loop: `exit`/`quit`/Ctrl-D/Ctrl-C leave, blank lines ignored
│   │   ├── question_session.py    ✅ one question: progress line, answer, one-line API error, Ctrl-C cancels
│   │   ├── question_outcome.py    ✅ `QuestionOutcome`: answered / failed / cancelled (→ exit status)
│   │   ├── question_answerer.py   ✅ `QuestionAnswerer` protocol the CLI needs (`ResearchAgent` implements it)
│   │   ├── trace_printer.py       ✅ `TracePrinter`: the `AgentObserver` that prints `[Plan]` / `[Tool: …]` live
│   │   ├── tool_call_format.py    ✅ one-line tool-call descriptions (`search_filing(item="1A") "…"`, `calculate` result)
│   │   └── answer_printer.py      ✅ the answer, its Sources, and round-limit / truncation notes
│   ├── agent.py                   ✅ `ResearchAgent`: planner call, then the tool-use executor loop (≤ 8 rounds)
│   ├── agent_factory.py           ✅ `build_agent(settings)`: the composition root (index + tools + Anthropic)
│   ├── tools/
│   │   ├── registry.py            ✅ `Tool` protocol, `ToolOutput` (content + citable `sources`), `ToolRegistry`
│   │   ├── search_filing.py       ✅ `SearchFilingTool` (search_filing): hybrid search, optionally within one Item
│   │   ├── get_passage.py         ✅ `GetPassageTool` (get_passage): follow "Note 5" / "Item 1A" / a passage_id
│   │   ├── tavily_search.py       ✅ `WebSearchTool` (web_search): one retry on timeout, failures as error results
│   │   ├── calculator.py          ✅ `CalculateTool` (calculate)
│   │   └── arithmetic.py          ✅ `ast` allow-list evaluator behind `calculate` (no `eval`/`exec`)
│   └── utils/
│       ├── config.py              ✅ `Settings`: .env + environment, validated, secrets kept out of repr/logs
│       ├── prompts.py             ✅ `load_prompt(name)` reads prompts/<name>.txt; `render_prompt` fills `{{placeholders}}`
│       ├── logging_config.py      ✅ logging to stderr; third-party records below WARNING dropped unless DEBUG
│       ├── passage.py             ✅ `Passage` value object + `PassageKind`
│       ├── filing_parser.py       ✅ `FilingParser`: HTML → Passages (Items, headings, risk factors, Notes)
│       ├── filing_layout.py       ✅ HTML → ordered text/table/anchor blocks with page numbers
│       ├── table_renderer.py      ✅ `<table>` → Markdown (merges `$`/`%` cells, drops spacer columns)
│       ├── html_text.py           ✅ visible text and bold/italic emphasis of inline-styled elements
│       ├── chunker.py             ✅ `Chunker`: Passages → Index Entries (≤350-token excerpts, never across a heading)
│       ├── text_packer.py         ✅ packs whole paragraphs into a token budget, splitting oversized ones
│       ├── table_card_builder.py  ✅ table Passage → Table Cards (caption, column headers, row labels)
│       ├── index_entry.py         ✅ `IndexEntry` value object
│       ├── embedder.py            ✅ `Embedder` protocol (+ `token_counter.py`: `TokenCounter` protocol)
│       ├── fastembed_embedder.py  ✅ fastembed `bge-small-en-v1.5` (ONNX); untruncated token counts
│       ├── index_store.py         ✅ `IndexStore` protocol + `IndexStoreError`
│       ├── chroma_index_store.py  ✅ persistent Chroma collection at `INDEX_DIR/chroma`
│       ├── bm25_retriever.py      ✅ BM25 (`rank_bm25`) over the same entries
│       ├── rank_fusion.py         ✅ Reciprocal Rank Fusion
│       ├── filing_index.py        ✅ `FilingIndex.search(query, limit, item)` → `PassageHit`s (one per Passage)
│       ├── filing_index_loader.py ✅ reuse the stored index or rebuild (content hash, `force_rebuild`, 512-token guard)
│       ├── filing_index_factory.py ✅ `open_filing_index(settings, force_rebuild)`: wires the concrete adapters
│       ├── filing_search.py       ✅ `FilingSearch` port that `search_filing` depends on (`FilingIndex` implements it)
│       ├── cross_reference_resolver.py ✅ `CrossReferenceResolver`: "Note 5", "Part II, Item 7", passage_id → Passage + nested Passages
│       ├── web_search.py          ✅ `WebSearchClient` protocol (returns `WebResult`s), `WebSearchError`
│       ├── tavily_web_search_client.py ✅ Tavily implementation of `WebSearchClient`
│       ├── web_result.py          ✅ `WebResult`: one web page (URL, title, excerpt, date or `None`), searched and cited
│       ├── citations.py           ✅ `CitationRegistry`: code-assigned `F#`/`W#` IDs per query
│       ├── citation_format.py     ✅ `CitationFormatter`: tool-result headers and Sources lines
│       ├── cited_answer.py        ✅ `CitationResolver`: drops unregistered markers, renumbers `[1]…`
│       ├── tool_result_citer.py   ✅ `ToolResultCiter`: registers a tool result's sources, renders them under `[F#]`/`[W#]`
│       ├── chat_model.py          ✅ `ChatModel` port, `ModelReply`, `ChatModelError` / `ChatModelRefusalError`
│       ├── anthropic_chat_model.py ✅ Anthropic implementation (`max_retries=3`, key-free one-line errors)
│       ├── plan.py                ✅ `Plan` / `PlanStep` and the planner's JSON schema
│       ├── planner.py             ✅ `Planner`: the structured-output planning call
│       ├── agent_result.py        ✅ `AgentResult` (plan, tool trace, cited answer), `ToolCallRecord`
│       └── agent_observer.py      ✅ `AgentObserver`: the plan and each tool call as they happen (CLI trace)
├── prompts/                       ✅ every prompt; code never hard-codes prompt text
│   ├── system_prompt.txt          ✅ executor rules: sources, Item scoping, citations, periods, calculate, gaps
│   ├── planner_prompt.txt         ✅ planning call
│   ├── round_limit.txt            ✅ the "answer with what you have" turn after 8 tool rounds
│   └── tool_descriptions.txt      ✅ one `## <tool>` section per tool
├── tests/
│   ├── conftest.py                ✅ session fixtures (parsed Filing, built index) + the `RUN_LIVE_TESTS` gate
│   ├── live_switch.py             ✅ `RUN_LIVE_TESTS` and API-key checks for `live` tests
│   ├── fakes/                     ✅ in-memory port fakes (index store, embedders, web search client, scripted chat model)
│   ├── offline/                   ✅ offline tier: parser, index, calculate, citations, web_search, agent loop, live switch
│   └── test_queries.py            ✅ live end-to-end tests of the two queries (`@pytest.mark.live`)
├── .github/workflows/
│   ├── ci.yml                     ✅ ruff + offline tests on every PR and push to main (regression gate)
│   ├── live-tests.yml             ✅ live tests: manual dispatch, or main pushes if repo variable `RUN_LIVE_TESTS=true`
│   └── claude-review.yml          ✅ automated Claude PR review (review gate)
├── .claude/                       ✅ agent/skill definitions for Claude Code (`/implement-issue`, `/implement-milestone`)
└── scripts/                       repo-template tooling, not part of the product (excluded from ruff)
```

### Code you can rely on today

- **`ToolRegistry`** (`src/tools/registry.py`). Every tool implements the `Tool` protocol
  (`name`, `description`, `input_schema`, `run(args) -> ToolOutput`). Expected failures come
  back as `ToolOutput(is_error=True)` and are never raised, so the agent loop can pass them to
  the model. The registry builds the Anthropic `tools` definitions and dispatches calls by name.
- **`Settings`** (`src/utils/config.py`). The only place configuration is read. If a required
  key is missing, it fails at startup with a message naming the variable.
- **`load_prompt`** (`src/utils/prompts.py`). Every prompt and tool description lives in
  `prompts/*.txt`.
- **`build_agent(settings)`** (`src/agent_factory.py`). Returns a `ResearchAgent` whose
  `answer(question)` gives an `AgentResult`: the plan, the ordered tool trace (name, args,
  ok/error, citation IDs), the answer with `[1]…` markers and its rendered Sources. Pass an
  `AgentObserver` to see the plan and each tool call live. Model failures raise
  `ChatModelError` with a one-line, key-free message.

---

## 5. Getting a development environment running

```bash
git clone https://github.com/yosefsha/leumi_fin_assist.git && cd leumi_fin_assist
uv venv --python 3.12 .venv            # the machine default may be 3.14; the project targets 3.12
uv pip install -r requirements.txt ruff
cp .env.example .env                   # fill in ANTHROPIC_API_KEY and TAVILY_API_KEY
ruff check .
pytest -m "not live"                   # offline tier, no keys needed (see §6)
RUN_LIVE_TESTS=true pytest -m live -v  # the two required queries, live: needs both keys, costs tokens
```

The live tier runs each required query once through `build_agent` (about a minute, two agent
runs) and checks the tools used, the Items cited and the figures (R&D share, gross margin)
against the parsed income statement. Add `-s` to print each run's plan, trace and answer;
on failure they are in the assertion message anyway.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | — | LLM calls |
| `TAVILY_API_KEY` | yes | — | web search (free tier: 1,000 requests/month) |
| `ANTHROPIC_MODEL` | no | `claude-sonnet-5-5` | model the agent uses |
| `FILING_PATH` | no | `data/apple_10k_2025.htm` | the Filing |
| `FILING_FISCAL_YEAR` | no | `2025` | the Filing's fiscal year, shown in citations as `10-K FY<year>`; change it with `FILING_PATH` |
| `INDEX_DIR` | no | `.index` | local retrieval index (git-ignored) |
| `LOG_LEVEL` | no | `INFO` | standard logging level |
| `RUN_LIVE_TESTS` | no | `false` | `true` runs the live query tests, which call the paid APIs |

Real environment variables override `.env`, except blank ones. On the first run after #4, the
embedding model is downloaded into `INDEX_DIR/models` and the index is built in
`INDEX_DIR/chroma`. Later runs reuse the index unless the Filing changes.

### Running the agent

```bash
python src/main.py                                  # interactive: type a question at "> "; exit/quit/Ctrl-D leaves
python src/main.py --query "What are Apple's top 3 risk factors …?"   # one question, then exit
python src/main.py --query "…" --quiet              # stdout gets only the answer and its Sources
python src/main.py --rebuild-index                  # rebuild the Filing index first
```

Without `--quiet`, each question shows `[Agent processing...]`, the `[Plan]`, and one
`[Tool: …]` line per tool call as it runs, then the answer and Sources. Ctrl-C during a
question cancels it and returns to the prompt. Logs go to stderr; under `--quiet` so do the
prompt and any notes. Exit status: 0 success, 1 model API failure (`--query`) or an index that
cannot be opened, 2 bad usage or configuration (such as a missing key), 130 interrupted. The user-facing guide is #12.

---

## 6. How the team works

- **One issue → one branch → one git worktree → one PR.** Worktrees live in
  `.claude/worktrees/<n>-<slug>`. The primary checkout stays on a clean `main`. Changes that
  touch only docs may go straight to `main` (`git pull --rebase` first). Full rules:
  [`CLAUDE.md`](CLAUDE.md).
- **Dependent issues wait for their prerequisite PR to be merged.** Nobody builds on an
  unmerged branch.
- **Definition of done for a PR:** not a draft, contains `Closes #<n>`, `ruff check .` is clean,
  acceptance criteria are verified locally with the evidence in the PR body, **and** the
  `Claude review` workflow has run on the latest push with every top-level and inline comment
  fixed or answered. Repeat until a review raises nothing new. A failing review check is a
  blocker, not a pass. The workflow needs the `CLAUDE_CODE_OAUTH_TOKEN` repo secret.
- **PRs are merged by a human only.** AI agents open PRs and handle review comments; they never
  merge.
- **Two test tiers** ([ADR-0004](docs/adr/0004-hybrid-test-tiers-and-ci.md)). The offline
  tier (`tests/offline/`, no keys) asserts each merged issue's acceptance criteria and each
  tool's boundary failure paths. `ci.yml` runs it with `ruff check .` on every PR, and it must
  pass before merge. Run it locally with `pytest -m "not live"` (under a minute once the
  ~130 MB embedding model is in `.index/models`; the first run downloads it). The live tier
  (`tests/test_queries.py`, #11) calls Anthropic and Tavily and runs only with
  `RUN_LIVE_TESTS=true`; plain `pytest` skips it. Tests target acceptance criteria and tool
  boundaries, not every public function.
- **Code rules** (enforced in review): every external source (HTTP API, index store, LLM)
  sits behind a `typing.Protocol` named in domain terms, injected where the app is wired
  together. Frozen dataclasses for value objects, Pydantic at boundaries, one concern per file,
  fully typed signatures, fail loudly at the boundary.
- **AI-assisted workflow:** `/implement-issue <n>` runs one issue end to end in a worktree;
  `/implement-milestone <n>` runs every independent issue of a milestone in parallel.

---

## 7. Open items for the incoming lead

These are undecided and recorded in issue #15:

1. The env-var "Configuration" guidance was removed from `docs/backend-python-instructions.md`
   in #13. Decide whether to restore it.
2. `scripts/copy_repo.py` and `scripts/create_remote_project.py` (template tooling) still
   describe the template's NestJS `ci.yml`, not this repo's.

Known risks to watch:

- **Numeric accuracy depends on table rendering** (ADR-0003). A wrong figure most likely means
  column or period confusion in a table Passage (#3).
- **Retrieval recall.** If the right Item isn't found, the documented upgrade is
  `bge-base-en-v1.5` (ADR-0002). Changing the model only requires a re-index.
- **Live-API tests cost money and can be flaky.** They assert on structure and figures with
  tolerances, not on wording (#11).

---

## 8. Where to start reading

1. [`docs/TASKS.md`](docs/TASKS.md): what's being built and how it's judged.
2. Issue **#15**: where things stand right now.
3. [`CONTEXT.md`](CONTEXT.md) and [`docs/adr/`](docs/adr/): the vocabulary and the decisions
   that are already made.
4. `src/tools/registry.py`: the contract every tool implements.
5. Open issues #3–#12: each one is a spec with acceptance criteria.
6. PR **#14** body: findings on the Filing's HTML structure (ToC anchors, heading styles, page
   footers, inline-XBRL tags, table quirks) that the parser relies on.
