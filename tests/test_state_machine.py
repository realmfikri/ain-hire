from ioh_hire.interview.state_machine import InterviewStateMachine, Phase


GOOD_ANSWERS = [
    "Nama saya Andi dan saya tertarik sales lapangan karena suka bertemu orang baru.",
    "Saya mau pekerjaan dengan target yang jelas dan kesempatan belajar komunikasi langsung.",
    "Saya pernah ditolak pembeli, tapi saya tetap sopan, evaluasi cara bicara, lalu coba lagi.",
    "Tok tok, selamat sore Bu. Saya dari Indosat HiFi. Boleh tahu internet rumah dipakai untuk apa saja?",
    "Saya paham Bu. Kalau boleh tahu, kendala di provider sekarang apa supaya saya bisa bandingkan manfaatnya?",
    "Harga perlu saya cek sesuai paket dan alamat, tapi saya bantu pilih yang cocok dengan kebutuhan keluarga.",
    "Saya tidak bisa menjamin sebelum cek coverage alamat Ibu, dan promo gratis harus dicek dulu ketentuannya.",
    "Boleh tahu kebutuhan internet Ibu? Kalau untuk belajar anak, koneksi stabil membantu. Saya cek coverage alamat Ibu lalu jadwalkan pemasangan jika cocok.",
]


def test_empty_answer_reprompts_without_advancing():
    machine = InterviewStateMachine()
    state = machine.new_session(candidate_id="cand_1", session_id="sess_00000a")
    machine.opening_reply(state)

    reply = machine.record_candidate_answer(state, "")

    assert reply.needs_retry is True
    assert state.phase == Phase.WARMUP
    assert state.candidate_turn_count == 0


def test_shallow_answer_gets_one_probe_then_advances():
    machine = InterviewStateMachine()
    state = machine.new_session(candidate_id="cand_1", session_id="sess_00000a")
    machine.opening_reply(state)

    first = machine.record_candidate_answer(state, "iya")
    assert "contoh konkretnya" in first.text
    assert state.phase == Phase.WARMUP

    second = machine.record_candidate_answer(
        state,
        "Saya pernah bantu jualan dan tertarik ketemu pelanggan langsung di lapangan.",
    )
    assert state.phase == Phase.MOTIVATION
    assert "target" in second.text.lower()


def test_full_flow_throws_objections_and_integrity_trap():
    machine = InterviewStateMachine()
    state = machine.new_session(candidate_id="cand_1", session_id="sess_00000a")
    machine.opening_reply(state)

    for answer in GOOD_ANSWERS:
        reply = machine.record_candidate_answer(state, answer, latency_ms=4000)
        if state.is_complete:
            break

    assert state.is_complete
    assert len(state.roleplay_objections_thrown) >= 2
    assert state.integrity_trap_thrown is True
    assert any("dijamin" in turn.text.lower() for turn in state.transcript if turn.speaker == "persona")
    assert reply.is_complete is True


def test_covered_competencies_are_tracked():
    machine = InterviewStateMachine()
    state = machine.new_session(candidate_id="cand_1", session_id="sess_00000a")
    machine.opening_reply(state)
    for answer in GOOD_ANSWERS:
        machine.record_candidate_answer(state, answer, latency_ms=4000)
        if state.is_complete:
            break

    covered = machine.covered_competencies(state)

    assert "Komunikasi & kejelasan" in covered
    assert "Integritas" in covered
    assert "Coachability" in covered
