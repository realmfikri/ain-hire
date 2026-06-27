-- Replace PROJECT_ID before running, or use bq with your configured default project.
-- Example:
--   bq query --use_legacy_sql=false < ddl/bigquery.sql

CREATE SCHEMA IF NOT EXISTS `PROJECT_ID.ioh_hire`
OPTIONS(location = "asia-southeast2");

CREATE TABLE IF NOT EXISTS `PROJECT_ID.ioh_hire.sessions` (
  session_id STRING NOT NULL,
  candidate_id STRING NOT NULL,
  role STRING NOT NULL,
  started_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  status STRING NOT NULL,
  duration_sec INT64,
  audio_uri_prefix STRING
)
PARTITION BY DATE(started_at)
CLUSTER BY candidate_id, status;

CREATE TABLE IF NOT EXISTS `PROJECT_ID.ioh_hire.scores` (
  session_id STRING NOT NULL,
  recommendation STRING NOT NULL,
  ranking_score INT64 NOT NULL,
  confidence STRING NOT NULL,
  knockout_flags ARRAY<STRING>,
  summary STRING NOT NULL,
  scored_at TIMESTAMP NOT NULL,
  model_version STRING NOT NULL
)
PARTITION BY DATE(scored_at)
CLUSTER BY recommendation, ranking_score;

CREATE TABLE IF NOT EXISTS `PROJECT_ID.ioh_hire.competency_scores` (
  session_id STRING NOT NULL,
  name STRING NOT NULL,
  score INT64,
  insufficient_evidence BOOL NOT NULL,
  rationale STRING NOT NULL,
  evidence_quotes ARRAY<STRING>
)
CLUSTER BY session_id, name;

CREATE TABLE IF NOT EXISTS `PROJECT_ID.ioh_hire.transcripts` (
  session_id STRING NOT NULL,
  turn_index INT64 NOT NULL,
  speaker STRING NOT NULL,
  text STRING NOT NULL,
  ts TIMESTAMP NOT NULL
)
PARTITION BY DATE(ts)
CLUSTER BY session_id, turn_index;
