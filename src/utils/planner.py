"""The planning call: one structured-output request that returns a Plan (Bonus 3)."""

import logging
from collections.abc import Sequence
from datetime import date

from anthropic.types import ToolParam
from pydantic import ValidationError

from utils.chat_model import ChatModel, ChatModelRefusalError
from utils.plan import Plan
from utils.prompts import render_prompt

logger = logging.getLogger(__name__)

PLANNER_PROMPT = "planner_prompt"


class Planner:
    """Asks the model for a Plan before any tool runs.

    The reply is constrained to `Plan.json_schema` (structured outputs), so each
    step names a registered tool. A model refusal or a reply that still fails
    validation yields an empty Plan with a warning: the plan is guidance, and the
    executor can answer without it. A failed API call propagates as `ChatModelError`.
    """

    def __init__(self, model: ChatModel, fiscal_year: int) -> None:
        self._model = model
        self._fiscal_year = fiscal_year

    def plan(self, question: str, tools: Sequence[ToolParam], today: date) -> Plan:
        """Return the Plan for `question` over `tools`."""
        tool_list = "\n\n".join(
            f"### {tool['name']}\n{tool.get('description', '')}" for tool in tools
        )
        system = render_prompt(
            PLANNER_PROMPT,
            {"fiscal_year": str(self._fiscal_year), "today": today.isoformat(), "tools": tool_list},
        )
        schema = Plan.json_schema([tool["name"] for tool in tools])
        try:
            raw = self._model.generate_json(system, question, schema)
            return Plan.model_validate_json(raw)
        except ChatModelRefusalError as error:
            logger.warning("Planner declined; continuing without a plan: %s", error)
        except ValidationError as error:
            logger.warning("Planner returned an invalid plan; continuing without one: %s", error)
        return Plan()
