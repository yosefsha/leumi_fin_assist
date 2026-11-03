"""The `calculate` tool (issue #7, PR #18): exact arithmetic; every attack is an error result."""

import json
from typing import Any

import pytest

from tools.calculator import CalculateTool


@pytest.fixture(scope="module")
def calculate() -> CalculateTool:
    return CalculateTool()


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("34550 / 416161 * 100", 8.302075398703867),
        ("31370 / 391035 * 100", 8.022299794136075),
        ("round(34550 / 416161 * 100, 2)", 8.3),
        ("abs(-5) + 2 ** 10 % 7", 7),
        ("-(3 - 10) * 1.5", 10.5),
    ],
)
def test_evaluates_arithmetic(calculate: CalculateTool, expression: str, expected: float) -> None:
    output = calculate.run({"expression": expression})
    assert not output.is_error
    assert json.loads(output.content) == {
        "expression": expression,
        "result": pytest.approx(expected),
    }


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "(1).__class__",
        "().__class__.__bases__",
        "eval('1')",
        "9**9**9",
        "10 ** 22",
        "1/0",
        "5 % 0",
        "0 ** -1",
        "(-8) ** 0.5",
        "x + 1",
        "round(1.234, 999999)",
        "416,161 / 2",
        "lambda: 1",
        "import os",
    ],
)
def test_rejects_unsafe_or_invalid_expressions(calculate: CalculateTool, expression: str) -> None:
    output = calculate.run({"expression": expression})
    assert output.is_error
    assert "result" not in output.content


@pytest.mark.parametrize(
    "args",
    [{}, {"expression": 5}, {"expression": ""}, {"expression": "1", "x": 1}, {"expr": "1"}],
    ids=["missing", "not-a-string", "empty", "extra-key", "wrong-name"],
)
def test_invalid_arguments_are_an_error_result(
    calculate: CalculateTool, args: dict[str, Any]
) -> None:
    output = calculate.run(args)
    assert output.is_error
    assert output.content.startswith("Invalid arguments:")
