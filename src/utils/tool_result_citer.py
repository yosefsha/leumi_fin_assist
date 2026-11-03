"""Give a tool result's sources their citation IDs before the model sees them."""

from dataclasses import dataclass

from tools.registry import Source, ToolOutput
from utils.citation_format import CitationFormatter
from utils.citations import Citation, CitationRegistry
from utils.passage import Passage
from utils.web_result import WebResult

SHOWN_ABOVE = "(content shown above)"


@dataclass(frozen=True)
class CitedToolResult:
    """A tool result as the model sees it, and the citation IDs it introduced."""

    content: str
    citation_ids: tuple[str, ...]


class ToolResultCiter:
    """Registers each source of a `ToolOutput` and renders it under its ID.

    The model-facing text is the tool's own `content` followed by one block per
    source, headed `[F#]` for a Filing Passage or `[W#]` for a web result. A
    source seen earlier in the same query keeps its ID and is shown as its header
    line only, marked as shown above, so repeated searches do not resend the same
    content. Results without sources (calculate, errors) pass through unchanged.
    """

    def __init__(self, formatter: CitationFormatter) -> None:
        self._formatter = formatter

    def cite(self, output: ToolOutput, registry: CitationRegistry) -> CitedToolResult:
        """Register `output.sources` in `registry`; return the text for the `tool_result`."""
        blocks = [output.content]
        citation_ids: list[str] = []
        for source in output.sources:
            known = len(registry)
            citation = _register(source, registry)
            citation_ids.append(citation.citation_id)
            if len(registry) > known:
                blocks.append(self._formatter.for_model(citation))
            else:
                blocks.append(f"{self._formatter.header_for_model(citation)} {SHOWN_ABOVE}")
        return CitedToolResult(
            content="\n\n".join(block for block in blocks if block),
            citation_ids=tuple(citation_ids),
        )


def _register(source: Source, registry: CitationRegistry) -> Citation:
    match source:
        case Passage():
            return registry.register_passage(source)
        case WebResult():
            return registry.register_web_result(source)
