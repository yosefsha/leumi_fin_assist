# Python

Python standards for this project. The repository layout is the one `docs/TASKS.md`
prescribes — see `docs/adr/0001-cli-agent-assignment-layout-no-ci.md`.

## Code Style
- Type-annotate all function signatures including return types.
- Use `dataclass(frozen=True)` for internal value objects that don't need Pydantic validation.
- Use Pydantic `BaseModel` for data validated at a boundary (tool arguments, external API payloads).
- Entry points (the CLI, tool adapters) must be thin — delegate to business logic classes.
- Use `snake_case` for functions and variables, `PascalCase` for classes.
- One class/concern per file.

## Data sources go behind a Protocol
Anything fetched from outside the process — an HTTP API, a database, a cache, a
queue — is reached through a `typing.Protocol` named in domain terms, with
domain return types and its own exception types. One implementation per source,
injected where the application is wired together, plus an in-memory fake for
tests. The full rule set lives in `.claude/agents/backend-engineer.md`.

## Testing
Two tiers (`docs/adr/0004-hybrid-test-tiers-and-ci.md`):
- **Offline**: `tests/offline/`, one file per area. No API keys and no network beyond the
  cached embedding-model download. Each test turns an acceptance criterion or a tool-boundary
  failure path into an assertion. Shared fixtures (the parsed Filing, the built index) are
  session-scoped in `tests/conftest.py`; ports are replaced by the in-memory fakes in
  `tests/fakes/`, never by patching business logic. CI runs `pytest -m "not live"` on every PR.
- **Live**: `tests/test_queries.py` (#11), marked `@pytest.mark.live`. Skipped unless
  `RUN_LIVE_TESTS=true` (environment or `.env`); when it is on, a missing API key fails the
  test. On GitHub, `live-tests.yml` runs them on manual dispatch, and on pushes to `main` only
  when the `RUN_LIVE_TESTS` repository variable is `true`.

## Dependencies
- Pin minimum versions in `requirements.txt` (e.g., `anthropic>=0.40.0`).
- For production, generate a locked `requirements.lock` with exact versions.
