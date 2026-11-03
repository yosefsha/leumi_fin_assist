"""The Filing as an ordered stream of layout blocks, produced by `FilingLayoutReader`."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextBlock:
    """One paragraph-level `<div>` outside any table."""

    text: str
    page_index: int
    bold: bool
    """Every visible character is bold."""
    italic: bool
    """Every visible character is italic."""


@dataclass(frozen=True)
class TableBlock:
    """One `<table>`, already rendered to Markdown."""

    markdown: str
    page_index: int


@dataclass(frozen=True)
class AnchorBlock:
    """An element the Table of Contents links to; `item` is set when it starts an Item."""

    target_id: str
    item: str | None


Block = TextBlock | TableBlock | AnchorBlock


@dataclass(frozen=True)
class PageNumber:
    """The page a block is printed on."""

    number: int | None
    approximate: bool


@dataclass(frozen=True)
class FilingLayout:
    """The Filing as an ordered block stream plus the page of each physical page."""

    blocks: tuple[Block, ...]
    pages: tuple[PageNumber, ...]
    """Indexed by a block's `page_index` (the physical page, counting from 0)."""

    def page_of(self, block: TextBlock | TableBlock) -> PageNumber:
        return self.pages[block.page_index]
