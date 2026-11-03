"""Citation IDs, validation and Sources rendering (issue #8, PR #17)."""

import logging

import pytest

from utils.citation_format import CitationFormatter
from utils.citations import CitationRegistry
from utils.cited_answer import CitationResolver
from utils.passage import Passage, PassageKind
from utils.web_result import WebResult


def _passage(passage_id: str, page: int) -> Passage:
    return Passage(
        passage_id=passage_id,
        item="Item 7",
        section_path=("Item 7", "Gross Margin"),
        page=page,
        kind=PassageKind.SECTION,
        content="## Gross Margin\n\nText.",
    )


@pytest.fixture
def resolver() -> CitationResolver:
    return CitationResolver(CitationFormatter(fiscal_year=2025))


def test_unregistered_marker_is_dropped_with_a_warning(
    resolver: CitationResolver, caplog: pytest.LogCaptureFixture
) -> None:
    registry = CitationRegistry()
    for number in (1, 2, 3):
        registry.register_passage(_passage(f"item-7-00{number}", page=23 + number))

    with caplog.at_level(logging.WARNING, logger="utils.cited_answer"):
        answer = resolver.resolve("Gross margin rose [F2][W9].", registry)

    assert answer.body == "Gross margin rose [1]."
    assert answer.sources == ("10-K FY2025 — Item 7 > Gross Margin, p. 25",)
    assert "W9" in caplog.text
    assert "F2" not in caplog.text


def test_markers_are_renumbered_by_first_appearance(resolver: CitationResolver) -> None:
    registry = CitationRegistry()
    registry.register_passage(_passage("item-7-001", page=24))
    registry.register_web_result(WebResult("https://ex.com/a", "Apple news", "Body."))

    answer = resolver.resolve("A [W1]. B [F1]. C [W1].", registry)

    assert answer.body == "A [1]. B [2]. C [1]."
    assert answer.sources == (
        "Apple news — https://ex.com/a (date unknown)",
        "10-K FY2025 — Item 7 > Gross Margin, p. 24",
    )


def test_reregistering_a_passage_returns_its_id() -> None:
    registry = CitationRegistry()
    a, b, c = (_passage(f"item-7-00{n}", page=24) for n in (1, 2, 3))
    ids = [registry.register_passage(p).citation_id for p in (a, b, c, b)]
    assert ids == ["F1", "F2", "F3", "F2"]
    assert len(registry) == 3


def test_reregistering_a_url_returns_its_id() -> None:
    registry = CitationRegistry()
    first = registry.register_web_result(WebResult("https://ex.com/a", "Apple news", "x"))
    again = registry.register_web_result(WebResult("  https://ex.com/a ", "Other title", "y"))
    other = registry.register_web_result(WebResult("https://ex.com/b", "", "z"))
    assert (first.citation_id, again.citation_id, other.citation_id) == ("W1", "W1", "W2")
    assert again.result.title == "Apple news"


def test_a_new_registry_restarts_at_f1() -> None:
    CitationRegistry().register_passage(_passage("item-7-001", page=24))
    fresh = CitationRegistry().register_passage(_passage("item-7-002", page=24))
    assert fresh.citation_id == "F1"
