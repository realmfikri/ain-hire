"""Persistence adapters for local demo data, Cloud Storage, and BigQuery."""

from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from ioh_hire.config import Settings
from ioh_hire.interview.content import ROLE_ID
from ioh_hire.interview.state_machine import InterviewSessionState, TranscriptTurn
from ioh_hire.report import build_scorecard_pdf
from ioh_hire.schema import InterviewResult


class ObjectStore(Protocol):
    def save_audio(
        self,
        session_id: str,
        turn_index: int,
        audio_bytes: bytes,
        mime_type: str | None,
    ) -> str:
        ...

    def save_report_pdf(
        self,
        session_id: str,
        result: InterviewResult,
        transcript: list[TranscriptTurn],
    ) -> str:
        ...


class InterviewRepository(Protocol):
    def save_session_started(self, state: InterviewSessionState) -> None:
        ...

    def save_transcript(self, session_id: str, transcript: list[TranscriptTurn]) -> None:
        ...

    def save_result(self, result: InterviewResult, transcript: list[TranscriptTurn]) -> str:
        ...

    def list_results(self) -> list[dict]:
        ...

    def sign_off(self, session_id: str, decision: str, reviewer: str = "demo_recruiter") -> None:
        ...


class LocalObjectStore:
    def __init__(self, root: Path):
        self.root = root

    def save_audio(
        self,
        session_id: str,
        turn_index: int,
        audio_bytes: bytes,
        mime_type: str | None,
    ) -> str:
        ext = mimetypes.guess_extension(mime_type or "") or ".webm"
        path = self.root / "ioh-hire" / session_id / "audio" / f"turn_{turn_index}{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio_bytes)
        return str(path)

    def save_report_pdf(
        self,
        session_id: str,
        result: InterviewResult,
        transcript: list[TranscriptTurn],
    ) -> str:
        path = self.root / "ioh-hire" / session_id / "report.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(build_scorecard_pdf(result, transcript))
        return str(path)


class GcsObjectStore:
    def __init__(self, settings: Settings):
        from google.cloud import storage

        self.settings = settings
        self.client = storage.Client(project=settings.project_id)
        self.bucket = self.client.bucket(settings.audio_bucket_name)

    def save_audio(
        self,
        session_id: str,
        turn_index: int,
        audio_bytes: bytes,
        mime_type: str | None,
    ) -> str:
        blob = self.bucket.blob(f"ioh-hire/{session_id}/audio/turn_{turn_index}.webm")
        blob.upload_from_string(
            audio_bytes,
            content_type=mime_type or "audio/webm",
        )
        return self._signed_or_gs(blob.name)

    def save_report_pdf(
        self,
        session_id: str,
        result: InterviewResult,
        transcript: list[TranscriptTurn],
    ) -> str:
        blob = self.bucket.blob(f"ioh-hire/{session_id}/report.pdf")
        blob.upload_from_string(
            build_scorecard_pdf(result, transcript),
            content_type="application/pdf",
        )
        return self._signed_or_gs(blob.name)

    def _signed_or_gs(self, blob_name: str) -> str:
        blob = self.bucket.blob(blob_name)
        try:
            return blob.generate_signed_url(
                expiration=timedelta(hours=6),
                method="GET",
            )
        except Exception:
            return f"gs://{self.settings.audio_bucket_name}/{blob_name}"


class LocalJsonRepository:
    def __init__(self, settings: Settings, object_store: ObjectStore | None = None):
        self.root = settings.local_data_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "store.json"
        self.object_store = object_store or LocalObjectStore(self.root)

    def save_session_started(self, state: InterviewSessionState) -> None:
        data = self._read()
        data["sessions"][state.session_id] = {
            "session_id": state.session_id,
            "candidate_id": state.candidate_id,
            "role": ROLE_ID,
            "started_at": _iso(state.started_at),
            "completed_at": _iso(state.completed_at) if state.completed_at else None,
            "status": "started",
            "duration_sec": state.duration_sec,
            "audio_uri_prefix": str(self.root / "ioh-hire" / state.session_id / "audio"),
        }
        self._write(data)

    def save_transcript(self, session_id: str, transcript: list[TranscriptTurn]) -> None:
        data = self._read()
        data["transcripts"][session_id] = [_turn_to_json(turn) for turn in transcript]
        self._write(data)

    def save_result(self, result: InterviewResult, transcript: list[TranscriptTurn]) -> str:
        data = self._read()
        report_uri = self.object_store.save_report_pdf(result.session_id, result, transcript)
        session = data["sessions"].setdefault(result.session_id, {})
        session.update(
            {
                "session_id": result.session_id,
                "candidate_id": result.candidate_id,
                "role": result.role,
                "completed_at": _iso(datetime.now(timezone.utc).timestamp()),
                "status": "completed",
                "duration_sec": result.interview_duration_sec,
            }
        )
        data["scores"][result.session_id] = {
            **result.model_dump(mode="json"),
            "report_uri": report_uri,
            "scored_at": datetime.now(timezone.utc).isoformat(),
            "model_version": "heuristic-local" if "heuristic" not in result.knockout_flags else "heuristic-local",
        }
        data["competency_scores"][result.session_id] = [
            item.model_dump(mode="json") for item in result.competencies
        ]
        data["transcripts"][result.session_id] = [_turn_to_json(turn) for turn in transcript]
        self._write(data)
        return report_uri

    def list_results(self) -> list[dict]:
        data = self._read()
        rows: list[dict] = []
        for session_id, score in data["scores"].items():
            session = data["sessions"].get(session_id, {})
            rows.append(
                {
                    "session": session,
                    "score": score,
                    "competencies": data["competency_scores"].get(session_id, []),
                    "transcript": data["transcripts"].get(session_id, []),
                    "signoff": data["signoffs"].get(session_id),
                }
            )
        return sorted(
            rows,
            key=lambda row: row["score"].get("ranking_score", 0),
            reverse=True,
        )

    def sign_off(self, session_id: str, decision: str, reviewer: str = "demo_recruiter") -> None:
        data = self._read()
        data["signoffs"][session_id] = {
            "session_id": session_id,
            "decision": decision,
            "reviewer": reviewer,
            "signed_at": datetime.now(timezone.utc).isoformat(),
        }
        if session_id in data["sessions"]:
            data["sessions"][session_id]["status"] = f"human_{decision.lower()}"
        self._write(data)

    def _read(self) -> dict:
        if not self.path.exists():
            return {
                "sessions": {},
                "scores": {},
                "competency_scores": {},
                "transcripts": {},
                "signoffs": {},
            }
        return json.loads(self.path.read_text())

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


class BigQueryRepository:
    def __init__(self, settings: Settings, object_store: ObjectStore):
        from google.cloud import bigquery

        self.settings = settings
        self.object_store = object_store
        self.bigquery = bigquery
        self.client = bigquery.Client(project=settings.project_id)
        self.dataset = f"{settings.project_id}.{settings.bq_dataset}"

    def save_session_started(self, state: InterviewSessionState) -> None:
        row = {
            "session_id": state.session_id,
            "candidate_id": state.candidate_id,
            "role": ROLE_ID,
            "started_at": _iso(state.started_at),
            "completed_at": None,
            "status": "started",
            "duration_sec": state.duration_sec,
            "audio_uri_prefix": f"gs://{self.settings.audio_bucket_name}/ioh-hire/{state.session_id}/audio",
        }
        self._insert(self.settings.bq_table_sessions, [row])

    def save_transcript(self, session_id: str, transcript: list[TranscriptTurn]) -> None:
        rows = [_turn_to_json(turn, session_id=session_id) for turn in transcript]
        if rows:
            self._insert(self.settings.bq_table_transcripts, rows)

    def save_result(self, result: InterviewResult, transcript: list[TranscriptTurn]) -> str:
        report_uri = self.object_store.save_report_pdf(result.session_id, result, transcript)
        score_row = {
            "session_id": result.session_id,
            "recommendation": result.recommendation.value,
            "ranking_score": result.ranking_score,
            "confidence": result.confidence,
            "knockout_flags": result.knockout_flags,
            "summary": result.summary_id,
            "scored_at": datetime.now(timezone.utc).isoformat(),
            "model_version": self.settings.scorer_model,
        }
        competency_rows = [
            {
                "session_id": result.session_id,
                "name": item.name,
                "score": item.score,
                "insufficient_evidence": item.insufficient_evidence,
                "rationale": item.rationale,
                "evidence_quotes": item.evidence_quotes,
            }
            for item in result.competencies
        ]
        self._insert(self.settings.bq_table_scores, [score_row])
        self._insert(self.settings.bq_table_competency, competency_rows)
        self.save_transcript(result.session_id, transcript)
        return report_uri

    def list_results(self) -> list[dict]:
        query = f"""
        SELECT
          s.session_id, s.candidate_id, s.status,
          sc.recommendation, sc.ranking_score, sc.confidence,
          sc.knockout_flags, sc.summary, sc.scored_at, sc.model_version
        FROM `{self.dataset}.{self.settings.bq_table_scores}` sc
        JOIN `{self.dataset}.{self.settings.bq_table_sessions}` s USING (session_id)
        ORDER BY sc.ranking_score DESC
        LIMIT 100
        """
        rows = self.client.query(query).result()
        return [
            {
                "session": {
                    "session_id": row.session_id,
                    "candidate_id": row.candidate_id,
                    "status": row.status,
                },
                "score": {
                    "recommendation": row.recommendation,
                    "ranking_score": row.ranking_score,
                    "confidence": row.confidence,
                    "knockout_flags": list(row.knockout_flags or []),
                    "summary_id": row.summary,
                    "scored_at": row.scored_at,
                    "model_version": row.model_version,
                },
                "competencies": self._fetch_competencies(row.session_id),
                "transcript": self._fetch_transcript(row.session_id),
                "signoff": None,
            }
            for row in rows
        ]

    def sign_off(self, session_id: str, decision: str, reviewer: str = "demo_recruiter") -> None:
        query = f"""
        UPDATE `{self.dataset}.{self.settings.bq_table_sessions}`
        SET status = @status
        WHERE session_id = @session_id
        """
        job_config = self.bigquery.QueryJobConfig(
            query_parameters=[
                self.bigquery.ScalarQueryParameter("status", "STRING", f"human_{decision.lower()}"),
                self.bigquery.ScalarQueryParameter("session_id", "STRING", session_id),
            ]
        )
        self.client.query(query, job_config=job_config).result()

    def _fetch_competencies(self, session_id: str) -> list[dict]:
        query = f"""
        SELECT name, score, insufficient_evidence, rationale, evidence_quotes
        FROM `{self.dataset}.{self.settings.bq_table_competency}`
        WHERE session_id = @session_id
        """
        rows = self.client.query(query, job_config=self._session_job_config(session_id)).result()
        return [dict(row.items()) for row in rows]

    def _fetch_transcript(self, session_id: str) -> list[dict]:
        query = f"""
        SELECT turn_index, speaker, text, ts
        FROM `{self.dataset}.{self.settings.bq_table_transcripts}`
        WHERE session_id = @session_id
        ORDER BY turn_index
        """
        rows = self.client.query(query, job_config=self._session_job_config(session_id)).result()
        return [dict(row.items()) for row in rows]

    def _session_job_config(self, session_id: str):
        return self.bigquery.QueryJobConfig(
            query_parameters=[
                self.bigquery.ScalarQueryParameter("session_id", "STRING", session_id)
            ]
        )

    def _insert(self, table: str, rows: list[dict]) -> None:
        if not rows:
            return
        errors = self.client.insert_rows_json(f"{self.dataset}.{table}", rows)
        if errors:
            raise RuntimeError(f"BigQuery insert failed for {table}: {errors}")


def build_object_store(settings: Settings) -> ObjectStore:
    if settings.use_stubs:
        return LocalObjectStore(settings.local_data_dir)
    return GcsObjectStore(settings)


def build_repository(settings: Settings, object_store: ObjectStore | None = None) -> InterviewRepository:
    object_store = object_store or build_object_store(settings)
    if settings.use_stubs:
        return LocalJsonRepository(settings, object_store=object_store)
    return BigQueryRepository(settings, object_store=object_store)


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _turn_to_json(turn: TranscriptTurn, session_id: str | None = None) -> dict:
    row = {
        "turn_index": turn.turn_index,
        "speaker": turn.speaker,
        "text": turn.text,
        "ts": _iso(turn.ts),
    }
    if session_id is not None:
        row["session_id"] = session_id
    return row
