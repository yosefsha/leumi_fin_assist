# CLI agent in the assignment layout, no CI workflow

> **Superseded in part by [ADR-0004](0004-hybrid-test-tiers-and-ci.md):** the "no CI workflow" and testing-scope decisions below are replaced by two test tiers: offline tests in CI on every PR, and live query tests behind `RUN_LIVE_TESTS` (default off). The repository-layout decision still stands.

The repository was generated from a FastAPI + React service template (`backend/`, `frontend/`, Postgres, Alembic, Docker, a `ci.yml` gate). The project is instead a Python command-line agent, so we follow the tree `docs/TASKS.md` prescribes — `src/` (with `src/tools/` and `src/utils/`), `prompts/`, `data/`, `tests/`, plus `requirements.txt` and `.env.example` at the root — and drop the template's service layout. A reviewer expects the assignment's shape, and nothing in the project needs a server, a database or a container.

`.github/workflows/ci.yml` is removed. The tests exercise the two required queries end to end against live APIs (an LLM provider and Tavily), which need paid keys and network access; a CI gate would either hold those secrets and spend money on every push, or mock the APIs and test nothing the assignment asks for. Tests are run locally before a PR is opened. The Claude PR review workflow (`.github/workflows/claude-review.yml`) is kept as the review gate on every pull request.

## Consequences

- Nothing automated stops a red test or a lint error from merging; running `pytest` and `ruff check .` locally is part of each issue's definition of done.
- The template's backend/frontend instruction docs are trimmed to the parts that still apply (coding principles, Python code style, the Protocol rule, dependencies).
