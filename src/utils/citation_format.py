"""How a Citation is written: in a tool result for the model, and in the Sources list."""

from utils.citations import Citation, FilingCitation, WebCitation
from utils.passage import Passage
from utils.web_result import WebResult


class CitationFormatter:
    """Writes Citations for the model and for the reader.

    `fiscal_year` is the Filing's fiscal year, written into each Filing source as
    `10-K FY<year>`; it is configuration, not something this class assumes.
    """

    def __init__(self, fiscal_year: int) -> None:
        if fiscal_year < 1:
            raise ValueError(f"fiscal_year must be a positive year; got {fiscal_year}.")
        self._filing_label = f"10-K FY{fiscal_year}"

    def for_model(self, citation: Citation) -> str:
        """Render a registered source as a tool-result block, headed by its citation ID.

        Filing: `[F1] <Section Path> — p. <n> (passage_id <id>, <kind>)` then the
        Passage content; the `passage_id` lets the model open the Passage's
        related Passages with `get_passage`.
        Web: `[W1] <title> — <url> (as of <date> | date unknown)` then the page content.
        """
        match citation:
            case FilingCitation(citation_id=cid, passage=passage):
                details = f"(passage_id {passage.passage_id}, {passage.kind.value})"
                return f"[{cid}] {_filing_locator(passage)} {details}\n{passage.content}"
            case WebCitation(citation_id=cid, result=result):
                return f"[{cid}] {_web_locator(result)}\n{result.content}"

    def source_line(self, citation: Citation) -> str:
        """Render a registered source as one entry of the Sources list (without its number).

        Filing: `10-K FY<year> — <Section Path>, p. <n>`.
        Web: `<title> — <url> (as of <date> | date unknown)`.
        """
        match citation:
            case FilingCitation(passage=passage):
                page = _page_text(passage)
                where = passage.section_path_text or passage.item
                return f"{self._filing_label} — {where}" + (f", {page}" if page else "")
            case WebCitation(result=result):
                return _web_locator(result)


def _filing_locator(passage: Passage) -> str:
    page = _page_text(passage)
    where = passage.section_path_text or passage.item
    return f"{where} — {page}" if page else where


def _page_text(passage: Passage) -> str:
    """`p. <n>`, marked `(approx.)` when inferred; empty for an unnumbered page."""
    if passage.page is None:
        return ""
    return f"p. {passage.page}" + (" (approx.)" if passage.page_approximate else "")


def _web_locator(result: WebResult) -> str:
    date = f"as of {result.published_date}" if result.published_date else "date unknown"
    title = f"{result.title} — " if result.title else ""
    return f"{title}{result.url} ({date})"
