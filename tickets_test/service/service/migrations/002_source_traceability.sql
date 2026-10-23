ALTER TABLE ticket_documents
    ADD COLUMN IF NOT EXISTS source_system TEXT,
    ADD COLUMN IF NOT EXISTS source_document_id TEXT,
    ADD COLUMN IF NOT EXISTS source_url TEXT,
    ADD COLUMN IF NOT EXISTS source_batch TEXT;

CREATE INDEX IF NOT EXISTS ticket_documents_source_idx
    ON ticket_documents(source_system, source_document_id)
    WHERE source_document_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ticket_documents_source_batch_idx
    ON ticket_documents(source_batch, document_id)
    WHERE source_batch IS NOT NULL;
