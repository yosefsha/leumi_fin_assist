"""In-memory `WebSearchClient` fake: answers each search with the next scripted outcome."""

from collections.abc import Iterable

from utils.web_result import WebResult
from utils.web_search import WebSearchError

type Outcome = list[WebResult] | WebSearchError


class ScriptedWebSearchClient:
    """Returns (or raises) the scripted outcomes in order and records every query.

    Running out of outcomes is a test bug, so it raises `AssertionError` rather
    than a `WebSearchError` the tool would turn into an error result.
    """

    def __init__(self, outcomes: Iterable[Outcome]) -> None:
        self._outcomes = list(outcomes)
        self.queries: list[str] = []

    def search(self, query: str) -> list[WebResult]:
        self.queries.append(query)
        if not self._outcomes:
            raise AssertionError(f"Unexpected extra search for {query!r}.")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, WebSearchError):
            raise outcome
        return outcome
