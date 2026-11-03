# Handover notes

This page is for whoever takes over the project: where it stands, how the team works, and what
is still open. The user-facing guide (setup, running, architecture, technical spec) is the
[README](../README.md).

## Status

The live progress tracker is pinned **issue #15** ("Project status & resume guide"). Read it
first, and update it after each merge. Snapshot as of 2026-11-03:

| Milestone | Issues | State |
|---|---|---|
| M1 — Foundation | #1 docs/ADRs, #2 scaffold + config + tool registry + Filing | merged |
| M2 — Document QA | #3 filing parser → #4 chunker + hybrid index → #5 `search_filing` / `get_passage` | merged |
| M3 — Web search & calc | #6 Tavily `web_search`, #7 `calculate` | merged |
| M4 — Agent & CLI | #8 citation registry, #9 planner + executor, #10 CLI | merged |
| M5 — Delivery | #21 offline test tier + CI, #11 live test queries, #12 user README | #21 and #11 merged; #12 is the last required deliverable |
| Backlog | #26 evaluation suite with token accounting | deferred until the required deliverables ship |

The critical path was **#3 → #4 → #5 → #9 → #10 → #11 → #12**; #6, #7 and #8 ran in parallel
with M2.

Each issue body holds the agreed design decisions and acceptance criteria. Treat them as the
spec. Changing a decision means updating the issue (and an ADR, if it's architectural).

## How the team works

- **One issue → one branch → one git worktree → one PR.** Worktrees live in
  `.claude/worktrees/<n>-<slug>`. The primary checkout stays on a clean `main`. Changes that
  touch only docs may go straight to `main` (`git pull --rebase` first). Full rules:
  [`CLAUDE.md`](../CLAUDE.md).
- **Dependent issues wait for their prerequisite PR to be merged.** Nobody builds on an
  unmerged branch.
- **Definition of done for a PR:** not a draft, contains `Closes #<n>`, `ruff check .` is clean,
  acceptance criteria are verified locally with the evidence in the PR body, **and** the
  `Claude review` workflow has run on the latest push with every top-level and inline comment
  fixed or answered. Repeat until a review raises nothing new. A failing review check is a
  blocker, not a pass. The workflow needs the `CLAUDE_CODE_OAUTH_TOKEN` repo secret.
- **PRs are merged by a human only.** AI agents open PRs and handle review comments; they never
  merge.
- **Two test tiers** ([ADR-0004](adr/0004-hybrid-test-tiers-and-ci.md)). The offline tier
  (`tests/offline/`, no keys) asserts each merged issue's acceptance criteria and each tool's
  boundary failure paths; `ci.yml` runs it with `ruff check .` on every PR, and it must pass
  before merge. The live tier (`tests/test_queries.py`) calls Anthropic and Tavily and runs only
  with `RUN_LIVE_TESTS=true`. Tests target acceptance criteria and tool boundaries, not every
  public function.
- **Code rules** (enforced in review, see [`coding-instructions.md`](coding-instructions.md) and
  [`backend-python-instructions.md`](backend-python-instructions.md)): every external source
  (HTTP API, index store, LLM) sits behind a `typing.Protocol` named in domain terms, injected
  at the composition root. Frozen dataclasses for value objects, Pydantic at boundaries, one
  concern per file, fully typed signatures, fail loudly at the boundary.
- **Prompt changes are behaviour changes.** After editing `prompts/*.txt` or changing
  `ANTHROPIC_MODEL`, re-run the live tier and add a dated section to
  [`query-run-results.md`](query-run-results.md) rather than overwriting the old one.
- **AI-assisted workflow:** `/implement-issue <n>` runs one issue end to end in a worktree;
  `/implement-milestone <n>` runs every independent issue of a milestone in parallel. Both live
  in `.claude/skills/`.

## Open items

Undecided, and recorded in issue #15:

1. The env-var "Configuration" guidance was removed from `docs/backend-python-instructions.md`
   in #13. Decide whether to restore it.
2. `scripts/copy_repo.py` and `scripts/create_remote_project.py` (repo-template tooling, excluded
   from ruff) still describe the template's NestJS `ci.yml`, not this repo's.
3. **Competitor figures from the web** (README → Known limitations): Microsoft's company-wide
   gross margin is not reliably found through Tavily. No fix has been chosen yet; the candidate
   is a primary-sources search (Tavily `include_domains` such as `microsoft.com` / `sec.gov`).

## Risks to watch

- **Numeric accuracy depends on table rendering** ([ADR-0003](adr/0003-no-xbrl-fact-tool.md)). A
  wrong figure most likely means column or period confusion in a table Passage (#3).
- **Retrieval recall.** If the right Item isn't found, the documented upgrade is
  `bge-base-en-v1.5` ([ADR-0002](adr/0002-local-embeddings-and-passage-retrieval.md)). Changing
  the model only requires a re-index (the model name is part of the index fingerprint).
- **Live-API tests cost money and can be flaky.** They assert on structure and figures with
  tolerances, not on wording (#11).
- **Prompt regressions are caught only by re-running.** The Microsoft Cloud segment-margin trap
  (fixed in commit `51dc883`) has no automated guard until the evaluation suite (#26) lands.

## Where to start reading

1. [`docs/TASKS.md`](TASKS.md): what's being built and how it's judged.
2. Issue **#15**: where things stand right now.
3. [`CONTEXT.md`](../CONTEXT.md) and [`docs/adr/`](adr/): the vocabulary and the decisions that
   are already made.
4. `src/tools/registry.py`: the contract every tool implements; `src/agent_factory.py`: how
   everything is wired.
5. Issues #3–#12: each one is a spec with acceptance criteria.
6. PR **#14** body: findings on the Filing's HTML structure (ToC anchors, heading styles, page
   footers, inline-XBRL tags, table quirks) that the parser relies on.
