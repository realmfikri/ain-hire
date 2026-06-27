import json

import pytest
from pydantic import ValidationError

from ioh_hire.schema import (
    COMPETENCY_NAMES,
    CompetencyScore,
    InterviewResult,
    Recommendation,
    recommendation_from_scores,
)


def _competencies(score: int = 4):
    return [
        CompetencyScore(
            name=name,
            score=score,
            rationale=f"Rationale for {name}",
            evidence_quotes=[f"Evidence for {name}"],
        )
        for name in COMPETENCY_NAMES
    ]


def test_interview_result_parses_valid_json():
    payload = {
        "session_id": "sess_123",
        "candidate_id": "cand_123",
        "role": "direct_sales_xlsatu",
        "competencies": [item.model_dump() for item in _competencies()],
        "knockout_flags": [],
        "recommendation": "PASS",
        "ranking_score": 76,
        "confidence": "high",
        "summary_id": "Kandidat kuat dan layak lanjut.",
        "recommended_next_step": "Lanjut interview manusia.",
        "interview_duration_sec": 612,
        "language_clarity_note": "Dialek tidak dipenalti.",
    }

    result = InterviewResult.model_validate_json(json.dumps(payload))

    assert result.recommendation == Recommendation.PASS
    assert result.competencies[0].evidence_quotes


def test_score_bounds_are_validated():
    with pytest.raises(ValidationError):
        CompetencyScore(
            name="Komunikasi & kejelasan",
            score=6,
            rationale="too high",
            evidence_quotes=["quote"],
        )


def test_scored_competency_requires_evidence_quote():
    with pytest.raises(ValidationError):
        CompetencyScore(
            name="Komunikasi & kejelasan",
            score=3,
            rationale="understandable",
            evidence_quotes=[],
        )


def test_knockout_score_requires_do_not_proceed():
    competencies = _competencies()
    competencies[0] = CompetencyScore(
        name="Komunikasi & kejelasan",
        score=1,
        rationale="Tidak bisa dipahami.",
        evidence_quotes=["..."],
    )
    with pytest.raises(ValidationError):
        InterviewResult(
            session_id="sess_123",
            candidate_id="cand_123",
            competencies=competencies,
            recommendation=Recommendation.PASS,
            ranking_score=20,
            confidence="medium",
            summary_id="Tidak lanjut.",
            recommended_next_step="Human sign-off.",
            interview_duration_sec=500,
        )


def test_recommendation_from_integrity_breach_forces_knockout():
    competencies = _competencies()
    competencies[-1] = CompetencyScore(
        name="Integritas",
        score=1,
        rationale="Overpromise.",
        evidence_quotes=["Dijamin kenceng terus di mana saja."],
    )

    recommendation, flags, ranking_score = recommendation_from_scores(competencies)

    assert recommendation == Recommendation.DO_NOT_PROCEED
    assert "integrity_breach" in flags
    assert ranking_score > 0
