"""Keyword retrieval over Index Entries with BM25 (Okapi), to recover exact-term matches."""

import re
from collections.abc import Sequence

from rank_bm25 import BM25Okapi

from utils.index_entry import IndexEntry

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does", "for", "from",
        "had", "has", "have", "how", "in", "is", "it", "its", "of", "on", "or", "s", "that",
        "the", "their", "them", "they", "this", "to", "was", "were", "what", "when", "where",
        "which", "who", "why", "will", "with",
    }
)  # fmt: skip


def bm25_tokens(text: str) -> list[str]:
    """Lower-cased alphanumeric terms of `text`, without common English stopwords."""
    return [token for token in _TOKEN.findall(text.lower()) if token not in _STOPWORDS]


class Bm25Retriever:
    """Ranks Index Entries by BM25 score against a query, optionally within one Item."""

    def __init__(self, entries: Sequence[IndexEntry]) -> None:
        if not entries:
            raise ValueError("BM25 needs at least one Index Entry.")
        self._entries = tuple(entries)
        self._bm25 = BM25Okapi([bm25_tokens(entry.text) for entry in self._entries])

    def rank(self, query: str, limit: int, item: str | None = None) -> tuple[str, ...]:
        """IDs of the up to `limit` best-scoring entries that share a term with `query`."""
        terms = bm25_tokens(query)
        if not terms or limit < 1:
            return ()
        scores = self._bm25.get_scores(terms)
        ranked = sorted(
            (
                (float(score), index)
                for index, score in enumerate(scores)
                if score > 0 and (item is None or self._entries[index].item == item)
            ),
            key=lambda pair: (-pair[0], pair[1]),
        )
        return tuple(self._entries[index].entry_id for _, index in ranked[:limit])
