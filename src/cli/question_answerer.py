"""What the CLI needs from the agent: answer one question at a time."""

from typing import Protocol

from utils.agent_result import AgentResult


class QuestionAnswerer(Protocol):
    """Answers a question with a cited result (`ResearchAgent` implements it).

    Raises `ChatModelError` when the model cannot be reached or gives no usable reply.
    """

    def answer(self, question: str) -> AgentResult: ...
