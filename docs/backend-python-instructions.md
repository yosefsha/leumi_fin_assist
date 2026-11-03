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
Testing scope is defined by docs/TASKS.md.

## Dependencies
- Pin minimum versions in `requirements.txt` (e.g., `anthropic>=0.40.0`).
- For production, generate a locked `requirements.lock` with exact versions.
