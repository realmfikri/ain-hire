"""Runtime configuration for the AIN Hire prototype."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _load_dotenv() -> None:
    path = Path(".env")
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, value = clean.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _strip_gs(uri: str) -> str:
    return uri.removeprefix("gs://")


@dataclass(frozen=True)
class Settings:
    project_id: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    google_cloud_location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    use_vertexai: bool = _bool_env("GOOGLE_GENAI_USE_VERTEXAI", True)

    interviewer_model: str = os.getenv("INTERVIEWER_MODEL", "gemini-flash-latest")
    interviewer_model_location: str = os.getenv("INTERVIEWER_MODEL_LOCATION", "global")
    scorer_model: str = os.getenv("SCORER_MODEL", "gemini-flash-latest")
    scorer_model_location: str = os.getenv("SCORER_MODEL_LOCATION", "global")

    stt_language: str = os.getenv("STT_LANGUAGE", "id-ID")
    stt_model: str = os.getenv("STT_MODEL", "chirp_2")
    stt_location: str = os.getenv("STT_LOCATION", "asia-southeast1")
    stt_recognizer: str = os.getenv("STT_RECOGNIZER", "_")

    tts_language: str = os.getenv("TTS_LANGUAGE", "id-ID")
    tts_voice_interviewer: str = os.getenv(
        "TTS_VOICE_INTERVIEWER", "id-ID-Chirp3-HD-Achernar"
    )
    tts_voice_persona: str = os.getenv("TTS_VOICE_PERSONA", "id-ID-Standard-A")

    bq_dataset: str = os.getenv("BQ_DATASET", "ain_hire")
    bq_location: str = os.getenv("BQ_LOCATION", "asia-southeast2")
    bq_table_sessions: str = os.getenv("BQ_TABLE_SESSIONS", "sessions")
    bq_table_scores: str = os.getenv("BQ_TABLE_SCORES", "scores")
    bq_table_competency: str = os.getenv("BQ_TABLE_COMPETENCY", "competency_scores")
    bq_table_transcripts: str = os.getenv("BQ_TABLE_TRANSCRIPTS", "transcripts")

    audio_bucket: str = os.getenv("AUDIO_BUCKET", "")
    staging_bucket: str = os.getenv("STAGING_BUCKET", "")
    cloud_run_region: str = os.getenv("CLOUD_RUN_REGION", "asia-southeast2")
    invite_link_mode: str = os.getenv("INVITE_LINK_MODE", "stub")

    use_stubs: bool = _bool_env("AIN_HIRE_USE_STUBS", True)
    local_data_dir: Path = Path(os.getenv("LOCAL_DATA_DIR", ".local_data"))

    @property
    def audio_bucket_name(self) -> str:
        return _strip_gs(self.audio_bucket)

    @property
    def staging_bucket_name(self) -> str:
        return _strip_gs(self.staging_bucket)


@lru_cache
def get_settings() -> Settings:
    return Settings()
