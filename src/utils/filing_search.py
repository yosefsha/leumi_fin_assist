"""The `FilingSearch` port: what `search_filing` needs from the Filing index."""

from typing import Protocol

from utils.passage_hit import PassageHit


class UnknownItemError(ValueError):
    """A search was filtered to an Item the Filing does not have."""

    def __init__(self, item: str, known: frozenset[str]) -> None:
        super().__init__(f"Unknown Item {item!r}; the Filing has: {', '.join(sorted(known))}.")
        self.item = item


class FilingSearch(Protocol):
    """Searches the Filing for the Passages relevant to a query.

    `FilingIndex` implements it; the tools depend on this Protocol only, so they
    never touch the embedding model or the vector store directly.
    """

    @property
    def items(self) -> frozenset[str]:
        """The Items a search can be filtered to, e.g. `Item 1A`."""
        ...

    def search(self, query: str, limit: int = 5, item: str | None = None) -> tuple[PassageHit, ...]:
        """Return up to `limit` Passages most relevant to `query`, best first.

        Raises `ValueError` for a blank query or a non-positive limit,
        `UnknownItemError` for an `item` not in `items`, and `EmbedderError` /
        `IndexStoreError` when retrieval fails.
        """
        ...
