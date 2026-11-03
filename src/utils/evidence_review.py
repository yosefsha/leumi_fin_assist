"""The evidence check's verdict on a draft answer: sufficient, or the gaps to close (#29)."""

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GapProblem(StrEnum):
    """Why the gathered evidence does not support part of the answer."""

    MISSING = "missing"
    SEGMENT_NOT_COMPANY_WIDE = "segment_not_company_wide"
    SECONDARY_SOURCE = "secondary_source"
    UNDATED_OR_STALE = "undated_or_stale"
    PERIOD_MISMATCH = "period_mismatch"
    OTHER = "other"


class Gap(BaseModel):
    """One requirement of the question the evidence does not meet, and how to look again."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    requirement: str = Field(min_length=1)
    problem: GapProblem
    retry_guidance: str = Field(min_length=1)


class EvidenceReview(BaseModel):
    """Whether the evidence supports a complete answer; when it does not, the gaps.

    `sufficient` and `gaps` must agree: a sufficient review lists no gaps, and an
    insufficient one lists at least one, so a caller never has to guess which wins.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    gaps: tuple[Gap, ...] = ()
    sufficient: bool

    @model_validator(mode="after")
    def _verdict_matches_gaps(self) -> Self:
        if self.sufficient == bool(self.gaps):
            raise ValueError(
                "A sufficient review lists no gaps; an insufficient one lists at least one."
            )
        return self

    @staticmethod
    def json_schema() -> dict[str, Any]:
        """The structured-output schema for an EvidenceReview (gaps first, then the verdict)."""
        return {
            "type": "object",
            "properties": {
                "gaps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "requirement": {"type": "string"},
                            "problem": {"type": "string", "enum": [p.value for p in GapProblem]},
                            "retry_guidance": {"type": "string"},
                        },
                        "required": ["requirement", "problem", "retry_guidance"],
                        "additionalProperties": False,
                    },
                },
                "sufficient": {"type": "boolean"},
            },
            "required": ["gaps", "sufficient"],
            "additionalProperties": False,
        }
