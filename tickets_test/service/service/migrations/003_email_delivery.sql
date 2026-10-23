ALTER TABLE action_outbox
    ADD COLUMN IF NOT EXISTS provider_message_id TEXT;

CREATE INDEX IF NOT EXISTS action_outbox_email_delivery_idx
    ON action_outbox(action_type, approval_status, delivery_status, created_at);
