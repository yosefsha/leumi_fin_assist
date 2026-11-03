"""The `IndexStore` port: where Index Entries and their vectors persist between runs."""

from collections.abc import Sequence
from typing import Protocol

from utils.embedder import Vector
from utils.index_entry import IndexEntry


class IndexStoreError(Exception):
    """The index store could not be opened, read or written."""


class IndexStore(Protocol):
    """Persists the Filing's Index Entries with their vectors and answers nearest-vector queries.

    The stored index is tagged with the fingerprint of what it was built from, so a
    caller can tell whether it is still current. Every method raises
    `IndexStoreError` on failure.
    """

    def fingerprint(self) -> str | None:
        """The fingerprint of the completed stored index, or `None` if there is none."""
        ...

    def replace(
        self, entries: Sequence[IndexEntry], vectors: Sequence[Vector], fingerprint: str
    ) -> None:
        """Replace everything stored with `entries` (paired with `vectors` by position).

        The fingerprint is recorded last, so an interrupted build reads back as no index.
        """
        ...

    def entries(self) -> tuple[IndexEntry, ...]:
        """All stored Index Entries."""
        ...

    def nearest(self, vector: Vector, limit: int, item: str | None = None) -> tuple[str, ...]:
        """IDs of up to `limit` entries nearest `vector`, nearest first, within `item` if set."""
        ...
