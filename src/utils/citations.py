"""The per-query Citation registry: code, not the model, assigns citation IDs.

Each Filing Passage and web result returned to the model is registered here and
gets an ID (`F1, F2…` for Passages, `W1, W2…` for web results). Registering the
same Passage (by `passage_id`) or the same URL again returns the ID it already
has. A registry is created fresh for each query, so IDs never leak between
questions.
"""

from dataclasses import dataclass

from utils.passage import Passage
from utils.web_result import WebResult

FILING_PREFIX = "F"
WEB_PREFIX = "W"


@dataclass(frozen=True)
class FilingCitation:
    """A registered Filing Passage and the ID the model cites it by."""

    citation_id: str
    passage: Passage


@dataclass(frozen=True)
class WebCitation:
    """A registered web result and the ID the model cites it by."""

    citation_id: str
    result: WebResult


type Citation = FilingCitation | WebCitation


class CitationRegistry:
    """Assigns stable citation IDs to the sources returned to the model during one query."""

    def __init__(self) -> None:
        self._by_id: dict[str, Citation] = {}
        self._by_passage_id: dict[str, FilingCitation] = {}
        self._by_url: dict[str, WebCitation] = {}

    def register_passage(self, passage: Passage) -> FilingCitation:
        """Return the Citation for `passage`, assigning the next `F<n>` ID on first sight."""
        citation = self._by_passage_id.get(passage.passage_id)
        if citation is None:
            citation_id = f"{FILING_PREFIX}{len(self._by_passage_id) + 1}"
            citation = FilingCitation(citation_id, passage)
            self._by_passage_id[passage.passage_id] = citation
            self._by_id[citation_id] = citation
        return citation

    def register_web_result(self, result: WebResult) -> WebCitation:
        """Return the Citation for `result`, assigning the next `W<n>` ID on first sight of its URL.

        A URL seen before keeps its ID and its first-registered record.
        """
        citation = self._by_url.get(result.url)
        if citation is None:
            citation_id = f"{WEB_PREFIX}{len(self._by_url) + 1}"
            citation = WebCitation(citation_id, result)
            self._by_url[result.url] = citation
            self._by_id[citation_id] = citation
        return citation

    def get(self, citation_id: str) -> Citation | None:
        """Return the Citation registered under `citation_id`, or `None` if there is none."""
        return self._by_id.get(citation_id)

    def __len__(self) -> int:
        return len(self._by_id)
