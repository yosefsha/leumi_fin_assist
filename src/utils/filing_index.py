"""Hybrid search over the Filing: dense + BM25, fused with RRF, returned as Passages."""

from collections.abc import Mapping

from utils.bm25_retriever import Bm25Retriever
from utils.embedder import Embedder
from utils.index_entry import IndexEntry
from utils.index_store import IndexStore
from utils.passage import Passage
from utils.passage_hit import PassageHit
from utils.rank_fusion import reciprocal_rank_fusion

CANDIDATES_PER_RETRIEVER = 50
"""How many Index Entries each retriever contributes to fusion."""


class UnknownItemError(ValueError):
    """A search was filtered to an Item the Filing does not have."""

    def __init__(self, item: str, known: frozenset[str]) -> None:
        super().__init__(f"Unknown Item {item!r}; the Filing has: {', '.join(sorted(known))}.")
        self.item = item


class FilingIndex:
    """Searches the Filing's Index Entries and returns whole Passages.

    The query runs through the dense store and BM25 (both filtered to `item` when
    given); the two entry rankings are fused with Reciprocal Rank Fusion, and
    entries are collapsed to their Passages, keeping each Passage's best rank.
    """

    def __init__(
        self,
        passages: Mapping[str, Passage],
        entries: tuple[IndexEntry, ...],
        store: IndexStore,
        embedder: Embedder,
    ) -> None:
        self._passages = dict(passages)
        self._entries = {entry.entry_id: entry for entry in entries}
        self._store = store
        self._embedder = embedder
        self._bm25 = Bm25Retriever(entries)
        self._items = frozenset(passage.item for passage in self._passages.values())

    @property
    def entry_count(self) -> int:
        """Number of Index Entries searched."""
        return len(self._entries)

    @property
    def passages(self) -> tuple[Passage, ...]:
        """Every Passage of the Filing, in Filing order."""
        return tuple(self._passages.values())

    @property
    def items(self) -> frozenset[str]:
        """The Items a search can be filtered to, e.g. `Item 1A`."""
        return self._items

    def search(self, query: str, limit: int = 5, item: str | None = None) -> tuple[PassageHit, ...]:
        """Return up to `limit` Passages most relevant to `query`, best first.

        Raises `ValueError` for a blank query or a non-positive limit,
        `UnknownItemError` for an `item` the Filing lacks, and `EmbedderError` /
        `IndexStoreError` when a retriever fails.
        """
        if not query.strip():
            raise ValueError("The search query is empty.")
        if limit < 1:
            raise ValueError(f"The result limit must be positive; got {limit}.")
        if item is not None and item not in self._items:
            raise UnknownItemError(item, self._items)
        dense = self._store.nearest(
            self._embedder.embed_query(query), CANDIDATES_PER_RETRIEVER, item
        )
        keyword = self._bm25.rank(query, CANDIDATES_PER_RETRIEVER, item)
        hits: dict[str, PassageHit] = {}
        for entry_id, score in reciprocal_rank_fusion([dense, keyword]):
            passage_id = self._entries[entry_id].passage_id
            if passage_id not in hits:
                hits[passage_id] = PassageHit(self._passages[passage_id], score)
                if len(hits) == limit:
                    break
        return tuple(hits.values())
