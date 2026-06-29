from __future__ import annotations

import time
from pathlib import Path

import streamlit as st

from ain_hire.config import Settings, get_settings
from ain_hire.interview import content
from ain_hire.interview.state_machine import InterviewSessionState, InterviewStateMachine
from ain_hire.schema import InterviewResult
from ain_hire.scoring import build_scoring_engine, has_implausibly_fast_answers
from ain_hire.storage import build_object_store, build_repository
from ain_hire.voice import build_voice_provider


# v0 intentionally uses Streamlit for speed and st.audio_input support.
# v1 should move to FastAPI plus a minimal mobile web client for finer control
# over recording codecs, resumable uploads, and unstable mobile connections.
st.set_page_config(
    page_title="AIN Hire",
    page_icon=None,
    layout="centered",
    initial_sidebar_state="collapsed",
)


@st.cache_resource
def _resources():
    settings = get_settings()
    object_store = build_object_store(settings)
    return {
        "settings": settings,
        "machine": InterviewStateMachine(),
        "voice": build_voice_provider(settings),
        "scorer": build_scoring_engine(settings),
        "repository": build_repository(settings, object_store=object_store),
        "object_store": object_store,
    }


def main() -> None:
    resources = _resources()
    page = st.sidebar.radio(
        "View",
        ["Candidate interview", "Recruiter dashboard"],
        label_visibility="collapsed",
    )
    if page == "Candidate interview":
        render_candidate(resources)
    else:
        render_recruiter(resources)


def render_candidate(resources: dict) -> None:
    settings: Settings = resources["settings"]
    machine: InterviewStateMachine = resources["machine"]
    repository = resources["repository"]

    st.title("AIN Hire")
    st.caption("Screening awal Direct Sales - XL SATU")

    if "interview_state" not in st.session_state:
        st.session_state.interview_state = None
        st.session_state.prompt_started_at = None
        st.session_state.scored_result = None

    if st.session_state.interview_state is None:
        candidate_from_url = ""
        try:
            candidate_from_url = st.query_params.get("candidate_id", "")
        except Exception:
            candidate_from_url = ""
        candidate_id = st.text_input(
            "Candidate ID",
            value=candidate_from_url or "",
            placeholder="contoh: cand_001",
        )
        st.info(content.CONSENT_TEXT)
        consent = st.checkbox("Saya setuju wawancara ini direkam dan dinilai untuk proses rekrutmen XLSmart.")
        if st.button("Mulai wawancara", disabled=not consent):
            state = machine.new_session(candidate_id=candidate_id.strip() or None)
            repository.save_session_started(state)
            machine.opening_reply(state)
            st.session_state.interview_state = state
            st.session_state.prompt_started_at = time.time()
            st.rerun()
        return

    state: InterviewSessionState = st.session_state.interview_state
    _render_latest_agent_turn(resources, state)

    if state.is_complete:
        _render_completion(resources, state)
        return

    with st.form("candidate_answer", clear_on_submit=True):
        audio_file = None
        if hasattr(st, "audio_input"):
            audio_file = st.audio_input("Rekam jawaban kamu")
        else:
            st.warning("Versi Streamlit ini belum menyediakan st.audio_input.")

        fallback_text = ""
        if settings.use_stubs:
            fallback_text = st.text_area(
                "Fallback teks untuk demo lokal",
                placeholder="Ketik jawaban jika Cloud STT belum dikonfigurasi.",
            )

        submitted = st.form_submit_button("Kirim jawaban")

    if submitted:
        _handle_candidate_submit(resources, state, audio_file, fallback_text)

    with st.expander("Transkrip sementara"):
        for turn in state.transcript:
            st.markdown(f"**{turn.speaker}:** {turn.text}")


def _render_latest_agent_turn(resources: dict, state: InterviewSessionState) -> None:
    voice = resources["voice"]
    latest = next(
        (turn for turn in reversed(state.transcript) if turn.speaker in {"interviewer", "persona"}),
        None,
    )
    if latest is None:
        return

    speaker_name = "Interviewer" if latest.speaker == "interviewer" else state.persona
    st.subheader(speaker_name)
    st.write(latest.text)
    try:
        audio = voice.synthesize(latest.text, persona=latest.speaker == "persona")
        if audio.audio_bytes:
            st.audio(audio.audio_bytes, format=audio.mime_type)
    except Exception as exc:
        st.caption(f"TTS tidak tersedia di mode ini: {exc}")


def _handle_candidate_submit(
    resources: dict,
    state: InterviewSessionState,
    audio_file,
    fallback_text: str,
) -> None:
    settings: Settings = resources["settings"]
    voice = resources["voice"]
    object_store = resources["object_store"]
    repository = resources["repository"]
    machine: InterviewStateMachine = resources["machine"]
    scorer = resources["scorer"]

    latency_ms = None
    if st.session_state.prompt_started_at:
        latency_ms = int((time.time() - st.session_state.prompt_started_at) * 1000)

    transcript_text = fallback_text.strip() if settings.use_stubs else ""
    audio_bytes = b""
    mime_type = None
    if audio_file is not None:
        audio_bytes = audio_file.getvalue()
        mime_type = getattr(audio_file, "type", "audio/webm")
        if audio_bytes:
            try:
                object_store.save_audio(
                    state.session_id,
                    state.candidate_turn_count + 1,
                    audio_bytes,
                    mime_type,
                )
            except Exception as exc:
                st.warning(f"Audio belum bisa disimpan: {exc}")
        if audio_bytes and not transcript_text:
            try:
                transcript_text = voice.transcribe(audio_bytes, mime_type=mime_type).text
            except Exception as exc:
                st.warning(f"Transkripsi gagal: {exc}")
                transcript_text = ""

    reply = machine.record_candidate_answer(state, transcript_text, latency_ms=latency_ms)
    if settings.use_stubs:
        repository.save_transcript(state.session_id, state.transcript)

    if reply.needs_retry:
        st.session_state.prompt_started_at = time.time()
        st.rerun()

    if state.is_complete and st.session_state.scored_result is None:
        result = scorer.score(
            state.session_id,
            state.candidate_id,
            state.transcript,
            state.duration_sec,
            latency_flag=has_implausibly_fast_answers(state.transcript),
        )
        repository.save_result(result, state.transcript)
        st.session_state.scored_result = result.model_dump(mode="json")

    st.session_state.prompt_started_at = time.time()
    st.rerun()


def _render_completion(resources: dict, state: InterviewSessionState) -> None:
    repository = resources["repository"]
    scorer = resources["scorer"]

    st.success("Wawancara selesai. Terima kasih.")
    if st.session_state.scored_result is None:
        result = scorer.score(
            state.session_id,
            state.candidate_id,
            state.transcript,
            state.duration_sec,
            latency_flag=has_implausibly_fast_answers(state.transcript),
        )
        repository.save_result(result, state.transcript)
        st.session_state.scored_result = result.model_dump(mode="json")

    result = InterviewResult.model_validate(st.session_state.scored_result)
    st.write(result.summary_id)
    st.metric("Recommendation", result.recommendation.value)
    st.metric("Ranking score", result.ranking_score)
    if st.button("Mulai sesi baru"):
        st.session_state.interview_state = None
        st.session_state.prompt_started_at = None
        st.session_state.scored_result = None
        st.rerun()


def render_recruiter(resources: dict) -> None:
    settings: Settings = resources["settings"]
    repository = resources["repository"]

    st.title("Recruiter shortlist")
    st.caption("Sorted by ranking_score. Human sign-off is required before any final reject.")
    rows = repository.list_results()
    if not rows:
        st.info("Belum ada sesi yang selesai.")
        return

    for row in rows:
        score = row["score"]
        session = row["session"]
        session_id = session["session_id"]
        title = (
            f"{session.get('candidate_id', session_id)} | "
            f"{score.get('recommendation')} | {score.get('ranking_score')}"
        )
        with st.expander(title, expanded=False):
            st.write(score.get("summary_id") or score.get("summary"))
            st.caption(f"Session: {session_id} | Status: {session.get('status', 'unknown')}")
            if score.get("knockout_flags"):
                st.warning("Knockout/Review flags: " + ", ".join(score["knockout_flags"]))

            st.subheader("Evidence")
            for item in row.get("competencies", []):
                score_value = "insufficient" if item.get("insufficient_evidence") else item.get("score")
                st.markdown(f"**{item.get('name')}**: {score_value}")
                st.write(item.get("rationale"))
                for quote in item.get("evidence_quotes", [])[:2]:
                    st.caption(f"\"{quote}\"")

            _render_audio_playback(settings, session_id)

            with st.expander("Full transcript"):
                for turn in row.get("transcript", []):
                    st.markdown(f"**{turn.get('speaker')}:** {turn.get('text')}")

            current_signoff = row.get("signoff")
            if current_signoff:
                st.success(
                    f"Signed off: {current_signoff['decision']} by {current_signoff['reviewer']}"
                )
            col1, col2, col3 = st.columns(3)
            if col1.button("Sign off PASS", key=f"pass_{session_id}"):
                repository.sign_off(session_id, "PASS")
                st.rerun()
            if col2.button("Sign off REJECT", key=f"reject_{session_id}"):
                repository.sign_off(session_id, "REJECT")
                st.rerun()
            if col3.button("Mark REVIEW", key=f"review_{session_id}"):
                repository.sign_off(session_id, "REVIEW")
                st.rerun()


def _render_audio_playback(settings: Settings, session_id: str) -> None:
    local_audio_dir = settings.local_data_dir / "ain-hire" / session_id / "audio"
    if not local_audio_dir.exists():
        return
    audio_paths = sorted(Path(local_audio_dir).glob("turn_*"))
    if not audio_paths:
        return
    st.subheader("Audio")
    for path in audio_paths:
        st.caption(path.name)
        st.audio(path.read_bytes())


if __name__ == "__main__":
    main()
