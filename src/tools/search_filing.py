"""The `search_filing` tool: hybrid retrieval over the Filing, optionally within one Item."""

import json
import logging
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tools.argument_errors import invalid_arguments_output
from tools.passage_json import passage_to_json
from tools.registry import ToolOutput
from utils.embedder import EmbedderError
from utils.filing_items import parse_item_label, short_item_label, sorted_items
from utils.filing_search import FilingSearch, UnknownItemError
from utils.index_store import IndexStoreError
from utils.prompts import load_tool_description

logger = logging.getLogger(__name__)

TOOL_NAME = "search_filing"
MAX_QUERY_LENGTH = 500
MAX_TOP_K = 10
DEFAULT_TOP_K = 5


class SearchFilingArgs(BaseModel):
    """The arguments the model passes to `search_filing`."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, str_strip_whitespace=True)

    query: str = Field(
        min_length=1,
        max_length=MAX_QUERY_LENGTH,
        description=(
            'What to look for, in the Filing\'s own words, e.g. "research and development expense".'
        ),
    )
    item: str | None = Field(
        default=None,
        min_length=1,
        description=(
            'Limit the search to one Item of the 10-K, e.g. "1A" (Risk Factors), '
            '"7" (MD&A) or "8" (Financial Statements). Omit to search the whole Filing.'
        ),
    )
    top_k: int = Field(
        default=DEFAULT_TOP_K,
        ge=1,
        le=MAX_TOP_K,
        description="How many Passages to return, best first.",
    )


class SearchFilingTool:
    """Searches the Filing through an injected `FilingSearch` and returns whole Passages.

    Invalid arguments, an Item the Filing lacks, and a retrieval failure are
    error results. A search that finds nothing is a normal result that says so.
    """

    def __init__(self, search: FilingSearch) -> None:
        self._search = search
        self._description = load_tool_description(TOOL_NAME)
        self._input_schema: dict[str, Any] = SearchFilingArgs.model_json_schema()

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
        """Search for `args["query"]`, within `args["item"]` if given; return Passages as JSON."""
        try:
            request = SearchFilingArgs.model_validate(args)
        except ValidationError as error:
            return invalid_arguments_output(TOOL_NAME, error)

        item = None if request.item is None else self._item_name(request.item)
        try:
            hits = self._search.search(request.query, limit=request.top_k, item=item)
        except UnknownItemError:
            return ToolOutput(content=self._unknown_item_message(request.item or ""), is_error=True)
        except (EmbedderError, IndexStoreError) as error:
            logger.warning("search_filing failed for query %r: %s", request.query, error)
            return ToolOutput(content=f"Filing search failed: {error}", is_error=True)

        result: dict[str, Any] = {
            "query": request.query,
            "item": item,
            "passages": [passage_to_json(hit.passage) for hit in hits],
        }
        if not hits:
            scope = f"in {item}" if item else "in the Filing"
            result["message"] = f"No matching passages {scope} for {request.query!r}."
        return ToolOutput(content=json.dumps(result, ensure_ascii=False))

    def _item_name(self, raw: str) -> str:
        """The Filing's name for the Item `raw` denotes (`"1a"` -> `"Item 1A"`).

        A name the Filing does not have is returned as normalised, for the search
        to reject with `UnknownItemError`.
        """
        candidate = parse_item_label(raw) or raw
        folded = candidate.casefold()
        return next((item for item in self._search.items if item.casefold() == folded), candidate)

    def _unknown_item_message(self, raw: str) -> str:
        labels = (short_item_label(item) for item in sorted_items(self._search.items))
        valid = ", ".join(f'"{label}"' for label in labels)
        return f"Unknown item {raw!r}. Valid items: {valid}."
