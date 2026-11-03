"""Turn Passages into Index Entries: packed text excerpts and Table Cards (ADR-0002)."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from utils.index_entry import IndexEntry
from utils.passage import Passage, PassageKind
from utils.table_card_builder import TableCardBuilder
from utils.text_packer import TextPacker

ENTRY_TOKEN_BUDGET = 350
"""Maximum model tokens of an Index Entry's excerpt, leaving headroom for its prefix."""

_PATH_SEPARATOR = " > "


@dataclass
class _Group:
    """Paragraphs under one heading of a Passage; Index Entries never span two groups."""

    headings: list[str]
    paragraphs: list[str]


class Chunker:
    """Splits each Passage into Index Entries that point back to it.

    Every entry's text starts with its Section Path (plus any sub-heading of the
    Passage it falls under), then a blank line, then the excerpt. Text Passages
    are packed from whole paragraphs up to `ENTRY_TOKEN_BUDGET` tokens and never
    across a heading; table Passages become Table Cards.
    """

    def __init__(self, packer: TextPacker, table_cards: TableCardBuilder) -> None:
        self._packer = packer
        self._table_cards = table_cards

    def chunk(self, passages: Iterable[Passage]) -> tuple[IndexEntry, ...]:
        """Return the Index Entries for `passages`, in Passage order."""
        return tuple(entry for passage in passages for entry in self._entries(passage))

    def _entries(self, passage: Passage) -> list[IndexEntry]:
        texts = (
            self._table_texts(passage)
            if passage.kind is PassageKind.TABLE
            else self._text_texts(passage)
        )
        return [
            IndexEntry(
                entry_id=f"{passage.passage_id}#{number:03d}",
                passage_id=passage.passage_id,
                item=passage.item,
                kind=passage.kind,
                page=passage.page,
                text=text,
            )
            for number, text in enumerate(texts, start=1)
        ]

    def _table_texts(self, passage: Passage) -> list[str]:
        prefix = passage.section_path_text
        return [f"{prefix}\n\n{body}" for body in self._table_cards.card_bodies(passage)]

    def _text_texts(self, passage: Passage) -> list[str]:
        texts: list[str] = []
        groups = _groups(passage)
        for group in groups:
            prefix = _PATH_SEPARATOR.join((*passage.section_path, *group.headings))
            texts.extend(f"{prefix}\n\n{piece}" for piece in self._packer.pack(group.paragraphs))
        if not texts:
            # A heading-only Passage (`Item 6. [Reserved]`) stays findable by its heading.
            headings = [heading for group in groups for heading in group.headings]
            texts.append(_PATH_SEPARATOR.join((*passage.section_path, *headings)))
        return texts


def _groups(passage: Passage) -> list[_Group]:
    """Split a text Passage's Markdown into heading-delimited groups of paragraphs.

    The Passage's own `## heading` is dropped when it already ends the Section
    Path. Consecutive headings with no text between them form one group.
    """
    groups: list[_Group] = []
    current = _Group(headings=[], paragraphs=[])
    for block in passage.content.split("\n\n"):
        block = block.strip()
        heading = _heading(block)
        if heading is None:
            if block:
                current.paragraphs.append(block)
            continue
        if current.paragraphs:
            groups.append(current)
            current = _Group(headings=[], paragraphs=[])
        if not _ends_path(passage.section_path, heading):
            current.headings.append(heading)
    groups.append(current)
    return groups


def _heading(block: str) -> str | None:
    for marker in ("## ", "### "):
        if block.startswith(marker):
            return block.removeprefix(marker).strip()
    return None


def _ends_path(section_path: Sequence[str], heading: str) -> bool:
    return bool(section_path) and section_path[-1] == heading
