"""Safe evaluation of arithmetic expressions for the `calculate` tool.

The expression is parsed with `ast` and walked against an allow-list: numeric
literals, `+ - * / ** %`, unary `+`/`-`, parentheses, and calls to `round` and
`abs`. Anything else is rejected before any arithmetic runs. Nothing is ever
passed to `eval` or `exec`.

Every intermediate value is bounded, so a hostile expression cannot exhaust
CPU or memory: the source length, the exponent of `**`, the magnitude of every
value and the `ndigits` of `round` all have hard limits.
"""

import ast
import math
import operator
from collections.abc import Callable

type Number = int | float

MAX_EXPRESSION_LENGTH = 500
"""Longest accepted expression, in characters. Also bounds literal size and nesting depth."""

MAX_MAGNITUDE = 10**21
"""Largest absolute value any literal, intermediate or final result may have."""

MAX_EXPONENT = 64
"""Largest absolute value of the right-hand side of `**`."""

MAX_ROUND_DIGITS = 15
"""Largest absolute value of `round`'s `ndigits` argument."""

_BINARY_OPERATORS: dict[type[ast.operator], Callable[[Number, Number], Number]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[Number], Number]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_ALLOWED_SYNTAX = "numbers, + - * / ** %, unary minus, parentheses, round(x[, ndigits]) and abs(x)"


class InvalidExpressionError(ValueError):
    """The expression is not allowed arithmetic, or cannot be evaluated within the limits."""


def evaluate_arithmetic(expression: str) -> Number:
    """Evaluate an arithmetic `expression` and return its value.

    Raises `InvalidExpressionError` for anything outside the allow-list, a
    division by zero, or a value, exponent or `ndigits` beyond its limit.
    """
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise InvalidExpressionError(
            f"Expression is {len(expression)} characters; the limit is {MAX_EXPRESSION_LENGTH}."
        )
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, ValueError) as error:
        raise InvalidExpressionError(f"Not a valid arithmetic expression: {error}.") from error
    except (RecursionError, MemoryError) as error:
        raise InvalidExpressionError("Expression is nested too deeply.") from error
    try:
        return _evaluate(tree.body)
    except ZeroDivisionError as error:
        raise InvalidExpressionError("Division by zero.") from error
    except OverflowError as error:
        raise InvalidExpressionError(
            f"Result is too large; the limit is {MAX_MAGNITUDE:.0e} in absolute value."
        ) from error
    except RecursionError as error:
        raise InvalidExpressionError("Expression is nested too deeply.") from error


def _evaluate(node: ast.expr) -> Number:
    match node:
        case ast.Constant(value=value) if type(value) in (int, float):
            return _bounded(value)
        case ast.BinOp(left=left, op=op, right=right) if type(op) in _BINARY_OPERATORS:
            return _binary(op, _evaluate(left), _evaluate(right))
        case ast.UnaryOp(op=op, operand=operand) if type(op) in _UNARY_OPERATORS:
            return _UNARY_OPERATORS[type(op)](_evaluate(operand))
        case ast.Call(func=ast.Name(id="round"), args=args, keywords=[]):
            return _round(args)
        case ast.Call(func=ast.Name(id="abs"), args=[argument], keywords=[]):
            return abs(_evaluate(argument))
        case ast.Tuple():
            raise InvalidExpressionError(
                "Commas are not allowed: write numbers without thousands separators "
                "(416161, not 416,161)."
            )
        case _:
            raise InvalidExpressionError(
                f"Unsupported syntax {ast.unparse(node)!r}. Allowed: {_ALLOWED_SYNTAX}."
            )


def _binary(op: ast.operator, left: Number, right: Number) -> Number:
    if isinstance(op, ast.Pow) and abs(right) > MAX_EXPONENT:
        raise InvalidExpressionError(
            f"Exponent {right} is too large; the limit is {MAX_EXPONENT} in absolute value."
        )
    return _bounded(_BINARY_OPERATORS[type(op)](left, right))


def _round(args: list[ast.expr]) -> Number:
    match args:
        case [number]:
            return _bounded(round(_evaluate(number)))
        case [number, digits]:
            ndigits = _evaluate(digits)
            if not isinstance(ndigits, int) or abs(ndigits) > MAX_ROUND_DIGITS:
                raise InvalidExpressionError(
                    f"round's ndigits must be a whole number between {-MAX_ROUND_DIGITS} "
                    f"and {MAX_ROUND_DIGITS}."
                )
            return _bounded(round(_evaluate(number), ndigits))
        case _:
            raise InvalidExpressionError("round takes one or two arguments: round(x[, ndigits]).")


def _bounded(value: Number | complex) -> Number:
    """Return `value` if it is a finite real number within `MAX_MAGNITUDE`, else raise."""
    if isinstance(value, complex):
        # A negative base raised to a fractional power yields a complex number.
        raise InvalidExpressionError("Result is not a real number.")
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidExpressionError("Result is not a finite number.")
    if abs(value) > MAX_MAGNITUDE:
        raise InvalidExpressionError(
            f"Value is too large; the limit is {MAX_MAGNITUDE:.0e} in absolute value."
        )
    return value
