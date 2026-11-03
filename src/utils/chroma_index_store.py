"""`IndexStore` backed by a persistent local Chroma collection."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import ChromaError, NotFoundError

from utils.embedder import Vector
from utils.index_entry import IndexEntry
from utils.index_store import IndexStoreError
from utils.passage import PassageKind

COLLECTION_NAME = "filing_index_entries"
_FINGERPRINT_KEY = "fingerprint"


@contextmanager
def _store_errors(action: str) -> Iterator[None]:
    """Re-raise Chroma, SQLite and filesystem failures as `IndexStoreError`."""
    try:
        yield
    except (ChromaError, ValueError, OSError, RuntimeError) as error:
        raise IndexStoreError(f"Index store failed to {action}: {error}") from error


class ChromaIndexStore:
    """Stores Index Entries in one cosine-distance Chroma collection under `path`.

    Vectors are supplied by the caller (Chroma's own embedding function is never
    used). Entry metadata carries `passage_id`, `item`, `kind` and, when known, `page`.
    """

    def __init__(self, path: Path) -> None:
        with _store_errors(f"open {path}"):
            self._client: ClientAPI = chromadb.PersistentClient(
                path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
            )

    def fingerprint(self) -> str | None:
        collection = self._collection()
        if collection is None:
            return None
        value = (collection.metadata or {}).get(_FINGERPRINT_KEY)
        return value if isinstance(value, str) else None

    def replace(
        self, entries: Sequence[IndexEntry], vectors: Sequence[Vector], fingerprint: str
    ) -> None:
        if len(entries) != len(vectors):
            raise ValueError(f"{len(entries)} entries but {len(vectors)} vectors.")
        with _store_errors("replace the index"):
            if self._collection() is not None:
                self._client.delete_collection(COLLECTION_NAME)
            collection = self._client.create_collection(
                COLLECTION_NAME,
                configuration={"hnsw": {"space": "cosine"}},
                embedding_function=None,
            )
            batch_size = self._client.get_max_batch_size()
            for start in range(0, len(entries), batch_size):
                batch = entries[start : start + batch_size]
                collection.add(
                    ids=[entry.entry_id for entry in batch],
                    embeddings=[list(vector) for vector in vectors[start : start + batch_size]],
                    documents=[entry.text for entry in batch],
                    metadatas=[_metadata(entry) for entry in batch],
                )
            collection.modify(metadata={_FINGERPRINT_KEY: fingerprint})

    def entries(self) -> tuple[IndexEntry, ...]:
        collection = self._collection()
        if collection is None:
            return ()
        with _store_errors("read the index"):
            stored = collection.get(include=["documents", "metadatas"])
        documents = stored["documents"] or []
        metadatas = stored["metadatas"] or []
        entries = [
            _entry(entry_id, document, metadata)
            for entry_id, document, metadata in zip(
                stored["ids"], documents, metadatas, strict=True
            )
        ]
        return tuple(sorted(entries, key=lambda entry: entry.entry_id))

    def nearest(self, vector: Vector, limit: int, item: str | None = None) -> tuple[str, ...]:
        collection = self._collection()
        if collection is None or limit < 1:
            return ()
        with _store_errors("query the index"):
            result = collection.query(
                query_embeddings=[list(vector)],
                n_results=limit,
                where={"item": item} if item is not None else None,
                include=["distances"],
            )
        return tuple(result["ids"][0]) if result["ids"] else ()

    def _collection(self) -> Collection | None:
        with _store_errors("open the collection"):
            try:
                return self._client.get_collection(COLLECTION_NAME, embedding_function=None)
            except NotFoundError:
                return None


def _metadata(entry: IndexEntry) -> dict[str, str | int]:
    metadata: dict[str, str | int] = {
        "passage_id": entry.passage_id,
        "item": entry.item,
        "kind": entry.kind.value,
    }
    if entry.page is not None:
        metadata["page"] = entry.page
    return metadata


def _entry(
    entry_id: str, document: str | None, metadata: Mapping[str, object] | None
) -> IndexEntry:
    if document is None or metadata is None:
        raise IndexStoreError(
            f"Stored entry {entry_id} has no text or metadata; rebuild the index."
        )
    page = metadata.get("page")
    try:
        return IndexEntry(
            entry_id=entry_id,
            passage_id=str(metadata["passage_id"]),
            item=str(metadata["item"]),
            kind=PassageKind(metadata["kind"]),
            page=page if isinstance(page, int) else None,
            text=document,
        )
    except (KeyError, ValueError) as error:
        raise IndexStoreError(
            f"Stored entry {entry_id} has invalid metadata ({error}); rebuild the index."
        ) from error
