"""Run one synthetic candidate through the v0 flow without a phone."""

from __future__ import annotations

import os
import sys
import wave
from io import BytesIO
from pathlib import Path

os.environ.setdefault("IOH_HIRE_USE_STUBS", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ioh_hire.config import get_settings
from ioh_hire.interview.state_machine import InterviewStateMachine
from ioh_hire.scoring import HeuristicScoringEngine, has_implausibly_fast_answers
from ioh_hire.storage import build_object_store, build_repository


ANSWERS = [
    "Nama saya Andi. Saya lulusan SMK dan pernah bantu jualan keluarga, jadi saya terbiasa ketemu orang dan tertarik kerja sales lapangan internet rumah.",
    "Saya suka pekerjaan yang ada target karena hasilnya jelas. Saya juga senang ngobrol dengan orang baru dan belajar cara menjelaskan manfaat produk dengan sederhana.",
    "Pernah saya tawarkan barang dagangan tapi banyak yang menolak. Saya tetap sopan, tanya alasannya, lalu coba lagi ke orang berikutnya sambil memperbaiki cara bicara.",
    "Tok tok, selamat sore Bu. Saya Andi dari Indosat HiFi. Boleh tahu di rumah internet biasanya dipakai untuk apa saja, misalnya kerja, belajar anak, atau nonton?",
    "Saya paham Bu sudah pakai provider lain. Kalau boleh, kendala yang sering dirasakan apa? Indosat HiFi bisa jadi pilihan kalau Ibu butuh koneksi rumah yang stabil untuk keluarga.",
    "Untuk harga dan paket saya akan cek penawaran terbaru sesuai alamat Ibu. Yang penting kita pastikan dulu kebutuhan dan coverage supaya paketnya pas.",
    "Saya tidak bisa menjamin sebelum cek coverage alamat Ibu. Untuk promo gratis juga harus saya cek dulu ketentuannya, tapi saya bisa bantu cek sekarang kalau Ibu berkenan.",
    "Boleh tahu kebutuhan internet di rumah Ibu paling sering untuk apa? Kalau untuk belajar anak dan nonton, manfaatnya koneksi rumah lebih stabil. Langkah berikutnya saya cek coverage dari alamat Ibu dan kalau cocok kita jadwalkan pemasangan.",
]


def _silent_wav_bytes(duration_ms: int = 300) -> bytes:
    sample_rate = 8000
    frame_count = int(sample_rate * duration_ms / 1000)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


def main() -> None:
    settings = get_settings()
    object_store = build_object_store(settings)
    repository = build_repository(settings, object_store=object_store)
    machine = InterviewStateMachine()
    scorer = HeuristicScoringEngine()

    state = machine.new_session(candidate_id="synthetic_good_001")
    repository.save_session_started(state)
    reply = machine.opening_reply(state)
    print(f"{reply.speaker}: {reply.text}")

    for answer in ANSWERS:
        print(f"candidate: {answer}")
        object_store.save_audio(
            state.session_id,
            state.candidate_turn_count + 1,
            _silent_wav_bytes(),
            "audio/wav",
        )
        reply = machine.record_candidate_answer(state, answer, latency_ms=4500)
        print(f"{reply.speaker}: {reply.text}")
        if state.is_complete:
            break

    result = scorer.score(
        state.session_id,
        state.candidate_id,
        state.transcript,
        state.duration_sec,
        latency_flag=has_implausibly_fast_answers(state.transcript),
    )
    report_uri = repository.save_result(result, state.transcript)
    print()
    print(result.model_dump_json(indent=2))
    print(f"Report: {report_uri}")


if __name__ == "__main__":
    main()
