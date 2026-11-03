"""Turn a table Passage into Table Cards: caption, column headers and row labels, no figures."""

import re
from dataclasses import dataclass

from utils.passage import Passage, PassageKind
from utils.text_packer import TextPacker

_CELL_SEPARATOR = re.compile(r"(?<!\\)\|")
_ROW_SEPARATOR = "; "


@dataclass(frozen=True)
class _Table:
    title: str
    caption: str | None
    columns: tuple[str, ...]
    row_labels: tuple[str, ...]


class TableCardBuilder:
    """Builds the Table Card bodies for one table Passage (ADR-0002).

    A card lists the table's caption (or heading), its column headers and its row
    labels; the figures stay in the Passage. When the card exceeds the packer's
    budget, the row labels are split into consecutive groups and every card
    repeats the caption and column headers.
    """

    def __init__(self, packer: TextPacker) -> None:
        self._packer = packer

    def card_bodies(self, passage: Passage) -> list[str]:
        """Return the card texts (without the Section Path prefix) for `passage`."""
        if passage.kind is not PassageKind.TABLE:
            raise ValueError(f"Passage {passage.passage_id} is a {passage.kind}, not a table.")
        table = _parse(passage.content)
        if not table.row_labels or self._packer.fits(_card(table, table.row_labels)):
            return [_card(table, table.row_labels)]
        cards: list[str] = []
        group: list[str] = []
        for label in table.row_labels:
            if group and not self._packer.fits(_card(table, (*group, label))):
                cards.append(_card(table, tuple(group)))
                group = []
            group.append(label)
        cards.append(_card(table, tuple(group)))
        return cards


def _card(table: _Table, row_labels: tuple[str, ...]) -> str:
    lines = [f"Table: {table.caption or table.title}"]
    if table.columns:
        lines.append(f"Columns: {_ROW_SEPARATOR.join(table.columns)}")
    if row_labels:
        lines.append(f"Rows: {_ROW_SEPARATOR.join(row_labels)}")
    return "\n".join(lines)


def _parse(content: str) -> _Table:
    """Split a table Passage's Markdown into heading, caption, header row and row labels."""
    title = ""
    caption_parts: list[str] = []
    table_lines: list[str] = []
    for block in content.split("\n\n"):
        if block.startswith("## ") and not title:
            title = block.removeprefix("## ").strip()
        elif block.startswith("|"):
            table_lines.extend(line for line in block.splitlines() if line.startswith("|"))
        else:
            caption_parts.append(block.strip())
    rows = [_cells(line) for line in table_lines]
    header = rows[0] if rows else []
    body = rows[2:]  # rows[1] is the `| --- |` separator
    return _Table(
        title=title,
        caption=" ".join(caption_parts) or None,
        columns=tuple(cell for cell in header if cell),
        row_labels=tuple(dict.fromkeys(row[0] for row in body if row and row[0])),
    )


def _cells(line: str) -> list[str]:
    inner = line.strip().removeprefix("|").removesuffix("|")
    return [cell.strip().replace("\\|", "|") for cell in _CELL_SEPARATOR.split(inner)]
