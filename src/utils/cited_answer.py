"""Validate the citation markers in a final answer and render its Sources list."""

import logging
import re
from dataclasses import dataclass

from utils.citation_format import CitationFormatter
from utils.citations import FILING_PREFIX, WEB_PREFIX, CitationRegistry

logger = logging.getLogger(__name__)

_ID = rf"[{FILING_PREFIX}{WEB_PREFIX}]\d+"
# `[F1]`, or a group the model wrote as `[F1, W2]`; leading spaces are captured so
# a marker that is dropped entirely does not leave a gap before the punctuation.
_MARKER = re.compile(rf"(?P<lead>[ \t]*)\[\s*(?P<ids>{_ID}(?:\s*[,;]\s*{_ID})*)\s*\]")
_ID_IN_GROUP = re.compile(_ID)


@dataclass(frozen=True)
class CitedAnswer:
    """A final answer whose markers are `[1]…` and whose sources are all registered.

    `sources[i]` is the source cited as `[i + 1]`.
    """

    body: str
    sources: tuple[str, ...]

    @property
    def text(self) -> str:
        """The body followed by a numbered Sources list (omitted when nothing is cited)."""
        if not self.sources:
            return self.body
        listing = "\n".join(f"[{n}] {source}" for n, source in enumerate(self.sources, 1))
        return f"{self.body}\n\nSources:\n{listing}"


class CitationResolver:
    """Turns the model's `[F#]` / `[W#]` markers into `[1]…` backed by the registry.

    Markers whose ID the registry does not hold are dropped with a warning, so an
    answer can only cite sources a tool actually returned. The rest are renumbered
    by first appearance; a source cited twice keeps its first number.
    """

    def __init__(self, formatter: CitationFormatter) -> None:
        self._formatter = formatter

    def resolve(self, answer: str, registry: CitationRegistry) -> CitedAnswer:
        """Return `answer` with validated, renumbered markers and its Sources list."""
        numbers: dict[str, int] = {}
        sources: list[str] = []
        unknown: list[str] = []

        def renumber(match: re.Match[str]) -> str:
            rendered: list[str] = []
            for citation_id in _ID_IN_GROUP.findall(match["ids"]):
                citation = registry.get(citation_id)
                if citation is None:
                    if citation_id not in unknown:
                        unknown.append(citation_id)
                    continue
                if citation_id not in numbers:
                    sources.append(self._formatter.source_line(citation))
                    numbers[citation_id] = len(sources)
                marker = f"[{numbers[citation_id]}]"
                if marker not in rendered:
                    rendered.append(marker)
            return match["lead"] + "".join(rendered) if rendered else ""

        body = _MARKER.sub(renumber, answer)
        if unknown:
            logger.warning(
                "Dropped citation markers with no registered source: %s", ", ".join(unknown)
            )
        return CitedAnswer(body=body, sources=tuple(sources))
