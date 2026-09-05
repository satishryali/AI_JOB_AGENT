"""Pydantic schemas for validated LLM responses."""

from pydantic import BaseModel, Field


class MatchScoreResponse(BaseModel):
    """Structured resume-match payload from the LLM."""

    score: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = ""
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)


class ApplyDecisionResponse(BaseModel):
    should_apply: bool
    reasoning: str = ""


class AnswersResponse(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


class TailoredResumeResponse(BaseModel):
    """Resume rewrite that must stay within provided facts."""

    summary: str = ""
    ordered_skills: list[str] = Field(default_factory=list)
    emphasized_experience: list[str] = Field(default_factory=list)
    notes: str = ""
