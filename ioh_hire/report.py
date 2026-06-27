"""Minimal recruiter scorecard PDF generation."""

from __future__ import annotations

import textwrap

from ioh_hire.interview.state_machine import TranscriptTurn
from ioh_hire.schema import InterviewResult


def build_scorecard_pdf(result: InterviewResult, transcript: list[TranscriptTurn]) -> bytes:
    lines = [
        "IOH AI Interviewer - Recruiter Scorecard",
        f"Session: {result.session_id}",
        f"Candidate: {result.candidate_id}",
        f"Recommendation: {result.recommendation.value}",
        f"Ranking score: {result.ranking_score}",
        f"Confidence: {result.confidence}",
        "",
        "Summary",
        result.summary_id,
        "",
        "Recommended next step",
        result.recommended_next_step,
        "",
        "Competencies",
    ]
    for item in result.competencies:
        score = "insufficient" if item.insufficient_evidence else str(item.score)
        lines.append(f"- {item.name}: {score}")
        lines.append(f"  Rationale: {item.rationale}")
        for quote in item.evidence_quotes[:2]:
            lines.append(f"  Evidence: \"{quote}\"")

    lines.extend(["", "Transcript"])
    for turn in transcript:
        lines.append(f"{turn.turn_index}. {turn.speaker}: {turn.text}")

    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, width=96) or [""])
    return _render_pdf(wrapped[:90])


def _render_pdf(lines: list[str]) -> bytes:
    y_start = 790
    line_height = 12
    content_lines = ["BT", "/F1 9 Tf", f"50 {y_start} Td"]
    for index, line in enumerate(lines):
        if index:
            content_lines.append(f"0 -{line_height} Td")
        content_lines.append(f"({_pdf_escape(line)}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            "trailer\n"
            f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_offset}\n"
            "%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
