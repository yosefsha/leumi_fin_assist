"""Build the Filing's hybrid index, or reuse the stored one when the Filing is unchanged."""

import hashlib
import logging
from collections.abc import Iterable, Mapping
from pathlib import Path

from utils.chunker import Chunker
from utils.embedder import Embedder
from utils.filing_index import FilingIndex
from utils.filing_parser import FilingParseError, FilingParser
from utils.index_entry import IndexEntry
from utils.index_store import IndexStore
from utils.passage import Passage
from utils.token_counter import TokenCounter

logger = logging.getLogger(__name__)

INDEX_FORMAT_VERSION = "1"
"""Bump when chunking or entry layout changes, so stored indexes built the old way rebuild."""


class IndexEntryTooLongError(Exception):
    """An Index Entry exceeds the embedding model's input limit and would be truncated."""

    def __init__(self, entry: IndexEntry, tokens: int, limit: int) -> None:
        super().__init__(
            f"Index Entry {entry.entry_id} is {tokens} tokens, over the embedding model's "
            f"{limit}-token input limit; it would be silently truncated."
        )
        self.entry = entry
        self.tokens = tokens
        self.limit = limit


class FilingIndexLoader:
    """Parses the Filing, then reuses the stored index or rebuilds it.

    The stored index is reused when its fingerprint (Filing content hash,
    embedding model, index format version) matches and every stored entry still
    points to a Passage; otherwise, or when `force_rebuild` is set, the Filing is
    re-chunked, length-checked, embedded and stored.
    """

    def __init__(
        self,
        parser: FilingParser,
        chunker: Chunker,
        embedder: Embedder,
        token_counter: TokenCounter,
        store: IndexStore,
    ) -> None:
        self._parser = parser
        self._chunker = chunker
        self._embedder = embedder
        self._token_counter = token_counter
        self._store = store

    def load(self, filing_path: Path, force_rebuild: bool = False) -> FilingIndex:
        """Return a searchable index of the Filing at `filing_path`.

        Raises `FilingParseError`, `IndexEntryTooLongError`, `EmbedderError` or
        `IndexStoreError`.
        """
        passages = {passage.passage_id: passage for passage in self._parser.parse_file(filing_path)}
        fingerprint = self._fingerprint(filing_path)
        entries = None if force_rebuild else self._reusable_entries(fingerprint, passages)
        if entries is None:
            entries = self._build(passages.values(), fingerprint)
        return FilingIndex(passages, entries, self._store, self._embedder)

    def _fingerprint(self, filing_path: Path) -> str:
        try:
            content = filing_path.read_bytes()
        except OSError as error:
            raise FilingParseError(f"Cannot read the Filing at {filing_path}: {error}") from error
        digest = hashlib.sha256(content).hexdigest()
        return f"sha256={digest};model={self._embedder.model_name};format={INDEX_FORMAT_VERSION}"

    def _reusable_entries(
        self, fingerprint: str, passages: Mapping[str, Passage]
    ) -> tuple[IndexEntry, ...] | None:
        if self._store.fingerprint() != fingerprint:
            logger.info("No current index for this Filing; building one.")
            return None
        entries = self._store.entries()
        if not entries or any(entry.passage_id not in passages for entry in entries):
            logger.warning("Stored index does not match the parsed Passages; rebuilding it.")
            return None
        logger.info("Reusing the stored index: %d Index Entries.", len(entries))
        return entries

    def _build(self, passages: Iterable[Passage], fingerprint: str) -> tuple[IndexEntry, ...]:
        entries = self._chunker.chunk(passages)
        self._check_lengths(entries)
        vectors = self._embedder.embed_documents([entry.text for entry in entries])
        self._store.replace(entries, vectors, fingerprint)
        logger.info("Built the index: %d Index Entries.", len(entries))
        return entries

    def _check_lengths(self, entries: tuple[IndexEntry, ...]) -> None:
        limit = self._embedder.max_input_tokens
        for entry in entries:
            tokens = self._token_counter.count_tokens(entry.text)
            if tokens > limit:
                raise IndexEntryTooLongError(entry, tokens, limit)
