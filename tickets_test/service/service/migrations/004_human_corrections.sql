CREATE TABLE IF NOT EXISTS ticket_human_corrections (
    correction_id BIGSERIAL PRIMARY KEY,
    correction_key TEXT NOT NULL UNIQUE,
    sha256 CHAR(64) NOT NULL,
    fields JSONB NOT NULL,
    reason TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    reviewer TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ticket_human_corrections_sha_idx
    ON ticket_human_corrections(sha256, created_at DESC);

DROP TRIGGER IF EXISTS ticket_human_corrections_no_update ON ticket_human_corrections;
CREATE TRIGGER ticket_human_corrections_no_update
BEFORE UPDATE OR DELETE ON ticket_human_corrections
FOR EACH ROW EXECUTE FUNCTION prevent_append_only_mutation();
