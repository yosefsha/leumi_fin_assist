"""The Filing parser on Apple's FY2025 10-K (issue #3, PR #16), its failure paths, and
other filers' page footers on a synthetic Filing (issue #35)."""

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


# --- Other filers' page footers (issue #35), on a synthetic three-page Filing -----------------

_HR_BREAK = '<hr style="page-break-after:always"/>'
_DIV_BREAK = '<div style="page-break-before:always"></div>'


def _synthetic_filing(footer_1: str, footer_2: str, page_break: str = _HR_BREAK) -> str:
    """A cover with a linked Table of Contents, then Item 1 and Item 1A on one page each."""
    return f"""<html><body>
<table>
  <tr><td><a href="#i1">Item 1.</a></td><td>Business</td></tr>
  <tr><td><a href="#i1a">Item 1A.</a></td><td>Risk Factors</td></tr>
</table>
<div>Contoso Ltd. Annual Report on Form 10-K for the fiscal year 2026</div>
{page_break}
<div id="i1"><span style="font-weight:bold">Item 1. Business</span></div>
<div>Contoso makes 12 kinds of widgets.</div>
<div>{footer_1}</div>
{page_break}
<div id="i1a"><span style="font-weight:bold">Item 1A. Risk Factors</span></div>
<div>Widget demand may fall.</div>
<div>{footer_2}</div>
</body></html>"""


def _pages(passages: tuple[Passage, ...]) -> dict[str, tuple[int | None, bool]]:
    return {p.item: (p.page, p.page_approximate) for p in passages if p.item != "Front Matter"}


@pytest.mark.parametrize(
    ("footer_1", "footer_2"),
    [
        ("Contoso Ltd. | 2026 Form 10-K | 7", "Contoso Ltd. | 2026 Form 10-K | 8"),
        ("Contoso Ltd. 2026 Form 10-K 7", "Contoso Ltd. 2026 Form 10-K 8"),
        ("2026 Annual Report on Form 10-K – Page 7", "2026 Annual Report on Form 10-K – Page 8"),
        ("7", "8"),
        ("- 7 -", "- 8 -"),
        ("Page 7", "Page 8"),
    ],
    ids=["apple-style", "space", "dash-page", "page-only", "dashed", "page-word"],
)
def test_other_filers_footers_give_each_page_its_printed_number(
    footer_1: str, footer_2: str
) -> None:
    passages = FilingParser().parse(_synthetic_filing(footer_1, footer_2))
    assert _pages(passages) == {"Item 1": (7, False), "Item 1A": (8, False)}
    assert not any(footer_2 in passage.content for passage in passages)


def test_a_page_break_on_a_div_separates_pages_too() -> None:
    passages = FilingParser().parse(_synthetic_filing("7", "8", page_break=_DIV_BREAK))
    assert _pages(passages) == {"Item 1": (7, False), "Item 1A": (8, False)}


def test_a_filing_without_footers_gives_no_page_rather_than_a_guess() -> None:
    passages = FilingParser().parse(_synthetic_filing("Contoso makes gadgets.", "Gadgets too."))
    assert {passage.page for passage in passages} == {None}
    assert not any(passage.page_approximate for passage in passages)


def test_a_bare_number_that_is_not_last_on_its_page_is_content_not_a_footer() -> None:
    html = _synthetic_filing("12", "End of Item 1A.").replace(
        "<div>12</div>", "<div>12</div><div>units shipped</div>"
    )
    passages = FilingParser().parse(html)
    assert {passage.page for passage in passages} == {None}
    assert any("12" in passage.content for passage in passages if passage.item == "Item 1")


def test_a_footer_that_does_not_count_upward_is_not_a_page_number() -> None:
    passages = FilingParser().parse(_synthetic_filing("7", "3"))
    # Page 3 after page 7 is not a page number: the page continues from 7, marked approximate.
    assert _pages(passages) == {"Item 1": (7, False), "Item 1A": (8, True)}
