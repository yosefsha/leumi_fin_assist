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

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning

from utils.filing_blocks import (
    AnchorBlock,
    Block,
    FilingLayout,
    PageNumber,
    TableBlock,
    TextBlock,
)
from utils.html_text import emphasis, normalize_whitespace, visible_text
from utils.table_renderer import TableRenderer

_ITEM_LINK = re.compile(r"^Item\s+(\d+[A-C]?)\.?$", re.IGNORECASE)
_PAGE_FOOTER = re.compile(r"Form 10-K\s*\|\s*(\d+)$")
_PAGE_BREAK = re.compile(r"page-break-(?:after|before)\s*:\s*always")
_INTERNAL_LINK = re.compile(r"^#.")
_STRUCTURAL_TAGS = ("div", "table", "hr")
_HIDDEN = re.compile(r"display\s*:\s*none")


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
        """Map each navigation-table link target to the Item it starts (`None` otherwise).

        Only links inside a Table of Contents or index table count, so a
        cross-reference link in body text never splits a Passage. When several
        targets claim the same Item, the first one in document order wins.
        """
        targets: dict[str, str | None] = {}
        claimed: set[str] = set()
        for table in soup.find_all("table"):
            if not _is_navigation(table):
                continue
            for link in table.find_all("a", href=_INTERNAL_LINK):
                target = link["href"][1:]
                match = _ITEM_LINK.match(visible_text(link))
                item = f"Item {match.group(1).upper()}" if match else None
                if item is not None and item not in claimed and targets.get(target) is None:
                    claimed.add(item)
                    targets[target] = item
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
        if _HIDDEN.search(tag.get("style", "")):
            return
        self._add_anchor(tag)
        if tag.name == "table":
            self._add_table(tag)
        elif tag.find(_STRUCTURAL_TAGS):
            self.visit(tag)
        else:
            # A leaf paragraph: a link target may sit on an inline element inside it.
            for inline in tag.find_all(id=True):
                self._add_anchor(inline)
            text = visible_text(tag)
            if text:
                bold, italic = emphasis(tag)
                self._add_text(text, bold=bold, italic=italic)

    def _add_anchor(self, tag: Tag) -> None:
        target = tag.get("id")
        if target in self._targets:
            self.blocks.append(AnchorBlock(target, self._targets[target]))

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
