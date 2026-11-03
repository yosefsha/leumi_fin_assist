"""The `FilingSearch` port: what `search_filing` needs from the Filing index."""

from typing import Protocol

from utils.passage_hit import PassageHit


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
