---
status: accepted
supersedes: the "no CI workflow" and testing-scope parts of ADR-0001
---

# Two test tiers: offline tests in CI on every PR, live query tests on demand

ADR-0001 dropped CI because the only planned tests were the two required queries run against live, paid APIs. CI would therefore have had to spend money and Tavily quota on every push, or mock the APIs and test nothing the assignment asks about. Since then, every merged issue (#3, #7, #8, and #4, #6 in review) was accepted on evidence from one-off scripts run by hand: parser counts, calculator attack cases, citation renumbering, the index's 512-token guard. That evidence lives only in PR descriptions. A later change that breaks the parser or the calculator's allow-list would go unnoticed until someone re-ran a script they don't have.

We split testing into two tiers:

- **Offline tier**: deterministic pytest tests, no API keys and no network beyond a cached model download. They run in a new `.github/workflows/ci.yml` on every pull request, together with `ruff check .`. They turn the acceptance criteria already verified by hand into assertions, and they cover the failure paths at each tool's boundary.
- **Live tier**: `tests/test_queries.py` (#11), the two required queries end to end against Anthropic and Tavily, marked `@pytest.mark.live`. **Nothing calls a paid API unless `RUN_LIVE_TESTS=true`, and the default is `false`.**
  - Locally, `RUN_LIVE_TESTS` is read from the environment or `.env`. When it isn't `true`, live tests are skipped with the reason "set RUN_LIVE_TESTS=true to run".
  - In GitHub, a separate `live-tests.yml` workflow runs on pushes to `main` that touch `src/` or `prompts/`, but its job runs only when the repository variable `RUN_LIVE_TESTS` is `true`; the variable is left unset or `false`. A manual `workflow_dispatch` always runs it, because a person asked. It uses `ANTHROPIC_API_KEY` and `TAVILY_API_KEY` repository secrets, kept separate from developers' own keys.

`docs/TASKS.md` requires `tests/test_queries.py`; it does not forbid other tests. The earlier "live tests only" scope was our interpretation, not the assignment's.

## Considered Options

- **Live tests only, no CI (ADR-0001)**: rejected. Regressions in deterministic code are caught only by hand, and the evidence for each merged issue cannot be re-run.
- **Live tests on every PR**: rejected. Each push spends LLM tokens and Tavily quota (free tier: 1,000 searches a month), and nondeterministic LLM output would make a required check flaky.
- **Live tests on every merge to `main`, always on**: rejected. Paid API calls must be an explicit choice, so automatic runs sit behind `RUN_LIVE_TESTS`, which defaults to off.
- **Full unit-test coverage of every public function**: rejected as out of proportion for a 3–4 hour assignment. The offline tier targets acceptance criteria and boundary failure paths, not every function.
- **Mocked end-to-end agent tests**: rejected. A scripted LLM response tests the mock, not the agent's tool choice.

## Consequences

- `ci.yml` returns. The `Claude review` workflow stays as the review gate; CI becomes the regression gate. Both must pass before merge.
- This changes #11's "plain `pytest` runs the live tests" decision. Plain `pytest` now runs the offline tier and skips the live tier unless `RUN_LIVE_TESTS=true`. When the switch is on, missing keys still fail loudly rather than skip. CI runs `pytest -m "not live"`.
- Offline index tests need the ~130 MB embedding model. CI caches the model directory, keyed on the model name.
- Secrets are not passed to workflows triggered from forks, so a fork PR runs only the offline tier.
- `docs/coding-instructions.md`'s rule "covered by a test for its failure path as well as its success path" is narrowed to tool boundaries and acceptance criteria. That resolves the open item in the status tracker (#15).
- `CLAUDE.md`, `README.md`, `docs/backend-python-instructions.md` and ADR-0001 are updated to point here.
