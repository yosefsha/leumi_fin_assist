"""How a tool reports model-supplied arguments that fail validation."""

from pydantic import ValidationError

from tools.registry import ToolOutput


def invalid_arguments_output(tool_name: str, error: ValidationError) -> ToolOutput:
    """An error result naming each invalid argument and what is wrong with it."""
    problems = "; ".join(
        f"{'.'.join(str(part) for part in issue['loc']) or 'arguments'}: {issue['msg']}"
        for issue in error.errors()
    )
    return ToolOutput(content=f"Invalid {tool_name} arguments: {problems}.", is_error=True)
