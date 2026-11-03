"""`WebSearchClient` implementation backed by the Tavily Search API."""

import requests
from pydantic import BaseModel, ValidationError
from tavily import TavilyClient
from tavily.errors import (
    BadRequestError,
    ForbiddenError,
    InvalidAPIKeyError,
    UsageLimitExceededError,
)
from tavily.errors import TimeoutError as TavilyTimeoutError

from utils.web_search import WebSearchError, WebSearchResult, WebSearchTimeoutError

# Fixed search parameters (issue #6): finance-tuned, deep search, five results,
# no Tavily-generated answer (the agent writes its own) and no domain allow-list.
_SEARCH_DEPTH = "advanced"
_TOPIC = "finance"
_MAX_RESULTS = 5
DEFAULT_TIMEOUT_SECONDS = 30.0


class _TavilyResult(BaseModel):
    """One entry of the Tavily `results` array; unknown fields are ignored."""

    url: str
    title: str = ""
    content: str = ""
    published_date: str | None = None


class _TavilyResponse(BaseModel):
    """The part of a Tavily search response the agent uses."""

    results: list[_TavilyResult]


class TavilyWebSearchClient:
    """Searches the web through Tavily.

    Every provider or transport failure is translated into a `WebSearchError`
    whose message is a short reason that never contains the API key.
    """

    def __init__(self, api_key: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        if not api_key.strip():
            raise ValueError("A Tavily API key is required.")
        if timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive; got {timeout_seconds}.")
        self._client = TavilyClient(api_key=api_key)
        self._timeout_seconds = timeout_seconds

    def search(self, query: str) -> list[WebSearchResult]:
        """Return up to five results for `query` (see `WebSearchClient.search`)."""
        try:
            raw = self._client.search(
                query,
                search_depth=_SEARCH_DEPTH,
                topic=_TOPIC,
                max_results=_MAX_RESULTS,
                include_answer=False,
                timeout=self._timeout_seconds,
            )
        except (TavilyTimeoutError, requests.Timeout) as error:
            raise WebSearchTimeoutError(
                f"Tavily did not respond within {self._timeout_seconds:g} seconds."
            ) from error
        except (InvalidAPIKeyError, ForbiddenError) as error:
            raise WebSearchError("Tavily rejected the API key (unauthorized).") from error
        except UsageLimitExceededError as error:
            raise WebSearchError("Tavily rate limit or usage quota exceeded.") from error
        except BadRequestError as error:
            detail = f": {error}" if str(error) else ""
            raise WebSearchError(f"Tavily rejected the request as invalid{detail}.") from error
        except requests.HTTPError as error:
            status = error.response.status_code if error.response is not None else "unknown"
            raise WebSearchError(f"Tavily returned HTTP {status}.") from error
        except requests.RequestException as error:
            raise WebSearchError(
                f"Network error talking to Tavily ({type(error).__name__})."
            ) from error

        try:
            response = _TavilyResponse.model_validate(raw)
        except ValidationError as error:
            raise WebSearchError("Tavily returned a response in an unexpected format.") from error
        return [
            WebSearchResult(
                url=result.url,
                title=result.title,
                content=result.content,
                published_date=result.published_date or None,
            )
            for result in response.results
        ]
