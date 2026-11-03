"""The Index Entry: an embedded excerpt that points to its Passage (see CONTEXT.md)."""

from dataclasses import dataclass

from utils.passage import PassageKind


@dataclass(frozen=True)
class IndexEntry:
    """One searchable excerpt of a Passage, or a Table Card for a table Passage.

    `text` is what is embedded and BM25-indexed: the Section Path prefix, a blank
    line, then the excerpt. `item`, `kind` and `page` are copied from the Passage
    so the index can filter and cite without loading it.
    """

    entry_id: str
    passage_id: str
    item: str
    kind: PassageKind
    page: int | None
    text: str
