"""Bounded turn-based interviewer state machine for the v0 prototype."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from ioh_hire.interview import content


Speaker = Literal["interviewer", "candidate", "persona"]


class Phase(str, Enum):
    WARMUP = "warmup"
    MOTIVATION = "motivation"
    RESILIENCE = "resilience"
    ROLEPLAY = "roleplay"
    COACHABILITY = "coachability"
    WRAP = "wrap"
    COMPLETE = "complete"


@dataclass
class TranscriptTurn:
    turn_index: int
    speaker: Speaker
    text: str
    ts: float = field(default_factory=time.time)
    latency_ms: int | None = None


@dataclass
class AgentReply:
    text: str
    speaker: Literal["interviewer", "persona"] = "interviewer"
    phase: Phase = Phase.WARMUP
    is_complete: bool = False
    needs_retry: bool = False


@dataclass
class InterviewSessionState:
    session_id: str
    candidate_id: str
    persona: str
    phase: Phase = Phase.WARMUP
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    transcript: list[TranscriptTurn] = field(default_factory=list)
    candidate_turn_count: int = 0
    roleplay_step: int = 0
    roleplay_objections_thrown: list[str] = field(default_factory=list)
    integrity_trap_thrown: bool = False
    probes_used: dict[str, int] = field(default_factory=dict)
    pending_probe: bool = False
    response_latencies_ms: list[int] = field(default_factory=list)
    max_candidate_turns: int = 12

    @property
    def duration_sec(self) -> int:
        end = self.completed_at or time.time()
        return max(0, int(end - self.started_at))

    @property
    def is_complete(self) -> bool:
        return self.phase == Phase.COMPLETE


class InterviewStateMachine:
    """Deterministic v0 flow; ADK/LLM can wrap this contract later."""

    def new_session(
        self, candidate_id: str | None = None, session_id: str | None = None
    ) -> InterviewSessionState:
        session_id = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        candidate_id = candidate_id or f"cand_{uuid.uuid4().hex[:8]}"
        persona = content.ROLEPLAY_PERSONAS[int(session_id[-1], 16) % 2] if session_id[-1].isalnum() else content.ROLEPLAY_PERSONAS[0]
        return InterviewSessionState(
            session_id=session_id,
            candidate_id=candidate_id,
            persona=persona,
        )

    def opening_reply(self, state: InterviewSessionState) -> AgentReply:
        text = f"{content.INTERVIEWER_INTRO}\n\n{content.WARMUP_PROMPT}"
        return self._append_reply(state, text, "interviewer", Phase.WARMUP)

    def record_candidate_answer(
        self,
        state: InterviewSessionState,
        text: str,
        latency_ms: int | None = None,
    ) -> AgentReply:
        clean_text = " ".join((text or "").strip().split())
        if not clean_text:
            return AgentReply(
                text=content.REPROMPT_AUDIO,
                speaker="interviewer",
                phase=state.phase,
                needs_retry=True,
            )

        if latency_ms is not None:
            state.response_latencies_ms.append(latency_ms)

        state.transcript.append(
            TranscriptTurn(
                turn_index=len(state.transcript),
                speaker="candidate",
                text=clean_text,
                latency_ms=latency_ms,
            )
        )
        state.candidate_turn_count += 1

        if state.candidate_turn_count >= state.max_candidate_turns:
            return self._complete(state)

        if self._should_probe(state, clean_text):
            state.pending_probe = True
            state.probes_used[state.phase.value] = state.probes_used.get(state.phase.value, 0) + 1
            return self._append_reply(
                state, content.FOLLOW_UP_GENERIC, "interviewer", state.phase
            )
        if state.pending_probe:
            state.pending_probe = False

        if state.phase == Phase.WARMUP:
            state.phase = Phase.MOTIVATION
            return self._append_reply(
                state, content.MOTIVATION_PROMPT, "interviewer", state.phase
            )
        if state.phase == Phase.MOTIVATION:
            state.phase = Phase.RESILIENCE
            return self._append_reply(
                state, content.RESILIENCE_PROMPT, "interviewer", state.phase
            )
        if state.phase == Phase.RESILIENCE:
            state.phase = Phase.ROLEPLAY
            return self._append_reply(
                state, content.ROLEPLAY_TRANSITION, "interviewer", state.phase
            )
        if state.phase == Phase.ROLEPLAY:
            return self._next_roleplay_reply(state, clean_text)
        if state.phase == Phase.COACHABILITY:
            return self._complete(state)
        if state.phase in {Phase.WRAP, Phase.COMPLETE}:
            return self._complete(state)

        return self._complete(state)

    def covered_competencies(self, state: InterviewSessionState) -> set[str]:
        covered: set[str] = set()
        candidate_text = " ".join(
            turn.text.lower() for turn in state.transcript if turn.speaker == "candidate"
        )
        if candidate_text:
            covered.add("Komunikasi & kejelasan")
        if any(word in candidate_text for word in ["manfaat", "hemat", "stabil", "keluarga", "belajar", "nonton", "kerja"]):
            covered.add("Persuasi & framing benefit")
        if state.roleplay_objections_thrown:
            covered.add("Ketahanan & komposur")
        if "?" in candidate_text or any(word in candidate_text for word in ["kebutuhan", "pakai apa", "berapa orang", "kendala"]):
            covered.add("Discovery & empati")
        if any(word in candidate_text for word in ["daftar", "jadwal", "cek coverage", "nomor", "lanjut"]):
            covered.add("Drive & orientasi target")
        if state.phase in {Phase.WRAP, Phase.COMPLETE}:
            covered.add("Coachability")
        if state.integrity_trap_thrown:
            covered.add("Integritas")
        return covered

    def _next_roleplay_reply(
        self, state: InterviewSessionState, candidate_text: str
    ) -> AgentReply:
        if state.roleplay_step == 0:
            objection = self._select_objection(candidate_text, state)
            state.roleplay_step = 1
            state.roleplay_objections_thrown.append(objection)
            return self._append_reply(
                state,
                f"{state.persona}: {objection}",
                "persona",
                Phase.ROLEPLAY,
            )
        if state.roleplay_step == 1:
            objection = self._select_objection(candidate_text, state)
            state.roleplay_step = 2
            state.roleplay_objections_thrown.append(objection)
            return self._append_reply(
                state,
                f"{state.persona}: {objection}",
                "persona",
                Phase.ROLEPLAY,
            )
        if state.roleplay_step == 2:
            trap = content.INTEGRITY_TRAPS[0]
            state.roleplay_step = 3
            state.integrity_trap_thrown = True
            return self._append_reply(
                state,
                f"{state.persona}: {trap}",
                "persona",
                Phase.ROLEPLAY,
            )

        state.phase = Phase.COACHABILITY
        return self._append_reply(
            state, content.COACHING_PROMPT, "interviewer", Phase.COACHABILITY
        )

    def _select_objection(
        self, candidate_text: str, state: InterviewSessionState
    ) -> str:
        lower = candidate_text.lower()
        preferred: list[str] = []
        if any(word in lower for word in ["harga", "murah", "mahal", "promo"]):
            preferred.append("Mahal nggak sih? Berapa per bulannya?")
        if any(word in lower for word in ["coverage", "jangkau", "alamat", "area"]):
            preferred.append("Rumah saya kejangkau jaringannya nggak sih?")
        if any(word in lower for word in ["pasang", "instalasi", "kontrak"]):
            preferred.append("Ribet nggak masangnya? Ada kontrak panjang nggak?")
        preferred.extend(content.OBJECTION_BANK)

        for objection in preferred:
            if objection not in state.roleplay_objections_thrown:
                return objection
        return content.OBJECTION_BANK[0]

    def _should_probe(self, state: InterviewSessionState, text: str) -> bool:
        if state.pending_probe:
            return False
        if state.probes_used.get(state.phase.value, 0) >= 1:
            return False
        if state.phase in {Phase.WRAP, Phase.COMPLETE}:
            return False
        words = text.split()
        return len(words) < 7 or text.lower() in {"tidak tahu", "ga tahu", "nggak tahu"}

    def _append_reply(
        self,
        state: InterviewSessionState,
        text: str,
        speaker: Literal["interviewer", "persona"],
        phase: Phase,
    ) -> AgentReply:
        state.transcript.append(
            TranscriptTurn(
                turn_index=len(state.transcript),
                speaker=speaker,
                text=text,
            )
        )
        return AgentReply(
            text=text,
            speaker=speaker,
            phase=phase,
            is_complete=phase == Phase.COMPLETE,
        )

    def _complete(self, state: InterviewSessionState) -> AgentReply:
        state.phase = Phase.COMPLETE
        state.completed_at = state.completed_at or time.time()
        return self._append_reply(
            state,
            content.WRAP_PROMPT,
            "interviewer",
            Phase.COMPLETE,
        )
