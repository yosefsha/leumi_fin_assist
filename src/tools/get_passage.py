"""The `get_passage` tool: follow a cross-reference such as `Note 5` to the Filing's text."""

import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tools.passage_json import passage_outline_json, passage_to_json
from tools.registry import ToolOutput
from utils.cross_reference_resolver import CrossReferenceResolver, UnknownReferenceError
from utils.prompts import load_tool_description

TOOL_NAME = "get_passage"
MAX_REFERENCE_LENGTH = 100


class GetPassageArgs(BaseModel):
    """The arguments the model passes to `get_passage`."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, str_strip_whitespace=True)

    reference: str = Field(
        min_length=1,
        max_length=MAX_REFERENCE_LENGTH,
        description=(
            'The cross-reference to follow: "Note 5", "Item 1A", "Part II, Item 7", '
            'or a passage_id such as "item-8-021".'
        ),
    )


class GetPassageTool:
    """Resolves a cross-reference to its Passage through an injected `CrossReferenceResolver`.

    Returns the Passage and an outline of the Passages nested under it (a Note's
    tables, an Item's subsections). An unresolvable reference is an error result
    that lists the accepted forms.
    """

    def __init__(self, resolver: CrossReferenceResolver) -> None:
        self._resolver = resolver
        self._description = load_tool_description(TOOL_NAME)
        self._input_schema: dict[str, Any] = GetPassageArgs.model_json_schema()

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
        """Resolve `args["reference"]`; return the Passage and its related Passages as JSON."""
        try:
            reference = GetPassageArgs.model_validate(args).reference
        except ValidationError as error:
            problems = "; ".join(
                f"{'.'.join(str(part) for part in issue['loc']) or 'arguments'}: {issue['msg']}"
                for issue in error.errors()
            )
            return ToolOutput(content=f"Invalid get_passage arguments: {problems}.", is_error=True)

        try:
            resolved = self._resolver.resolve(reference)
        except UnknownReferenceError as error:
            return ToolOutput(content=str(error), is_error=True)

        result = {
            "reference": reference,
            "passage": passage_to_json(resolved.passage),
            "related": [passage_outline_json(passage) for passage in resolved.related],
        }
        return ToolOutput(content=json.dumps(result, ensure_ascii=False, indent=2))
