# Coding Instructions

## General

- All configuration must be production-ready standard — no placeholder values, TODO stubs, or "good enough for now" defaults. Every config entry should be deployable to production as-is.
- Write to the industry standard of the language and framework in front of you, not to a personal style. The stack's own idioms and its community conventions win over a clever alternative; a reviewer who knows idiomatic Python should recognise the shape of the code without being told how this repo does things.

## Design Principles

Follow SOLID, and treat it as a set of concrete obligations rather than a slogan
to cite in review. What each one demands here:

- **Single responsibility** — one class, one reason to change. A route handler that also parses a payload, applies a business rule and writes to a database has three. Split it, and put the pieces where the structure section says they go.
- **Open/closed** — adding a case should mean adding a file, not editing a growing `if`/`switch`. When a second variant of something arrives, that is the signal to extract the abstraction the first one implied — not a signal to add another branch.
- **Liskov substitution** — every implementation of an interface must be usable through it without the caller knowing which one it got. An implementation that only works when the caller special-cases it, or that raises where its siblings return, has broken the contract, not extended it.
- **Interface segregation** — small, purpose-named interfaces. A caller that needs one method must not be made to depend on nine. Prefer several narrow ports over one service-shaped interface that everything ends up importing.
- **Dependency inversion** — business logic depends on abstractions it owns and names; concrete clients (HTTP, database, cache, queue) depend on those abstractions and are wired in at the edge. This is the rule the Python "Data sources go behind a Protocol" section exists to enforce, and it is the one that carries the most weight in this codebase.

Extensibility is judged by the same standard the Protocol/port rule applies:
**adding the second source, provider or variant must not require editing the
code that consumes the first.** If it does, the seam is in the wrong place.

Two limits, so the above doesn't become its own kind of damage:

- **Extensibility is the seam, not extra code.** Build the abstraction and one real implementation (plus the in-memory fake tests use). Do not write a second implementation, a plugin registry or a configuration switch for a case nobody has asked for — YAGNI outranks a speculative interface.
- **Do not abstract on first use.** A single implementation behind a hand-rolled framework is harder to change than the concrete code it replaced. The exception is anything crossing a process boundary, which goes behind a port immediately — that boundary is known to move.

Also standard, and not negotiable per-feature:

- **DRY within a bounded context, not across the repo.** Two things that merely look alike are not duplication; coupling them because of the resemblance is worse than repeating them.
- **Fail loudly at the boundary.** Validate input where it enters the process and reject it there. Never swallow an exception to keep a request alive, and never let a transport-level error (an HTTP client error, a driver error) reach a caller that has no way to interpret it.
- **Make illegal states unrepresentable.** Immutable value objects, exhaustive types, no optional field that is really required — lean on the type system rather than on a runtime check a later caller can skip.
- **Every public function is typed and named for what it does in domain terms.** Tests cover each issue's acceptance criteria and the failure paths at each tool's boundary (invalid arguments, an unavailable source, nothing found), not every public function (`docs/adr/0004-hybrid-test-tiers-and-ci.md`).
