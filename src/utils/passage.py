"""The Passage: the returnable unit of the Filing (see CONTEXT.md)."""

from dataclasses import dataclass
from enum import StrEnum


class PassageKind(StrEnum):
    """What a Passage holds."""

    SECTION = "section"
    """The text under one heading (or an Item's opening text before its first heading)."""

    RISK_FACTOR = "risk_factor"
    """One individual risk factor in Item 1A: its heading sentence and its explanation."""

    NOTE = "note"
    """One whole Note to the financial statements, sub-headings included."""

    TABLE = "table"
    """One table, rendered to Markdown, with its caption."""


@dataclass(frozen=True)
class Passage:
    """A returnable unit of the Filing: one subsection, risk factor, Note or table.

    `content` is Markdown. A text Passage starts with its heading as `## <heading>`;
    inside a Note, sub-headings are `### <sub-heading>` lines; paragraphs are
    separated by blank lines; a table inside the text is replaced by a
    `_[Table: <caption>]_` line, the table itself being its own Passage.

    `page` is the printed page number from the Filing's page footer. It is `None`
    only for unnumbered front pages (the cover). `page_approximate` is `True` when
    the number was inferred rather than read from a footer.
    """

    passage_id: str
    item: str
    section_path: tuple[str, ...]
    page: int | None
    kind: PassageKind
    content: str
    page_approximate: bool = False

    @property
    def section_path_text(self) -> str:
        """The Section Path as written in a Citation, e.g. `Item 7 > Gross Margin`."""
        return " > ".join(self.section_path)
