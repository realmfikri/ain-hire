"""Validated scoring schema for recruiter-facing interview results."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ain_hire.interview.content import ROLE_ID


class Recommendation(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    DO_NOT_PROCEED = "DO_NOT_PROCEED"


class CompetencyScore(BaseModel):
    name: str
    score: Optional[int] = Field(None, ge=1, le=5)
    insufficient_evidence: bool = False
    rationale: str
    evidence_quotes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_evidence_or_insufficient(self) -> "CompetencyScore":
        if self.insufficient_evidence:
            return self
        if self.score is None:
            raise ValueError("score is required unless insufficient_evidence is true")
        if not self.rationale.strip():
            raise ValueError("rationale is required")
        if not self.evidence_quotes:
            raise ValueError("evidence_quotes must not be empty when scored")
        return self

    @field_validator("evidence_quotes")
    @classmethod
    def trim_quotes(cls, value: list[str]) -> list[str]:
        return [quote.strip()[:240] for quote in value if quote.strip()]


class InterviewResult(BaseModel):
    session_id: str
    candidate_id: str
    role: str = ROLE_ID
    competencies: list[CompetencyScore]
    knockout_flags: list[str] = Field(default_factory=list)
    recommendation: Recommendation
    ranking_score: int = Field(..., ge=0, le=100)
    confidence: Literal["low", "medium", "high"]
    summary_id: str
    recommended_next_step: str
    interview_duration_sec: int
    language_clarity_note: Optional[str] = None

    @model_validator(mode="after")
    def enforce_knockouts(self) -> "InterviewResult":
        names = {_normalize_competency_name(score.name): score for score in self.competencies}
        communication = names.get(_normalize_competency_name("Komunikasi & kejelasan"))
        integrity = names.get(_normalize_competency_name("Integritas"))
        has_knockout_score = any(
            score is not None
            and score.score == 1
            and _normalize_competency_name(score.name)
            in {
                _normalize_competency_name("Komunikasi & kejelasan"),
                _normalize_competency_name("Integritas"),
            }
            for score in [communication, integrity]
        )
        if has_knockout_score and self.recommendation != Recommendation.DO_NOT_PROCEED:
            raise ValueError("knockout score requires DO_NOT_PROCEED recommendation")
        return self


KNOCKOUT_COMPETENCIES = {"Komunikasi & kejelasan", "Integritas"}

COMPETENCY_NAMES = [
    "Komunikasi & kejelasan",
    "Persuasi & framing benefit",
    "Ketahanan & komposur",
    "Discovery & empati",
    "Drive & orientasi target",
    "Coachability",
    "Integritas",
]

WEIGHTS = {
    "Komunikasi & kejelasan": 20,
    "Persuasi & framing benefit": 20,
    "Ketahanan & komposur": 20,
    "Discovery & empati": 15,
    "Drive & orientasi target": 15,
    "Coachability": 10,
}


def ranking_score_from_competencies(competencies: list[CompetencyScore]) -> int:
    """Compute the v0 weighted shortlist score, excluding integrity pass/fail."""

    by_name = {_normalize_competency_name(item.name): item for item in competencies}
    total_weight = sum(WEIGHTS.values())
    points = 0.0
    for name, weight in WEIGHTS.items():
        item = by_name.get(_normalize_competency_name(name))
        if item is None or item.score is None or item.insufficient_evidence:
            score = 2
        else:
            score = item.score
        points += ((score - 1) / 4) * weight
    return max(0, min(100, round((points / total_weight) * 100)))


def recommendation_from_scores(
    competencies: list[CompetencyScore], latency_flag: bool = False
) -> tuple[Recommendation, list[str], int]:
    by_name = {_normalize_competency_name(item.name): item for item in competencies}
    flags: list[str] = []

    communication = by_name.get(_normalize_competency_name("Komunikasi & kejelasan"))
    if communication and communication.score == 1:
        flags.append("communication_knockout")

    integrity = by_name.get(_normalize_competency_name("Integritas"))
    if integrity and integrity.score == 1:
        flags.append("integrity_breach")

    if latency_flag:
        flags.append("implausibly_fast_response")

    ranking_score = ranking_score_from_competencies(competencies)
    if flags and any(flag in flags for flag in ["communication_knockout", "integrity_breach"]):
        return Recommendation.DO_NOT_PROCEED, flags, ranking_score
    if latency_flag:
        return Recommendation.REVIEW, flags, ranking_score
    if ranking_score >= 70:
        return Recommendation.PASS, flags, ranking_score
    if ranking_score >= 45:
        return Recommendation.REVIEW, flags, ranking_score
    return Recommendation.DO_NOT_PROCEED, flags, ranking_score


def _normalize_competency_name(name: str) -> str:
    return name.strip().casefold()
