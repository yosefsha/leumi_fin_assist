"""The web-search port: what the agent needs from a web search provider.

Business logic depends on `WebSearchClient` only; a provider (Tavily) implements
it in its own module and is injected where the agent is wired together.
"""

from typing import Protocol

from utils.web_result import WebResult


class WebSearchError(Exception):
    """The search could not be completed. The message is a short, key-free reason."""


class WebSearchTimeoutError(WebSearchError):
    """The provider did not answer in time; the same search may succeed if retried."""


class WebSearchClient(Protocol):
    """Searches the web for pages relevant to a query."""

    def search(self, query: str) -> list[WebResult]:
        """Return the most relevant pages for `query`, best first (possibly none).

        Raises `WebSearchTimeoutError` when the provider times out and
        `WebSearchError` for any other failure (rejected key, rate limit, server
        or network error, malformed response).
        """
        ...
