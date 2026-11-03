"""The web-search port: what the agent needs from a web search provider.

Business logic depends on `WebSearchClient` only; a provider (Tavily) implements
it in its own module and is injected where the agent is wired together.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WebSearchResult:
    """One web page returned for a query: its URL, title, an excerpt and its date.

    `published_date` is the date as the provider reports it, or `None` when the
    source gives none.
    """

    url: str
    title: str
    content: str
    published_date: str | None


class WebSearchError(Exception):
    """The search could not be completed. The message is a short, key-free reason."""


class WebSearchTimeoutError(WebSearchError):
    """The provider did not answer in time; the same search may succeed if retried."""


class WebSearchClient(Protocol):
    """Searches the web for pages relevant to a query."""

    def search(self, query: str) -> list[WebSearchResult]:
        """Return the most relevant pages for `query`, best first (possibly none).

        Raises `WebSearchTimeoutError` when the provider times out and
        `WebSearchError` for any other failure (rejected key, rate limit, server
        or network error, malformed response).
        """
        ...
