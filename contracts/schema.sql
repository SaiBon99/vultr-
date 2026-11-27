-- contracts/schema.sql : FROZEN Phase 0 contract (Option B, vector(1024)).
-- Owner: Coordinator. infra/sql/001_init.sql applies this file; backend reads it. Change only via an OpenSpec change.
-- Idempotent: safe to run more than once.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid()

-- Roles (NOLOGIN here; infra sets LOGIN + PASSWORD from env). memory_reader can only see active memories.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quarantine_proxy') THEN CREATE ROLE quarantine_proxy NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'memory_reader') THEN CREATE ROLE memory_reader NOLOGIN; END IF;
END $$;

GRANT USAGE ON SCHEMA public TO quarantine_proxy, memory_reader; -- required on PG 15+ (public no longer world-writable/usable by default on managed PG)

CREATE TABLE IF NOT EXISTS sessions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash       text NOT NULL UNIQUE,                       -- sha256 hex of the opaque session_token; token itself never stored
  gate_mode        text NOT NULL DEFAULT 'quarantined' CHECK (gate_mode IN ('quarantined', 'naive')),
  tainted          boolean NOT NULL DEFAULT false,             -- sticky: never flips back to false
  external_sources jsonb NOT NULL DEFAULT '[]'::jsonb,         -- [{source_ref, source_kind, read_at}]
  write_count      integer NOT NULL DEFAULT 0,
  created_at       timestamptz NOT NULL DEFAULT now()
);

-- Active recall only. Nothing quarantined ever lives here.
CREATE TABLE IF NOT EXISTS memories (
  id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id                  uuid NOT NULL REFERENCES sessions(id),
  content                     text NOT NULL,
  source                      text NOT NULL CHECK (source IN ('user', 'external_override')),
  source_ref                  text,
  payload_hash                text NOT NULL,                   -- 'sha256:<hex>' of content (UTF-8)
  embedding                   vector(1024),
  promoted_from_quarantine_id uuid,
  created_at                  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS memories_embedding_hnsw ON memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS memories_session_idx ON memories (session_id);

CREATE TABLE IF NOT EXISTS quarantine_queue (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id      uuid NOT NULL REFERENCES sessions(id),
  status          text NOT NULL DEFAULT 'quarantined' CHECK (status IN ('quarantined', 'purged', 'overridden')),
  content         text,                                        -- wiped to NULL on purge
  payload_hash    text NOT NULL,                               -- retained on purge (tombstone)
  embedding       vector(1024),                                -- retained on purge for known-poison similarity
  source          text NOT NULL CHECK (source IN ('user', 'external')),
  source_ref      text,
  verdict         text NOT NULL CHECK (verdict IN ('TAINTED_UNREVIEWED', 'POLICY_BLOCKED', 'INCONCLUSIVE')),
  rule_flags      jsonb NOT NULL DEFAULT '[]'::jsonb,          -- array of RuleFlag strings (contracts/openapi.yaml)
  judge_status    text NOT NULL DEFAULT 'pending' CHECK (judge_status IN ('pending', 'done', 'failed')),
  judge_note      jsonb,                                       -- contracts/judge.schema.json when judge_status = 'done'
  override_reason text,
  decided_by      text,
  decided_at      timestamptz,
  receipt_uri     text,                                        -- latest receipt (s3://bucket/receipts/<receipt_id>.json)
  created_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT purged_has_no_content CHECK (status <> 'purged' OR content IS NULL),
  CONSTRAINT blocked_override_needs_reason CHECK (
    NOT (status = 'overridden' AND verdict = 'POLICY_BLOCKED') OR length(btrim(coalesce(override_reason, ''))) > 0)
);
CREATE INDEX IF NOT EXISTS quarantine_session_idx ON quarantine_queue (session_id);
CREATE INDEX IF NOT EXISTS quarantine_status_idx ON quarantine_queue (status);
CREATE INDEX IF NOT EXISTS quarantine_poison_hnsw ON quarantine_queue USING hnsw (embedding vector_cosine_ops)
  WHERE status = 'purged' AND embedding IS NOT NULL;

-- Append-only SHA-256 hash chain. Hash formula: contracts/README.md.
CREATE TABLE IF NOT EXISTS audit_events (
  seq        bigserial PRIMARY KEY,
  session_id uuid,
  event_type text NOT NULL,
  target_id  uuid,
  payload    jsonb NOT NULL,
  prev_hash  text NOT NULL,
  event_hash text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS audit_events_prev_hash_uniq ON audit_events (prev_hash); -- one successor per link: concurrent appends conflict instead of forking the chain

CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'audit_events is append-only'; END $$;
DROP TRIGGER IF EXISTS audit_events_no_mutation ON audit_events;
CREATE TRIGGER audit_events_no_mutation BEFORE UPDATE OR DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION audit_events_append_only();

-- Grants. memory_reader: SELECT on memories ONLY (no quarantine_queue, sessions or audit_events).
GRANT SELECT ON TABLE memories TO memory_reader;
GRANT SELECT, INSERT, UPDATE ON TABLE sessions, memories, quarantine_queue TO quarantine_proxy;
GRANT SELECT, INSERT ON TABLE audit_events TO quarantine_proxy;
GRANT USAGE, SELECT ON SEQUENCE audit_events_seq_seq TO quarantine_proxy;
