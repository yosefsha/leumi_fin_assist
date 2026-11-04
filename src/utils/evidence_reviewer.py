"""The evidence check: one structured-output call that judges a draft answer's evidence (#29)."""

import logging
from collections.abc import Sequence
from datetime import date

from pydantic import ValidationError

from utils.agent_result import EvidenceCheck
from utils.chat_model import ChatModel, ChatModelError
from utils.evidence_review import EvidenceReview
from utils.plan import Plan
from utils.prompts import render_prompt
from utils.tool_evidence import ToolEvidence

logger = logging.getLogger(__name__)

EVIDENCE_CHECK_PROMPT = "evidence_check_prompt"
NO_EVIDENCE = "(no tool calls were made)"


class EvidenceReviewer:
    """Asks the model whether the evidence gathered so far supports the draft answer.

    The reply is constrained to `EvidenceReview.json_schema` (structured outputs).
    The check is advisory: any failure - a failed API call, a refusal, a reply cut
    off before its JSON is complete, or a reply that fails validation - yields an
    `EvidenceCheck` with no review and a warning, so the draft answer stands.
    """

    def __init__(self, model: ChatModel, fiscal_year: int, company: str) -> None:
        self._model = model
        self._fiscal_year = fiscal_year
        self._company = company

    def review(
        self,
        question: str,
        plan: Plan,
        evidence: Sequence[ToolEvidence],
        draft_answer: str,
        tool_names: Sequence[str],
        today: date,
    ) -> EvidenceCheck:
        """Return the check of `draft_answer` to `question` against `evidence`."""
        system = render_prompt(
            EVIDENCE_CHECK_PROMPT,
            {
                "company": self._company,
                "fiscal_year": str(self._fiscal_year),
                "today": today.isoformat(),
                "tools": ", ".join(tool_names),
            },
        )
        prompt = _review_request(question, plan, evidence, draft_answer)
        try:
            raw = self._model.generate_json(system, prompt, EvidenceReview.json_schema())
            return EvidenceCheck(review=EvidenceReview.model_validate_json(raw))
        except ChatModelError as error:
            logger.warning("Evidence check failed; keeping the draft answer: %s", error)
        except ValidationError as error:
            logger.warning("Evidence check gave an invalid review; keeping the draft: %s", error)
        return EvidenceCheck(review=None)


def _review_request(
    question: str, plan: Plan, evidence: Sequence[ToolEvidence], draft_answer: str
) -> str:
    """The user turn: the question, the plan, every tool call with its result, and the draft."""
    plan_text = plan.numbered() if plan.steps else "(no plan)"
    evidence_text = "\n\n".join(item.render() for item in evidence) or NO_EVIDENCE
    return (
        f"<question>\n{question}\n</question>\n\n"
        f"<plan>\n{plan_text}\n</plan>\n\n"
        f"<evidence>\n{evidence_text}\n</evidence>\n\n"
        f"<draft_answer>\n{draft_answer}\n</draft_answer>"
    )
