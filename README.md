# IOH AI Interviewer

Mobile-first v0 prototype for screening entry-level Direct Sales candidates for Indosat HiFi. The app runs a short Bahasa Indonesia voice interview, scores the transcript against a sales competency rubric, persists an audit trail, and shows a ranked recruiter shortlist with human sign-off.

## What is included

- Streamlit candidate client with consent gate, turn-based audio, STT/TTS provider interfaces, and local text fallback.
- Deterministic v0 interviewer state machine with bounded probing, role-play objections, integrity trap, coachability prompt, and wrap.
- Separate scorer interface: pinned Gemini scorer for GCP mode, heuristic scorer for local no-cost demo mode.
- Pydantic `InterviewResult` schema with knockout enforcement and ranking score helper.
- Local JSON storage plus GCS/BigQuery adapters.
- Recruiter dashboard sorted by `ranking_score`, evidence quotes, transcript, local audio playback, and sign-off buttons.
- BigQuery DDL and a seed script that creates one completed synthetic interview.
- Tests for schema validation and the interviewer state machine.

No GCP resources are created by this repo. Create buckets, datasets, and Cloud Run/Agent Engine deployments only after approval.

## Local setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For local no-cost mode, keep:

```dotenv
IOH_HIRE_USE_STUBS=true
```

Run tests:

```bash
pytest
```

Seed a completed demo interview:

```bash
python scripts/seed_demo.py
```

Run the Streamlit app:

```bash
streamlit run app.py
```

Open the recruiter dashboard from the sidebar after running the seed script.

## GCP mode

Set these in `.env` or Cloud Run environment variables:

- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION=global`
- `GOOGLE_GENAI_USE_VERTEXAI=true`
- `INTERVIEWER_MODEL=gemini-flash-latest`
- `SCORER_MODEL=gemini-2.5-flash-001`
- `STT_LANGUAGE=id-ID`
- `STT_MODEL=chirp_2`
- `STT_LOCATION=asia-southeast2`
- `TTS_LANGUAGE=id-ID`
- `TTS_VOICE_INTERVIEWER`
- `TTS_VOICE_PERSONA`
- `BQ_DATASET=ioh_hire`
- `AUDIO_BUCKET`
- `IOH_HIRE_USE_STUBS=false`

Apply the BigQuery schema after replacing `PROJECT_ID` in [ddl/bigquery.sql](ddl/bigquery.sql).

Cloud Run example:

```bash
gcloud run deploy ioh-ai-interviewer \
  --source . \
  --region "$CLOUD_RUN_REGION" \
  --service-account "$CLOUD_RUN_SERVICE_ACCOUNT" \
  --set-env-vars IOH_HIRE_USE_STUBS=false
```

Agent Engine deploy helper:

```bash
python scripts/deploy_agent_engine.py
```

The deploy helper requires `GOOGLE_CLOUD_PROJECT`, `AGENT_ENGINE_REGION`, `STAGING_BUCKET`, and `AGENT_ENGINE_SERVICE_ACCOUNT` in the environment.

## Data layout

GCS:

```text
gs://$AUDIO_BUCKET/ioh-hire/{session_id}/audio/turn_{n}.webm
gs://$AUDIO_BUCKET/ioh-hire/{session_id}/report.pdf
```

BigQuery tables:

- `ioh_hire.sessions`
- `ioh_hire.scores`
- `ioh_hire.competency_scores`
- `ioh_hire.transcripts`

Local stub mode mirrors the same information under `.local_data/`.

## Notes

- The interviewer and scorer are deliberately separate. The interviewer converses; the scorer judges after completion.
- Dialect, accent, code-switching, and informal speech are explicitly not scoring penalties.
- Bad or empty audio triggers a re-prompt and does not advance the state machine.
- Human sign-off is required in the recruiter dashboard before final rejection.
- Real WhatsApp/ATS integration, real-time streaming, voice consistency checks, and multi-role configuration are out of scope for v0.
