"""Scoring engines for the AIN Hire."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from ain_hire.config import Settings
from ain_hire.interview.content import PRODUCT_CONTEXT, ROLE_ID, ROLE_NAME, SCORING_RUBRIC
from ain_hire.interview.state_machine import TranscriptTurn
from ain_hire.schema import (
    COMPETENCY_NAMES,
    CompetencyScore,
    InterviewResult,
    recommendation_from_scores,
)


class ScoringEngine(Protocol):
    def score(
        self,
        session_id: str,
        candidate_id: str,
        transcript: list[TranscriptTurn],
        duration_sec: int,
        latency_flag: bool = False,
    ) -> InterviewResult:
        ...


@dataclass(frozen=True)
class GeminiScoringEngine:
    settings: Settings
    max_parse_attempts: int = 2

    def score(
        self,
        session_id: str,
        candidate_id: str,
        transcript: list[TranscriptTurn],
        duration_sec: int,
        latency_flag: bool = False,
    ) -> InterviewResult:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=self.settings.use_vertexai,
            project=self.settings.project_id,
            location=self.settings.scorer_model_location,
        )
        prompt = self._build_prompt(session_id, candidate_id, transcript, duration_sec)
        last_error = ""
        for attempt in range(self.max_parse_attempts):
            retry_suffix = (
                "\n\nRespons sebelumnya gagal divalidasi. Kembalikan hanya JSON valid "
                f"yang sesuai schema. Error: {last_error}"
                if last_error
                else ""
            )
            response = client.models.generate_content(
                model=self.settings.scorer_model,
                contents=prompt + retry_suffix,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            raw_text = response.text or ""
            try:
                data = json.loads(_extract_json(raw_text))
                competencies = [
                    CompetencyScore.model_validate(item)
                    for item in data.get("competencies", [])
                ]
                recommendation, flags, ranking_score = recommendation_from_scores(
                    competencies, latency_flag=latency_flag
                )
                data.update(
                    {
                        "session_id": session_id,
                        "candidate_id": candidate_id,
                        "role": ROLE_ID,
                        "competencies": competencies,
                        "recommendation": recommendation,
                        "knockout_flags": flags,
                        "ranking_score": ranking_score,
                        "interview_duration_sec": duration_sec,
                    }
                )
                return InterviewResult.model_validate(data)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = str(exc)
                if attempt == self.max_parse_attempts - 1:
                    raise

        raise RuntimeError("unreachable scoring retry state")

    def _build_prompt(
        self,
        session_id: str,
        candidate_id: str,
        transcript: list[TranscriptTurn],
        duration_sec: int,
    ) -> str:
        transcript_json = [
            {
                "turn_index": turn.turn_index,
                "speaker": turn.speaker,
                "text": turn.text,
                "latency_ms": turn.latency_ms,
            }
            for turn in transcript
        ]
        return f"""
Anda adalah scorer rekrutmen XLSmart untuk role {ROLE_NAME}. Anda BUKAN interviewer.
Nilai hanya berdasarkan transkrip. Jangan menebak gender, etnis, agama, umur,
daerah asal, atau atribut terlindungi lain. Jangan gunakan aksen, dialek,
code-switching, atau bahasa informal sebagai penalti; nilai hanya kejelasan.

Konteks produk:
{PRODUCT_CONTEXT}

Rubrik:
{SCORING_RUBRIC}

Aturan scoring:
- Output JSON saja.
- Semua kompetensi wajib muncul dengan nama persis:
  {", ".join(COMPETENCY_NAMES)}
- Sistem akan menghitung recommendation, ranking_score, dan knockout_flags
  secara deterministik; jangan mengambil keputusan aggregate sendiri. Isi field
  itu dengan placeholder: recommendation "REVIEW", ranking_score 0,
  knockout_flags [].
- evidence_quotes harus kutipan verbatim singkat dari transkrip kandidat.
- Jika bukti kurang, set score null dan insufficient_evidence true.
- confidence harus salah satu: "low", "medium", "high".
- summary_id berisi ringkasan singkat untuk rekruter.
- recommended_next_step berisi langkah berikutnya untuk rekruter.
- language_clarity_note berisi catatan deskriptif; jangan menilai aksen/dialek.

Struktur JSON wajib:
{{
  "session_id": "{session_id}",
  "candidate_id": "{candidate_id}",
  "role": "{ROLE_ID}",
  "competencies": [
    {{
      "name": "Komunikasi & kejelasan",
      "score": 1,
      "insufficient_evidence": false,
      "rationale": "Alasan singkat berbasis bukti.",
      "evidence_quotes": ["Kutipan kandidat."]
    }}
  ],
  "knockout_flags": [],
  "recommendation": "REVIEW",
  "ranking_score": 0,
  "confidence": "medium",
  "summary_id": "Ringkasan singkat.",
  "recommended_next_step": "Langkah berikutnya.",
  "interview_duration_sec": {duration_sec},
  "language_clarity_note": "Dialek, aksen, code-switching, dan gaya informal tidak dipenalti."
}}

session_id: {session_id}
candidate_id: {candidate_id}
role: {ROLE_ID}
interview_duration_sec: {duration_sec}

Transkrip JSON:
{json.dumps(transcript_json, ensure_ascii=False)}
"""


class HeuristicScoringEngine:
    """No-cost scorer for local demos and tests."""

    def score(
        self,
        session_id: str,
        candidate_id: str,
        transcript: list[TranscriptTurn],
        duration_sec: int,
        latency_flag: bool = False,
    ) -> InterviewResult:
        candidate_turns = [turn for turn in transcript if turn.speaker == "candidate"]
        all_candidate = " ".join(turn.text for turn in candidate_turns)
        lower = all_candidate.lower()
        roleplay_candidates = _candidate_turns_after(transcript, "simulasi")
        coach_turn = candidate_turns[-1].text if candidate_turns else ""

        competencies = [
            self._communication(candidate_turns),
            self._persuasion(candidate_turns, lower),
            self._resilience(candidate_turns, transcript, lower),
            self._discovery(candidate_turns, lower),
            self._drive(candidate_turns, lower),
            self._coachability(coach_turn),
            self._integrity(roleplay_candidates),
        ]
        recommendation, flags, ranking_score = recommendation_from_scores(
            competencies, latency_flag=latency_flag
        )
        insufficient = sum(1 for item in competencies if item.insufficient_evidence)
        confidence = "low" if insufficient >= 3 else "medium"
        if insufficient == 0 and len(candidate_turns) >= 6:
            confidence = "high"

        summary = self._summary(competencies, candidate_turns, flags)
        next_step = {
            "PASS": "Lanjutkan ke interview manusia dan validasi data administrasi.",
            "REVIEW": "Tinjau transkrip, audio, dan bukti sebelum menentukan follow-up.",
            "DO_NOT_PROCEED": "Perlu sign-off rekruter sebelum kandidat ditutup.",
        }[recommendation.value]

        return InterviewResult(
            session_id=session_id,
            candidate_id=candidate_id,
            competencies=competencies,
            knockout_flags=flags,
            recommendation=recommendation,
            ranking_score=ranking_score,
            confidence=confidence,  # type: ignore[arg-type]
            summary_id=summary,
            recommended_next_step=next_step,
            interview_duration_sec=duration_sec,
            language_clarity_note=(
                "Catatan ini deskriptif saja; dialek, aksen, dan gaya informal tidak dipenalti."
            ),
        )

    def _communication(self, turns: list[TranscriptTurn]) -> CompetencyScore:
        if not turns:
            return _insufficient("Komunikasi & kejelasan")
        avg_words = sum(len(turn.text.split()) for turn in turns) / len(turns)
        quote = _first_quote(turns)
        if avg_words < 5:
            score = 2
            rationale = "Jawaban terlalu singkat sehingga struktur komunikasi belum terlihat kuat."
        elif avg_words < 12:
            score = 3
            rationale = "Jawaban bisa dipahami, tetapi masih cenderung singkat atau umum."
        elif avg_words < 35:
            score = 4
            rationale = "Jawaban cukup jelas dan mudah diikuti untuk konteks sales lapangan."
        else:
            score = 3
            rationale = "Jawaban informatif, tetapi agak panjang sehingga bisa terasa bertele-tele."
        return CompetencyScore(
            name="Komunikasi & kejelasan",
            score=score,
            rationale=rationale,
            evidence_quotes=[quote],
        )

    def _persuasion(self, turns: list[TranscriptTurn], lower: str) -> CompetencyScore:
        if not turns:
            return _insufficient("Persuasi & framing benefit")
        benefit_terms = ["manfaat", "stabil", "lancar", "belajar", "nonton", "kerja", "keluarga", "buffering", "hemat", "lebih mudah"]
        product_terms = ["xl satu", "xlsatu", "internet", "wifi", "fiber"]
        score = 2
        if any(term in lower for term in product_terms):
            score = 3
        if any(term in lower for term in benefit_terms):
            score = 4
        if any(term in lower for term in ["anak", "keluarga", "kebutuhan ibu", "kebutuhan bapak", "rumah ibu", "rumah bapak"]):
            score = 5
        return CompetencyScore(
            name="Persuasi & framing benefit",
            score=score,
            rationale="Skor mencerminkan seberapa jauh kandidat mengaitkan produk dengan manfaat yang relevan untuk penghuni.",
            evidence_quotes=[_best_quote(turns, benefit_terms + product_terms)],
        )

    def _resilience(
        self,
        turns: list[TranscriptTurn],
        transcript: list[TranscriptTurn],
        lower: str,
    ) -> CompetencyScore:
        if not turns:
            return _insufficient("Ketahanan & komposur")
        persona_pushback = sum(1 for turn in transcript if turn.speaker == "persona")
        positive = any(term in lower for term in ["tetap", "coba lagi", "lanjut", "sabar", "tidak menyerah", "dengar", "baik"])
        score = 3
        if persona_pushback >= 2 and positive:
            score = 4
        if persona_pushback >= 3 and any(term in lower for term in ["cek dulu", "tidak apa", "saya pahami", "boleh saya bantu"]):
            score = 5
        return CompetencyScore(
            name="Ketahanan & komposur",
            score=score,
            rationale="Kandidat dinilai dari cara tetap tenang dan melanjutkan percakapan setelah keberatan penghuni.",
            evidence_quotes=[_best_quote(turns, ["tetap", "sabar", "cek dulu", "saya pahami", "boleh"])],
        )

    def _discovery(self, turns: list[TranscriptTurn], lower: str) -> CompetencyScore:
        if not turns:
            return _insufficient("Discovery & empati")
        discovery_terms = ["apa", "berapa", "kebutuhan", "kendala", "pakai", "sering", "alamat", "coverage", "boleh tahu"]
        question_count = sum(turn.text.count("?") for turn in turns)
        keyword_hit = sum(1 for term in discovery_terms if term in lower)
        score = 1 if question_count == 0 and keyword_hit < 2 else 3
        if question_count >= 2 or keyword_hit >= 4:
            score = 4
        if question_count >= 3 and any(term in lower for term in ["kebutuhan", "kendala", "berapa orang"]):
            score = 5
        return CompetencyScore(
            name="Discovery & empati",
            score=score,
            rationale="Skor melihat apakah kandidat bertanya dan menyesuaikan pitch, bukan hanya monolog.",
            evidence_quotes=[_best_quote(turns, discovery_terms)],
        )

    def _drive(self, turns: list[TranscriptTurn], lower: str) -> CompetencyScore:
        if not turns:
            return _insufficient("Drive & orientasi target")
        close_terms = ["daftar", "jadwal", "nomor", "kontak", "cek coverage", "cek alamat", "lanjut", "pasang", "follow up"]
        hits = sum(1 for term in close_terms if term in lower)
        score = 1 if hits == 0 else 3
        if hits >= 2:
            score = 4
        if hits >= 3:
            score = 5
        return CompetencyScore(
            name="Drive & orientasi target",
            score=score,
            rationale="Skor berdasarkan keberanian meminta langkah berikutnya yang konkret.",
            evidence_quotes=[_best_quote(turns, close_terms)],
        )

    def _coachability(self, coach_turn: str) -> CompetencyScore:
        if not coach_turn:
            return _insufficient("Coachability")
        lower = coach_turn.lower()
        applied = [
            any(term in lower for term in ["kebutuhan", "kendala", "pakai internet"]),
            any(term in lower for term in ["manfaat", "lancar", "stabil", "keluarga", "belajar", "nonton"]),
            any(term in lower for term in ["cek coverage", "jadwal", "daftar", "alamat", "nomor"]),
        ]
        score = 2 + sum(applied)
        return CompetencyScore(
            name="Coachability",
            score=max(1, min(5, score)),
            rationale="Skor melihat apakah kandidat menerapkan feedback: tanya kebutuhan, kaitkan manfaat, dan tutup dengan next step.",
            evidence_quotes=[coach_turn[:220]],
        )

    def _integrity(self, roleplay_turns: list[TranscriptTurn]) -> CompetencyScore:
        if not roleplay_turns:
            return _insufficient("Integritas")
        text = " ".join(turn.text for turn in roleplay_turns).lower()
        caveat_terms = ["cek", "tergantung", "sesuai alamat", "coverage", "belum bisa", "tidak bisa", "tidak menjamin", "pastikan dulu"]
        overpromise_terms = ["dijamin", "pasti kenceng", "pasti bisa", "gratis bulan pertama", "gratis selamanya", "di mana aja", "1gbps"]
        overpromise = any(term in text for term in overpromise_terms) and not any(
            caveat in text for caveat in caveat_terms
        )
        if overpromise:
            return CompetencyScore(
                name="Integritas",
                score=1,
                rationale="Kandidat terlihat membuat janji pasti soal coverage, kecepatan, atau promo tanpa verifikasi.",
                evidence_quotes=[_best_quote(roleplay_turns, overpromise_terms)],
            )
        score = 5 if any(term in text for term in caveat_terms) else 3
        return CompetencyScore(
            name="Integritas",
            score=score,
            rationale="Kandidat tidak memberi jaminan palsu dan mengarah ke pengecekan bila informasi belum pasti.",
            evidence_quotes=[_best_quote(roleplay_turns, caveat_terms)],
        )

    def _summary(
        self,
        competencies: list[CompetencyScore],
        turns: list[TranscriptTurn],
        flags: list[str],
    ) -> str:
        by_name = {item.name: item for item in competencies}
        top = sorted(
            [item for item in competencies if item.score is not None],
            key=lambda item: item.score or 0,
            reverse=True,
        )[:2]
        concern = sorted(
            [item for item in competencies if item.score is not None],
            key=lambda item: item.score or 0,
        )[0]
        if "integrity_breach" in flags:
            return (
                "Kandidat perlu ditinjau ketat karena ada indikasi overpromise pada simulasi. "
                "Rekruter perlu memverifikasi audio dan transkrip sebelum keputusan akhir."
            )
        strengths = ", ".join(item.name for item in top)
        return (
            f"Kandidat menunjukkan sinyal terkuat pada {strengths}. "
            f"Area yang perlu ditinjau adalah {concern.name}."
        )


def build_scoring_engine(settings: Settings) -> ScoringEngine:
    if settings.use_stubs:
        return HeuristicScoringEngine()
    return GeminiScoringEngine(settings=settings)


def has_implausibly_fast_answers(transcript: list[TranscriptTurn]) -> bool:
    for turn in transcript:
        if turn.speaker != "candidate" or turn.latency_ms is None:
            continue
        if turn.latency_ms < 1500 and len(turn.text.split()) >= 25:
            return True
    return False


def _extract_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model response")
    return stripped[start : end + 1]


def _insufficient(name: str) -> CompetencyScore:
    return CompetencyScore(
        name=name,
        score=None,
        insufficient_evidence=True,
        rationale="Bukti transkrip tidak cukup untuk menilai kompetensi ini.",
        evidence_quotes=[],
    )


def _first_quote(turns: list[TranscriptTurn]) -> str:
    return next((turn.text[:220] for turn in turns if turn.text.strip()), "Tidak ada kutipan.")


def _best_quote(turns: list[TranscriptTurn], keywords: list[str]) -> str:
    for keyword in keywords:
        for turn in turns:
            lower = turn.text.lower()
            if _keyword_in(keyword, lower):
                return turn.text[:220]
    return _first_quote(turns)


def _keyword_in(keyword: str, lower_text: str) -> bool:
    keyword = keyword.lower()
    if len(keyword) <= 3:
        return re.search(rf"\b{re.escape(keyword)}\b", lower_text) is not None
    return keyword in lower_text


def _candidate_turns_after(
    transcript: list[TranscriptTurn], interviewer_keyword: str
) -> list[TranscriptTurn]:
    started = False
    turns: list[TranscriptTurn] = []
    for turn in transcript:
        if turn.speaker == "interviewer" and interviewer_keyword in turn.text.lower():
            started = True
            continue
        if started and turn.speaker == "candidate":
            turns.append(turn)
    return turns
