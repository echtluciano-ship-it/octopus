CREATE TABLE IF NOT EXISTS ingress_events (
    event_id BIGSERIAL PRIMARY KEY,
    event_key TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    instance_name TEXT NOT NULL,
    raw_payload JSONB NOT NULL,
    raw_sha256 CHAR(64) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inbound_messages (
    message_id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES ingress_events(event_id),
    provider TEXT NOT NULL DEFAULT 'evolution',
    instance_name TEXT NOT NULL,
    group_id TEXT NOT NULL,
    group_name TEXT,
    provider_message_id TEXT NOT NULL,
    sender_id TEXT,
    sender_name TEXT,
    message_timestamp TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expected_attachments INTEGER NOT NULL DEFAULT 0 CHECK(expected_attachments >= 0),
    arrival_sequence BIGSERIAL NOT NULL,
    UNIQUE(provider, instance_name, group_id, provider_message_id)
);

CREATE TABLE IF NOT EXISTS ticket_documents (
    document_id BIGSERIAL PRIMARY KEY,
    message_id BIGINT NOT NULL REFERENCES inbound_messages(message_id),
    attachment_index INTEGER NOT NULL,
    original_filename TEXT,
    mime_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK(size_bytes >= 0),
    sha256 CHAR(64) NOT NULL,
    visual_hash TEXT,
    object_key TEXT NOT NULL,
    status TEXT NOT NULL,
    duplicate_of BIGINT REFERENCES ticket_documents(document_id),
    duplicate_reason TEXT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(message_id, attachment_index)
);
CREATE INDEX IF NOT EXISTS ticket_documents_sha_idx ON ticket_documents(sha256, size_bytes);
CREATE INDEX IF NOT EXISTS ticket_documents_visual_idx ON ticket_documents(visual_hash) WHERE visual_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS ticket_documents_status_idx ON ticket_documents(status);

CREATE TABLE IF NOT EXISTS ticket_state_events (
    state_event_id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES ticket_documents(document_id),
    previous_status TEXT,
    new_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL UNIQUE REFERENCES ticket_documents(document_id),
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS processing_jobs_ready_idx ON processing_jobs(status, available_at);

CREATE TABLE IF NOT EXISTS ticket_extractions (
    extraction_id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES ticket_documents(document_id),
    attempt INTEGER NOT NULL,
    document_type TEXT,
    ticket_date DATE,
    amount_cents BIGINT,
    identifier_type TEXT,
    identifier_value TEXT,
    full_name TEXT,
    tax_id TEXT,
    origin_bank TEXT,
    destination_account_key TEXT,
    observations TEXT,
    ocr_text TEXT NOT NULL,
    confidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    extractor_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id, attempt)
);

CREATE TABLE IF NOT EXISTS action_outbox (
    action_id BIGSERIAL PRIMARY KEY,
    document_id BIGINT REFERENCES ticket_documents(document_id),
    action_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    approval_status TEXT NOT NULL DEFAULT 'BLOCKED_SHADOW',
    delivery_status TEXT NOT NULL DEFAULT 'NOT_SENT',
    attempts INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL UNIQUE,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ
);

CREATE OR REPLACE FUNCTION prevent_append_only_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only table';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ingress_events_no_update ON ingress_events;
CREATE TRIGGER ingress_events_no_update BEFORE UPDATE OR DELETE ON ingress_events
FOR EACH ROW EXECUTE FUNCTION prevent_append_only_mutation();

DROP TRIGGER IF EXISTS state_events_no_update ON ticket_state_events;
CREATE TRIGGER state_events_no_update BEFORE UPDATE OR DELETE ON ticket_state_events
FOR EACH ROW EXECUTE FUNCTION prevent_append_only_mutation();
