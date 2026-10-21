from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TicketStatus(StrEnum):
    RECEIVED = "RECEIVED"
    ORIGINAL_STORED = "ORIGINAL_STORED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    EXTRACTED = "EXTRACTED"
    READY_FOR_SHEET = "READY_FOR_SHEET"
    SHEET_GENERATED = "SHEET_GENERATED"
    SHADOW_COMPARED = "SHADOW_COMPARED"
    DUPLICATE_CONFIRMED = "DUPLICATE_CONFIRMED"
    REVIEW = "REVIEW"
    WRONG_ACCOUNT_REVIEW = "WRONG_ACCOUNT_REVIEW"
    CHECK_REVIEW = "CHECK_REVIEW"
    ERROR_RETRYABLE = "ERROR_RETRYABLE"
    ERROR_FINAL = "ERROR_FINAL"


@dataclass(frozen=True)
class MessageInput:
    provider: str
    instance_id: str
    group_id: str
    group_name: str
    provider_message_id: str
    sender_id: str
    sender_name: str | None
    message_timestamp: str
    received_at: str
    raw_payload_json: str
    expected_attachments: int = 0


@dataclass(frozen=True)
class AttachmentInput:
    attachment_index: int
    original_filename: str | None
    mime_type: str
    size_bytes: int
    sha256: str
    object_uri: str
    visual_hash: str | None = None


@dataclass(frozen=True)
class IngestResult:
    message_id: int
    arrival_sequence: int
    inserted: bool
    document_ids: tuple[int, ...]
    exact_duplicate_ids: tuple[int, ...]
