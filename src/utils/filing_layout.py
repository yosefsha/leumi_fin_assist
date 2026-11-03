"""Flatten the Filing's inline-XBRL HTML into an ordered stream of layout blocks.

The Filing (Workiva output) nests its text in `<div><span style=…>` leaves, wraps
whole runs of those divs in `ix:*` tags, separates pages with
`<hr style="page-break-after:always">` and closes every numbered page with a
footer such as `Apple Inc. | 2025 Form 10-K | 28`. This module walks that tree
once and yields what the parser needs: text blocks with their emphasis, rendered
tables, the Table of Contents' anchor targets, and the printed page of each block.
"""

import re
import warnings
from dataclasses import dataclass

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning

from utils.html_text import emphasis, normalize_whitespace, visible_text
from utils.table_renderer import TableRenderer

_ITEM_LINK = re.compile(r"^Item\s+(\d+[A-C]?)\.?$", re.IGNORECASE)
_PAGE_FOOTER = re.compile(r"Form 10-K\s*\|\s*(\d+)$")
_PAGE_BREAK = re.compile(r"page-break-(?:after|before)\s*:\s*always")
_INTERNAL_LINK = re.compile(r"^#.")
_STRUCTURAL_TAGS = ("div", "table", "hr")


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


class FilingLayoutReader:
    """Reads the Filing's HTML into a `FilingLayout`."""

    def __init__(self, table_renderer: TableRenderer) -> None:
        self._table_renderer = table_renderer

    def read(self, html: str) -> FilingLayout:
        """Flatten `html` into blocks. `ix:*` wrappers are walked through, not skipped."""
        with warnings.catch_warnings():
            # Inline XBRL is XHTML; lxml's HTML parser reads it correctly but bs4 warns.
            warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(html, "lxml")
        for hidden in soup.find_all("ix:header"):
            hidden.decompose()
        for br in soup.find_all("br"):
            br.replace_with(" ")

        targets = self._toc_targets(soup)
        walk = _Walk(targets, self._table_renderer)
        walk.visit(soup.body or soup)
        return FilingLayout(
            blocks=tuple(walk.blocks), pages=self._number_pages(walk.footers, walk.page_index)
        )

    @staticmethod
    def _toc_targets(soup: BeautifulSoup) -> dict[str, str | None]:
        """Map each internal link target to the Item it starts (`None` for other targets)."""
        targets: dict[str, str | None] = {}
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not href.startswith("#") or len(href) == 1:
                continue
            match = _ITEM_LINK.match(visible_text(link))
            target = href[1:]
            if match:
                targets[target] = f"Item {match.group(1).upper()}"
            else:
                targets.setdefault(target, None)
        return targets

    @staticmethod
    def _number_pages(footers: dict[int, int], last_index: int) -> tuple[PageNumber, ...]:
        """Number each physical page from its footer.

        A page without a footer before the first numbered page (the cover) gets
        `None`; one after it continues from the previous number, flagged
        approximate. A Filing with no footers at all is numbered by physical page
        count, also flagged approximate.
        """
        if not footers:
            return tuple(PageNumber(index + 1, approximate=True) for index in range(last_index + 1))
        pages: list[PageNumber] = []
        previous: int | None = None
        for index in range(last_index + 1):
            if index in footers:
                previous = footers[index]
                pages.append(PageNumber(previous, approximate=False))
            elif previous is None:
                pages.append(PageNumber(None, approximate=False))
            else:
                previous += 1
                pages.append(PageNumber(previous, approximate=True))
        return tuple(pages)


class _Walk:
    """One depth-first pass over the document body, collecting blocks in order."""

    def __init__(self, targets: dict[str, str | None], table_renderer: TableRenderer) -> None:
        self._targets = targets
        self._table_renderer = table_renderer
        self.blocks: list[Block] = []
        self.footers: dict[int, int] = {}
        self.page_index = 0

    def visit(self, element: Tag) -> None:
        for child in element.children:
            if isinstance(child, Tag):
                self._visit_tag(child)
            elif type(child) is NavigableString and normalize_whitespace(str(child)):
                # Loose text beside structural siblings: keep it as its own paragraph.
                self._add_text(normalize_whitespace(str(child)), bold=False, italic=False)

    def _visit_tag(self, tag: Tag) -> None:
        if tag.name == "hr":
            if _PAGE_BREAK.search(tag.get("style", "")):
                self.page_index += 1
            return
        target = tag.get("id")
        if target in self._targets:
            self.blocks.append(AnchorBlock(target, self._targets[target]))
        if tag.name == "table":
            self._add_table(tag)
        elif tag.find(_STRUCTURAL_TAGS):
            self.visit(tag)
        else:
            text = visible_text(tag)
            if text:
                bold, italic = emphasis(tag)
                self._add_text(text, bold=bold, italic=italic)

    def _add_table(self, table: Tag) -> None:
        if _is_navigation(table):
            return
        markdown = self._table_renderer.render(table)
        if markdown:
            self.blocks.append(TableBlock(markdown, self.page_index))

    def _add_text(self, text: str, bold: bool, italic: bool) -> None:
        footer = _PAGE_FOOTER.search(text)
        if footer and len(text) < 80:
            self.footers[self.page_index] = int(footer.group(1))
            return
        self.blocks.append(TextBlock(text, self.page_index, bold=bold, italic=italic))


def _is_navigation(table: Tag) -> bool:
    """A table of contents or index: most of its text rows link inside the Filing."""
    rows = [row for row in table.find_all("tr") if row.get_text(strip=True)]
    linked = [row for row in rows if row.find("a", href=_INTERNAL_LINK)]
    return bool(rows) and 2 * len(linked) >= len(rows)
