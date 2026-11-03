"""Render a Filing `<table>` to a compact Markdown table."""

import re
from dataclasses import dataclass

from bs4 import Tag

from utils.html_text import emphasis, visible_text

# Cells that are only a currency sign, or only a suffix, belong to a neighbouring figure.
_PREFIX_CELLS = frozenset({"$", "€", "£", "¥", "("})
_SUFFIX_CELLS = frozenset({"%", ")", "%)"})
_HIDDEN = re.compile(r"display\s*:\s*none")


@dataclass
class _Cell:
    """One non-empty cell after span expansion: grid columns [start, end)."""

    text: str
    start: int
    end: int
    bold: bool


class TableRenderer:
    """Turns a layout-heavy financial `<table>` into a Markdown table.

    The Filing's tables carry a grid-sizing first row, empty spacer columns, and
    figures split across cells (`$` | `34,550` | `%`). Rendering:

    1. Expand `colspan` / `rowspan` into grid columns; drop hidden and empty cells.
    2. Merge a lone `$` (or other prefix) cell into the next value, and a lone
       `%` / `)` cell into the previous one.
    3. Derive logical columns from the cells' grid spans, so a value that spans
       two grid columns in one row and sits in the second of them in another
       row lands in the same column, while a header spanning several periods
       does not fuse those periods together.
    4. Leading rows whose row-label column is empty, or with several cells all
       bold, are the header; their texts are joined per column (e.g. `Years ended
       September 27, 2025`). A table without such rows gets a blank Markdown
       header.
    """

    def render(self, table: Tag) -> str | None:
        """Return the Markdown for `table`, or `None` when it has no visible text."""
        rows = [cells for cells in self._grid_rows(table) if cells]
        if not rows:
            return None
        columns = self._logical_columns(rows)
        header_count = self._header_row_count(rows, columns)
        grid = [
            self._place(row, columns, spread=index < header_count) for index, row in enumerate(rows)
        ]
        # With no header rows, the Markdown header stays blank so no data row is lost.
        header = [
            " ".join(filter(None, column)) for column in zip(*grid[:header_count], strict=True)
        ]
        header = header or [""] * len(columns)
        body = grid[header_count:]

        lines = [self._markdown_row(header), self._markdown_row(["---"] * len(columns))]
        lines.extend(self._markdown_row(row) for row in body)
        return "\n".join(lines)

    def _grid_rows(self, table: Tag) -> list[list[_Cell]]:
        """Each row's non-empty cells with grid spans, honouring colspan and rowspan.

        `$` / `%` cells are already merged into their figures. Hidden cells are
        skipped, as a browser removes them from the table layout.
        """
        rows: list[list[_Cell]] = []
        # Grid column -> number of further rows a cell above still covers it.
        carried: dict[int, int] = {}
        for tr in table.find_all("tr"):
            cells: list[_Cell] = []
            position = 0
            for td in tr.find_all(["td", "th"], recursive=False):
                if _HIDDEN.search(td.get("style", "")):
                    continue
                while carried.get(position, 0) > 0:
                    position += 1
                colspan, rowspan = self._span(td, "colspan"), self._span(td, "rowspan")
                text = visible_text(td)
                if text:
                    cells.append(_Cell(text, position, position + colspan, emphasis(td)[0]))
                if rowspan > 1:
                    for column in range(position, position + colspan):
                        carried[column] = rowspan
                position += colspan
            carried = {column: left - 1 for column, left in carried.items() if left > 1}
            rows.append(self._merge_split_figures(cells))
        return rows

    @staticmethod
    def _span(td: Tag, attribute: str) -> int:
        try:
            return max(1, int(td.get(attribute, 1)))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _merge_split_figures(cells: list[_Cell]) -> list[_Cell]:
        merged: list[_Cell] = []
        pending_prefix: _Cell | None = None
        for cell in cells:
            if cell.text in _PREFIX_CELLS:
                # Consecutive prefixes (`$` then `(`) chain onto the same figure.
                if pending_prefix is not None:
                    cell = _Cell(
                        pending_prefix.text + cell.text, pending_prefix.start, cell.end, cell.bold
                    )
                pending_prefix = cell
                continue
            if cell.text in _SUFFIX_CELLS and merged and pending_prefix is None:
                merged[-1].text += cell.text
                merged[-1].end = cell.end
                continue
            if pending_prefix is not None:
                cell = _Cell(
                    pending_prefix.text + cell.text, pending_prefix.start, cell.end, cell.bold
                )
                pending_prefix = None
            merged.append(cell)
        if pending_prefix is not None:
            merged.append(pending_prefix)
        return merged

    @staticmethod
    def _logical_columns(rows: list[list[_Cell]]) -> list[tuple[int, int]]:
        """Cluster cell spans into columns, narrowest first.

        A span overlapping no column starts one; overlapping one column widens it;
        overlapping several is a spanning header and leaves the columns alone.
        """
        spans = sorted(
            {(cell.start, cell.end) for row in rows for cell in row},
            key=lambda span: (span[1] - span[0], span[0]),
        )
        columns: list[tuple[int, int]] = []
        for start, end in spans:
            hits = [
                i for i, (c_start, c_end) in enumerate(columns) if start < c_end and c_start < end
            ]
            if not hits:
                columns.append((start, end))
            elif len(hits) == 1:
                c_start, c_end = columns[hits[0]]
                widened = (min(start, c_start), max(end, c_end))
                others = [c for i, c in enumerate(columns) if i != hits[0]]
                if not any(
                    widened[0] < o_end and o_start < widened[1] for o_start, o_end in others
                ):
                    columns[hits[0]] = widened
        return sorted(columns)

    @staticmethod
    def _overlapping(cell: _Cell, columns: list[tuple[int, int]]) -> list[int]:
        return [
            i for i, (start, end) in enumerate(columns) if cell.start < end and start < cell.end
        ]

    def _header_row_count(self, rows: list[list[_Cell]], columns: list[tuple[int, int]]) -> int:
        """Leading rows with an empty row-label column, or with several cells all bold.

        A lone bold cell (`ASSETS:`) is a row-group label, not a header.
        """
        count = 0
        for row in rows:
            titled = len(row) > 1 and all(cell.bold for cell in row)
            has_label = any(0 in self._overlapping(cell, columns) for cell in row)
            if has_label and not titled:
                break
            count += 1
        return count if count < len(rows) else 0

    def _place(self, row: list[_Cell], columns: list[tuple[int, int]], spread: bool) -> list[str]:
        """Lay the row's cells out over the logical columns.

        A header cell spanning several columns is repeated in each (`spread`);
        a body cell goes to the first column it covers.
        """
        placed = [""] * len(columns)
        for cell in row:
            targets = self._overlapping(cell, columns)
            for index in targets if spread else targets[:1]:
                placed[index] = f"{placed[index]} {cell.text}".strip()
        return placed

    @staticmethod
    def _markdown_row(cells: list[str]) -> str:
        return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"
