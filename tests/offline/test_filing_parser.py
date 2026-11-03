"""The Filing parser on Apple's FY2025 10-K (issue #3, PR #16), and its failure paths."""

import re
from pathlib import Path

import pytest

from utils.filing_parser import FilingParseError, FilingParser
from utils.passage import Passage, PassageKind

_NOTE_NUMBER = re.compile(r"^Note (\d+)\b")


def _item(passages: tuple[Passage, ...], item: str) -> tuple[Passage, ...]:
    return tuple(passage for passage in passages if passage.item == item)


@pytest.mark.parametrize("item", ["Item 1", "Item 1A", "Item 7", "Item 8"])
def test_core_items_have_substantial_content(passages: tuple[Passage, ...], item: str) -> None:
    content = sum(len(passage.content) for passage in _item(passages, item))
    assert content > 10_000


def test_item_1a_is_not_the_whole_document(passages: tuple[Passage, ...]) -> None:
    total = sum(len(passage.content) for passage in passages)
    risk_section = sum(len(passage.content) for passage in _item(passages, "Item 1A"))
    assert risk_section < total / 2


def test_risk_factors_are_individual_passages_in_document_order(
    passages: tuple[Passage, ...],
) -> None:
    risks = [p for p in passages if p.kind is PassageKind.RISK_FACTOR]
    assert len(risks) >= 20
    assert all(risk.item == "Item 1A" for risk in risks)
    assert "Macroeconomic and Industry Risks" in risks[0].section_path
    last = "The price of the Company’s stock is subject to volatility."
    assert risks[-1].section_path[-1] == last
    pages = [risk.page for risk in risks]
    assert pages == sorted(pages)


def test_statement_of_operations_table_has_line_items_and_fiscal_years(
    passages: tuple[Passage, ...],
) -> None:
    [table] = [
        p
        for p in _item(passages, "Item 8")
        if p.kind is PassageKind.TABLE
        and p.section_path[-1] == "CONSOLIDATED STATEMENTS OF OPERATIONS"
    ]
    for expected in (
        "Research and development",
        "Total net sales",
        "September 27, 2025",
        "September 28, 2024",
        "September 30, 2023",
    ):
        assert expected in table.content
    assert "| Total net sales | 416,161 |" in table.content
    assert "| Research and development | 34,550 |" in table.content


def test_page_numbers_never_decrease(passages: tuple[Passage, ...]) -> None:
    pages = [passage.page for passage in passages if passage.page is not None]
    assert pages
    assert pages == sorted(pages)


def test_notes_1_to_13_are_one_passage_each(passages: tuple[Passage, ...]) -> None:
    notes = [p for p in passages if p.kind is PassageKind.NOTE]
    numbers = [int(_NOTE_NUMBER.match(note.section_path[-1]).group(1)) for note in notes]
    assert numbers == list(range(1, 14))
    assert all(note.item == "Item 8" for note in notes)


def test_passage_ids_are_unique(passages: tuple[Passage, ...]) -> None:
    ids = [passage.passage_id for passage in passages]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "html",
    ["", "<html><body><p><b>Annual report</b></p><p>No Items here.</p></body></html>"],
    ids=["empty", "no-items"],
)
def test_html_without_items_raises(html: str) -> None:
    with pytest.raises(FilingParseError, match="No Items found"):
        FilingParser().parse(html)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FilingParseError, match="Cannot read the Filing"):
        FilingParser().parse_file(tmp_path / "missing.htm")
