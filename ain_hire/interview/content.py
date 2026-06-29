"""Bahasa Indonesia interview IP for the XLSmart direct sales screen."""

from __future__ import annotations

ROLE_ID = "direct_sales_xlsatu"
ROLE_NAME = "Direct Sales - XL SATU"

CONSENT_TEXT = (
    "Sebelum mulai, kami perlu persetujuan kamu. Wawancara ini akan direkam "
    "dalam bentuk audio, ditranskrip, dan dinilai untuk membantu rekruter XLSmart "
    "menentukan kandidat yang perlu dihubungi lebih lanjut. Rekaman dan "
    "transkrip dipakai hanya untuk proses rekrutmen dan audit penilaian. "
    "Keputusan akhir tetap oleh manusia, bukan otomatis oleh AI."
)

INTERVIEWER_INTRO = (
    "Halo, saya AI Interviewer dari AIN Hire untuk XLSmart. Kita akan ngobrol singkat sekitar "
    "delapan sampai dua belas menit. Jawab santai dalam Bahasa Indonesia "
    "sehari-hari. Dialek atau logat tidak dinilai; yang penting jawaban kamu "
    "bisa dipahami."
)

WARMUP_PROMPT = (
    "Halo, kenalin dulu ya. Boleh ceritain singkat tentang diri kamu dan "
    "kenapa tertarik jadi sales lapangan internet rumah?"
)

MOTIVATION_PROMPT = (
    "Kerjaan sales lapangan punya target dan banyak ketemu orang baru. "
    "Apa yang bikin kamu mau menjalani pekerjaan seperti ini?"
)

RESILIENCE_PROMPT = (
    "Kerjaan ini sering banget dapet penolakan: diketok pintunya, ditolak, "
    "lalu pindah ke rumah berikutnya. Ceritain satu pengalaman kamu ditolak "
    "atau gagal, dan gimana kamu nyikapinnya."
)

ROLEPLAY_TRANSITION = (
    "Oke, sekarang kita coba simulasi ya. Bayangin saya penghuni rumah, kamu "
    "lagi nawarin internet rumah XL SATU dari pintu ke pintu. Mulai aja, "
    "ketok 'pintu' saya."
)

COACHING_PROMPT = (
    "Saya kasih masukan singkat. Coba tanya kebutuhan penghuni dulu, lalu "
    "jelaskan manfaat yang relevan, dan tutup dengan langkah berikutnya yang "
    "jelas seperti cek coverage atau jadwal pemasangan. Sekarang ulangi pitch "
    "singkat kamu dengan masukan itu."
)

WRAP_PROMPT = (
    "Terima kasih, wawancaranya sudah selesai. Tim rekrutmen XLSmart akan meninjau "
    "hasilnya dan menghubungi kamu jika ada tahap berikutnya."
)

REPROMPT_AUDIO = (
    "Maaf, audio kamu belum terdengar jelas atau belum ada jawaban yang masuk. "
    "Tolong rekam ulang jawaban kamu dengan suara sedikit lebih dekat ke mikrofon."
)

FOLLOW_UP_GENERIC = "Boleh kasih contoh konkretnya?"

ROLEPLAY_PERSONAS = ["Bu Sri", "Pak Budi"]

OBJECTION_BANK = [
    "Saya udah pakai IndiHome, ngapain repot-repot pindah?",
    "Saya udah pakai First Media, ngapain ganti?",
    "Di kompleks sini banyak yang pakai Biznet, bedanya apa?",
    "Mahal nggak sih? Berapa per bulannya?",
    "Rumah saya kejangkau jaringannya nggak sih?",
    "Lagi sibuk nih, nanti aja deh.",
    "Internet HP saya udah cukup kok buat sekarang.",
    "Ribet nggak masangnya? Ada kontrak panjang nggak?",
]

INTEGRITY_TRAPS = [
    (
        "Rumah saya sinyalnya jelek lho. Emang dijamin kenceng terus di sini? "
        "Kalau bisa, bulan pertama gratis nggak?"
    ),
    (
        "Kalau saya daftar sekarang, bisa dijamin pasti aktif dan paling cepat "
        "dibanding semua provider lain nggak?"
    ),
]

PRODUCT_CONTEXT = (
    "XL SATU adalah fixed home broadband untuk internet rumah, terutama berbasis "
    "fiber hingga sekitar 1Gbps, dengan varian wireless Lite di area tertentu. "
    "Paket dapat mencakup kuota mobile bersama untuk anggota rumah tangga. "
    "Harga paket kira-kira Rp129 ribu sampai Rp499 ribu per bulan, belum termasuk "
    "perangkat bila berlaku. Coverage bergantung alamat dan hanya tersedia di "
    "area yang dijangkau XL SATU. Kandidat tidak boleh menjamin coverage, "
    "kecepatan, harga, promo gratis, kontrak, atau jadwal instalasi kalau belum "
    "diverifikasi."
)

SCORING_RUBRIC = """
Nilai setiap kompetensi 1-5 dengan bukti kutipan transkrip:

1. Komunikasi & kejelasan (K): jelas, mudah dipahami, terstruktur sederhana.
2. Persuasi & framing benefit: mengubah fitur menjadi manfaat untuk penghuni.
3. Ketahanan & komposur: tetap hangat dan berusaha setelah penolakan.
4. Discovery & empati: bertanya dan mendengarkan sebelum/ketika pitching.
5. Drive & orientasi target: mengarah ke next step konkret.
6. Coachability: menerapkan feedback dalam turn berikutnya.
7. Integritas (K): tidak overpromise soal coverage, speed, harga, kontrak.

Dialek, aksen, code-switching, dan gaya informal tidak boleh menurunkan skor.
Jika kualitas audio/transkrip tidak cukup untuk menilai kompetensi, tandai
insufficient_evidence, bukan memberi skor rendah.
"""
