"""One-line descriptions of tool calls for the live trace, e.g. `search_filing(item="1A") "…"`."""

import json
from collections.abc import Callable, Mapping
from typing import Any

from utils.agent_result import ToolCallRecord

MAX_TEXT_LENGTH = 120
MAX_ERROR_LENGTH = 200

type CallFormatter = Callable[[ToolCallRecord], str]


def describe_call(record: ToolCallRecord) -> str:
    """The call as the trace shows it: the tool, its scoping arguments, and its main text."""
    return _FORMATTERS.get(record.name, _generic)(record)


def describe_outcome(record: ToolCallRecord) -> str:
    """The trace line for a finished call: `[Tool: …]`, or `[Tool error: … — reason]`."""
    if record.is_error:
        reason = _one_line(record.output, MAX_ERROR_LENGTH)
        return f"[Tool error: {describe_call(record)} — {reason}]"
    result_line = _RESULT_LINES.get(record.name)
    if result_line is not None:
        return f"[Tool: {record.name}] {result_line(record)}"
    return f"[Tool: {describe_call(record)}]"


def _search_filing(record: ToolCallRecord) -> str:
    item = record.args.get("item")
    scope = f"(item={_quoted(item)})" if item else ""
    return f"search_filing{scope} {_quoted(record.args.get('query', ''))}"


def _text_arg(name: str) -> CallFormatter:
    """A tool described by one text argument, e.g. `web_search "<company> gross margin"`."""
    return lambda record: f"{record.name} {_quoted(record.args.get(name, ''))}"


def _generic(record: ToolCallRecord) -> str:
    args = ", ".join(f"{key}={_compact(value)}" for key, value in record.args.items())
    return f"{record.name}({args})"


def _calculation(record: ToolCallRecord) -> str:
    """`expression = result` from the `calculate` output; the raw output if it is not that JSON."""
    try:
        data = json.loads(record.output)
        return f"{data['expression']} = {data['result']}"
    except (ValueError, TypeError, KeyError):
        return _one_line(record.output, MAX_TEXT_LENGTH)


def _quoted(value: Any) -> str:
    return json.dumps(_one_line(str(value), MAX_TEXT_LENGTH), ensure_ascii=False)


def _compact(value: Any) -> str:
    return _one_line(json.dumps(value, ensure_ascii=False, default=str), MAX_TEXT_LENGTH)


def _one_line(text: str, limit: int) -> str:
    """`text` with its whitespace collapsed, cut to `limit` characters with an ellipsis."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


_FORMATTERS: Mapping[str, CallFormatter] = {
    "search_filing": _search_filing,
    "get_passage": _text_arg("reference"),
    "web_search": _text_arg("query"),
    "calculate": _text_arg("expression"),
}

# Tools whose result is worth showing in the trace, as `[Tool: <name>] <result>`.
_RESULT_LINES: Mapping[str, CallFormatter] = {"calculate": _calculation}
