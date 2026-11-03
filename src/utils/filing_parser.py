"""Turn the Filing's HTML into Passages: Items, headings, risk factors, Notes, tables."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from utils.filing_layout import (
    AnchorBlock,
    Block,
    FilingLayout,
    FilingLayoutReader,
    PageNumber,
    TableBlock,
    TextBlock,
)
from utils.passage import Passage, PassageKind
from utils.table_renderer import TableRenderer

FRONT_MATTER = "Front Matter"
"""The `item` of text before Item 1 (cover page, forward-looking statements notice)."""

_RISK_FACTORS_ITEM = "Item 1A"
_FINANCIAL_STATEMENTS_ITEM = "Item 8"

_ITEM_HEADING = re.compile(r"^Item\s+(\d+[A-C]?)\.", re.IGNORECASE)
_NOTE_HEADING = re.compile(r"^Note\s+\d+\s*[–-]\s*\S")
# Navigation labels that close the open section but are not part of any Section Path.
_STRUCTURAL_HEADING = re.compile(r"^(?:PART\s+[IV]+|TABLE OF CONTENTS)$", re.IGNORECASE)
_HAS_LETTER = re.compile(r"[^\W\d_]")

_MAX_HEADING_CHARS = 200
"""A wholly bold or italic block longer than this is an emphasised paragraph, not a heading."""

_MAX_BOLD_ITALIC_HEADING_CHARS = 400
"""Bold-italic headings are whole risk-factor sentences; the Filing's longest is 284 chars."""

_MAX_CAPTION_CHARS = 300
"""A paragraph right before a table, at most this long, is taken as the table's caption."""

# Section Path depth by emphasis: bold headings sit above italic ones; a Note is the root.
_NOTE_LEVEL = 0
_BOLD_LEVEL = 1
_ITALIC_LEVEL = 2


class FilingParseError(Exception):
    """The Filing could not be read, or its structure was not recognised."""


class FilingParser:
    """Parses the Filing into Passages in document order.

    Items start at the Table of Contents' link targets (falling back to the last
    bold `Item N.` heading per Item when the ToC has no links), so the ToC itself
    never splits the document. Within an Item, a wholly bold or italic block
    outside a table is a heading; bold nests above italic in the Section Path.
    In Item 1A, each bold-italic heading is one risk factor. In Item 8, each
    `Note N – Title` heading starts one Note Passage that runs to the next Note
    or ToC target. Every table is its own Passage.
    """

    def __init__(self, layout_reader: FilingLayoutReader | None = None) -> None:
        self._layout_reader = layout_reader or FilingLayoutReader(TableRenderer())

    def parse_file(self, path: Path) -> tuple[Passage, ...]:
        """Read and parse the Filing at `path`."""
        try:
            html = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError) as error:
            raise FilingParseError(f"Cannot read the Filing at {path}: {error}") from error
        return self.parse(html)

    def parse(self, html: str) -> tuple[Passage, ...]:
        """Parse Filing HTML. Raises `FilingParseError` when no Item can be located."""
        layout = self._layout_reader.read(html)
        starts = self._item_starts(layout.blocks)
        if not starts:
            raise FilingParseError(
                "No Items found: the Filing has neither Table of Contents links to Items "
                "nor bold 'Item N.' headings."
            )
        return _PassageAssembler(layout, starts).assemble()

    @staticmethod
    def _item_starts(blocks: tuple[Block, ...]) -> dict[int, str]:
        """Map block index → Item label for each block that starts an Item."""
        anchored = {
            index: block.item
            for index, block in enumerate(blocks)
            if isinstance(block, AnchorBlock) and block.item
        }
        if anchored:
            return anchored
        # Fallback: the last heading per Item, so an earlier mention never wins.
        last_heading: dict[str, int] = {}
        for index, block in enumerate(blocks):
            if isinstance(block, TextBlock) and _is_heading(block):
                match = _ITEM_HEADING.match(block.text)
                if match:
                    last_heading[f"Item {match.group(1).upper()}"] = index
        return {index: label for label, index in last_heading.items()}


def _is_heading(block: TextBlock) -> bool:
    if not _HAS_LETTER.search(block.text):
        # An emphasised figure or phone number, e.g. the cover's "(408) 996-1010".
        return False
    if block.bold and block.italic:
        return len(block.text) <= _MAX_BOLD_ITALIC_HEADING_CHARS
    return (block.bold or block.italic) and len(block.text) <= _MAX_HEADING_CHARS


@dataclass(frozen=True)
class _Heading:
    level: int
    title: str


@dataclass
class _Draft:
    """A text Passage being accumulated; `slot` keeps its place in document order."""

    slot: int
    item: str
    section_path: tuple[str, ...]
    page: PageNumber
    kind: PassageKind
    lines: list[str] = field(default_factory=list)
    has_body: bool = False
    is_item_heading: bool = False
    """Opened by the Item's own heading (`Item 6. [Reserved]`)."""


@dataclass(frozen=True)
class _Finished:
    item: str
    section_path: tuple[str, ...]
    page: PageNumber
    kind: PassageKind
    content: str


class _PassageAssembler:
    """Walks the block stream once, opening and closing Passages at headings."""

    def __init__(self, layout: FilingLayout, item_starts: dict[int, str]) -> None:
        self._layout = layout
        self._item_starts = item_starts
        self._item = FRONT_MATTER
        self._headings: list[_Heading] = []
        self._draft: _Draft | None = None
        self._caption: str | None = None
        self._slots: list[_Finished | None] = []
        self._item_first_slot = 0
        self._bare_item_heading: _Draft | None = None

    def assemble(self) -> tuple[Passage, ...]:
        for index, block in enumerate(self._layout.blocks):
            if index in self._item_starts:
                self._start_item(self._item_starts[index])
            if isinstance(block, AnchorBlock):
                self._on_anchor()
            elif isinstance(block, TableBlock):
                self._on_table(block)
            elif _is_heading(block):
                self._on_heading(block)
            else:
                self._on_paragraph(block)
        self._flush()
        self._close_item()
        return self._numbered()

    # -- block handlers --------------------------------------------------------------

    def _start_item(self, item: str) -> None:
        self._flush()
        self._close_item()
        self._item = item
        self._headings = []
        self._item_first_slot = len(self._slots)

    def _on_anchor(self) -> None:
        # A ToC target inside an Item (e.g. the auditor's report after the Notes)
        # closes any open Note.
        if self._in_note:
            self._flush()
            self._headings = []

    def _on_heading(self, block: TextBlock) -> None:
        text = block.text
        self._caption = None
        if _STRUCTURAL_HEADING.match(text):
            self._flush()
            self._headings = []
            return
        if _ITEM_HEADING.match(text):
            self._flush()
            self._headings = []
            self._open(block, PassageKind.SECTION, heading=text).is_item_heading = True
            return
        if self._item == _FINANCIAL_STATEMENTS_ITEM and _NOTE_HEADING.match(text):
            self._flush()
            self._headings = [_Heading(_NOTE_LEVEL, text)]
            self._open(block, PassageKind.NOTE, heading=text)
            return

        level = _BOLD_LEVEL if block.bold and not block.italic else _ITALIC_LEVEL
        if self._in_note:
            self._push_heading(_Heading(level, text))
            self._draft_for(block).lines.append(f"### {text}")
            return
        self._flush()
        self._push_heading(_Heading(level, text))
        is_risk_factor = self._item == _RISK_FACTORS_ITEM and block.bold and block.italic
        kind = PassageKind.RISK_FACTOR if is_risk_factor else PassageKind.SECTION
        self._open(block, kind, heading=text)

    def _on_paragraph(self, block: TextBlock) -> None:
        draft = self._draft_for(block)
        draft.lines.append(block.text)
        draft.has_body = True
        self._caption = block.text if len(block.text) <= _MAX_CAPTION_CHARS else None

    def _on_table(self, block: TableBlock) -> None:
        caption = self._take_caption()
        path = self._section_path()
        title = path[-1]
        lines = [f"## {title}"]
        if caption:
            lines.append(caption)
        lines.append(block.markdown)
        self._slots.append(
            _Finished(
                self._item, path, self._layout.page_of(block), PassageKind.TABLE, "\n\n".join(lines)
            )
        )
        self._draft_for(block).lines.append(f"_[Table: {caption or title}]_")

    # -- helpers ---------------------------------------------------------------------

    @property
    def _in_note(self) -> bool:
        return bool(self._headings) and self._headings[0].level == _NOTE_LEVEL

    def _push_heading(self, heading: _Heading) -> None:
        floor = 1 if self._in_note else 0
        while len(self._headings) > floor and self._headings[-1].level >= heading.level:
            self._headings.pop()
        self._headings.append(heading)

    def _section_path(self) -> tuple[str, ...]:
        return (self._item, *(heading.title for heading in self._headings))

    def _take_caption(self) -> str | None:
        """Move the paragraph right before a table out of the text and into the table."""
        caption, self._caption = self._caption, None
        if caption and self._draft and self._draft.lines and self._draft.lines[-1] == caption:
            self._draft.lines.pop()
            self._draft.has_body = any(
                not line.startswith(("## ", "### ", "_[Table: ")) for line in self._draft.lines
            )
        return caption

    def _open(self, block: TextBlock, kind: PassageKind, heading: str) -> _Draft:
        self._slots.append(None)
        self._draft = _Draft(
            slot=len(self._slots) - 1,
            item=self._item,
            section_path=self._section_path(),
            page=self._layout.page_of(block),
            kind=kind,
            lines=[f"## {heading}"],
        )
        return self._draft

    def _draft_for(self, block: TextBlock | TableBlock) -> _Draft:
        """The open draft, or a heading-less one for text that follows a table or Item start."""
        if self._draft is not None:
            return self._draft
        self._slots.append(None)
        self._draft = _Draft(
            slot=len(self._slots) - 1,
            item=self._item,
            section_path=self._section_path(),
            page=self._layout.page_of(block),
            kind=PassageKind.NOTE if self._in_note else PassageKind.SECTION,
        )
        return self._draft

    def _flush(self) -> None:
        """Close the open draft; a draft with only headings and table links is dropped."""
        draft, self._draft = self._draft, None
        self._caption = None
        if draft is None:
            return
        if not draft.has_body:
            if draft.is_item_heading:
                self._bare_item_heading = draft
            return
        self._slots[draft.slot] = _Finished(
            draft.item, draft.section_path, draft.page, draft.kind, "\n\n".join(draft.lines)
        )

    def _close_item(self) -> None:
        """Keep a heading-only Item (`Item 6. [Reserved]`) when it yielded no other Passage."""
        draft, self._bare_item_heading = self._bare_item_heading, None
        produced = any(slot is not None for slot in self._slots[self._item_first_slot :])
        if draft is not None and not produced:
            self._slots[draft.slot] = _Finished(
                draft.item, draft.section_path, draft.page, draft.kind, "\n\n".join(draft.lines)
            )

    def _numbered(self) -> tuple[Passage, ...]:
        counters: dict[str, int] = {}
        passages: list[Passage] = []
        for finished in self._slots:
            if finished is None:
                continue
            slug = finished.item.lower().replace(" ", "-")
            counters[slug] = counters.get(slug, 0) + 1
            passages.append(
                Passage(
                    passage_id=f"{slug}-{counters[slug]:03d}",
                    item=finished.item,
                    section_path=finished.section_path,
                    page=finished.page.number,
                    kind=finished.kind,
                    content=finished.content,
                    page_approximate=finished.page.approximate,
                )
            )
        return tuple(passages)
