PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS inbound_messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    group_name TEXT NOT NULL,
    provider_message_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    sender_name TEXT,
    message_timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL,
    expected_attachments INTEGER NOT NULL CHECK(expected_attachments >= 0),
    raw_payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(provider, instance_id, group_id, provider_message_id)
);

CREATE TABLE IF NOT EXISTS ticket_documents (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES inbound_messages(message_id),
    attachment_index INTEGER NOT NULL,
    original_filename TEXT,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
    sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
    visual_hash TEXT,
    object_uri TEXT NOT NULL,
    status TEXT NOT NULL,
    duplicate_of INTEGER REFERENCES ticket_documents(document_id),
    duplicate_reason TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(message_id, attachment_index)
);

CREATE INDEX IF NOT EXISTS idx_documents_sha256
ON ticket_documents(sha256, size_bytes);

CREATE INDEX IF NOT EXISTS idx_documents_visual_hash
ON ticket_documents(visual_hash) WHERE visual_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS ticket_state_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES ticket_documents(document_id),
    previous_status TEXT,
    new_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_extractions (
    extraction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES ticket_documents(document_id),
    attempt INTEGER NOT NULL,
    document_type TEXT,
    ticket_date TEXT,
    amount_cents INTEGER,
    identifier_type TEXT,
    identifier_value TEXT,
    full_name TEXT,
    tax_id TEXT,
    origin_bank TEXT,
    destination_account_key TEXT,
    observations TEXT,
    confidence_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(document_id, attempt)
);

CREATE TABLE IF NOT EXISTS duplicate_evidence (
    duplicate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES ticket_documents(document_id),
    candidate_document_id INTEGER NOT NULL REFERENCES ticket_documents(document_id),
    evidence_type TEXT NOT NULL,
    evidence_value TEXT NOT NULL,
    strength TEXT NOT NULL,
    decision TEXT NOT NULL,
    decided_by TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(document_id, candidate_document_id, evidence_type, evidence_value)
);

CREATE TABLE IF NOT EXISTS close_batches (
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(window_start, window_end)
);

CREATE TABLE IF NOT EXISTS close_batch_items (
    batch_id INTEGER NOT NULL REFERENCES close_batches(batch_id),
    document_id INTEGER NOT NULL REFERENCES ticket_documents(document_id),
    arrival_position INTEGER NOT NULL,
    PRIMARY KEY(batch_id, document_id),
    UNIQUE(batch_id, arrival_position)
);

CREATE TABLE IF NOT EXISTS shadow_comparisons (
    comparison_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES close_batches(batch_id),
    metric TEXT NOT NULL,
    automatic_value TEXT NOT NULL,
    manual_value TEXT NOT NULL,
    matches INTEGER NOT NULL CHECK(matches IN (0, 1)),
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_outbox (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER REFERENCES ticket_documents(document_id),
    action_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    approval_status TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL UNIQUE,
    last_error TEXT,
    created_at TEXT NOT NULL,
    delivered_at TEXT
);

CREATE TRIGGER IF NOT EXISTS inbound_messages_no_update
BEFORE UPDATE ON inbound_messages BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS inbound_messages_no_delete
BEFORE DELETE ON inbound_messages BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS state_events_no_update
BEFORE UPDATE ON ticket_state_events BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS state_events_no_delete
BEFORE DELETE ON ticket_state_events BEGIN SELECT RAISE(ABORT, 'append-only'); END;
