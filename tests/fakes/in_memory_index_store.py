"""In-memory `IndexStore` fake: exact cosine search over a list, no persistence."""

import math
from collections.abc import Sequence

from utils.embedder import Vector
from utils.index_entry import IndexEntry


class InMemoryIndexStore:
    """Holds Index Entries and vectors in memory; behaves like `ChromaIndexStore`."""

    def __init__(self) -> None:
        self._entries: tuple[IndexEntry, ...] = ()
        self._vectors: tuple[Vector, ...] = ()
        self._fingerprint: str | None = None

    def fingerprint(self) -> str | None:
        return self._fingerprint

    def replace(
        self, entries: Sequence[IndexEntry], vectors: Sequence[Vector], fingerprint: str
    ) -> None:
        if len(entries) != len(vectors):
            raise ValueError(f"{len(entries)} entries but {len(vectors)} vectors.")
        self._entries = tuple(entries)
        self._vectors = tuple(vectors)
        self._fingerprint = fingerprint

    def entries(self) -> tuple[IndexEntry, ...]:
        return tuple(sorted(self._entries, key=lambda entry: entry.entry_id))

    def nearest(self, vector: Vector, limit: int, item: str | None = None) -> tuple[str, ...]:
        if limit < 1:
            return ()
        scored = sorted(
            (
                (-_cosine(vector, stored), entry.entry_id)
                for entry, stored in zip(self._entries, self._vectors, strict=True)
                if item is None or entry.item == item
            )
        )
        return tuple(entry_id for _, entry_id in scored[:limit])


def _cosine(left: Vector, right: Vector) -> float:
    norms = math.hypot(*left) * math.hypot(*right)
    return sum(a * b for a, b in zip(left, right, strict=True)) / norms if norms else 0.0
