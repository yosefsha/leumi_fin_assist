"""The `web_search` tool: current or external information the Filing does not hold."""

import json
import logging
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tools.argument_errors import invalid_arguments_output
from tools.registry import ToolOutput
from utils.prompts import load_tool_description
from utils.web_search import WebSearchClient, WebSearchError, WebSearchResult, WebSearchTimeoutError

logger = logging.getLogger(__name__)

TOOL_NAME = "web_search"
# Tavily rejects queries longer than 400 characters.
MAX_QUERY_LENGTH = 400


class WebSearchArgs(BaseModel):
    """The arguments the model passes to `web_search`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(
        min_length=1,
        max_length=MAX_QUERY_LENGTH,
        description=(
            "A specific search query naming the company, the metric and the period, "
            'e.g. "Microsoft gross margin latest quarter".'
        ),
    )


class WebSearchTool:
    """Searches the web through an injected `WebSearchClient`.

    A timed-out search is retried once. Every failure - invalid arguments, a
    second timeout or any other provider error, or no results - is returned as
    an error `ToolOutput` with a short reason; no exception reaches the agent.
    """

    def __init__(self, client: WebSearchClient) -> None:
        self._client = client
        self._description = load_tool_description(TOOL_NAME)
        self._input_schema: dict[str, Any] = WebSearchArgs.model_json_schema()

    @property
    def name(self) -> str:
        return TOOL_NAME

    @property
    def description(self) -> str:
        return self._description

    @property
    def input_schema(self) -> Mapping[str, Any]:
        return self._input_schema

    def run(self, args: Mapping[str, Any]) -> ToolOutput:
        """Search for `args["query"]` and return the results as JSON."""
        try:
            query = WebSearchArgs.model_validate(args).query
        except ValidationError as error:
            return invalid_arguments_output(TOOL_NAME, error)

        try:
            results = self._search_with_retry(query)
        except WebSearchError as error:
            logger.warning("web_search failed for query %r: %s", query, error)
            return ToolOutput(content=f"Web search failed: {error}", is_error=True)

        if not results:
            return ToolOutput(content=f"No web results found for {query!r}.", is_error=True)
        return ToolOutput(content=_to_json(query, results))

    def _search_with_retry(self, query: str) -> list[WebSearchResult]:
        """Run the search, retrying exactly once if the first attempt times out."""
        try:
            return self._client.search(query)
        except WebSearchTimeoutError as error:
            logger.info("web_search timed out for query %r (%s); retrying once.", query, error)
        return self._client.search(query)


def _to_json(query: str, results: list[WebSearchResult]) -> str:
    return json.dumps(
        {
            "query": query,
            "results": [asdict(result) for result in results],
        },
        ensure_ascii=False,
        indent=2,
    )
