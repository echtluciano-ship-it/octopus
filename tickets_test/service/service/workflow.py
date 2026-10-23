from __future__ import annotations

import json
import re
from typing import Any

from service.db import connection


TERMINAL_REVIEW = {"REVIEW", "WRONG_ACCOUNT_REVIEW", "CHECK_REVIEW"}


def _plain(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def classify(extracted: dict[str, Any], account_config: dict) -> tuple[str, str]:
    document_type = extracted.get("document_type")
    account_key = extracted.get("destination_account_key")
    if document_type == "check":
        return "CHECK_REVIEW", "Los cheques estan fuera del alcance inicial."
    if document_type not in {"transfer", "deposit"}:
        return "REVIEW", "No se pudo clasificar con certeza como transferencia o deposito."
    if extracted.get("missing_fields"):
        fields = ", ".join(extracted["missing_fields"])
        return "REVIEW", f"Campos obligatorios no determinados: {fields}."
    if document_type == "deposit":
        accepted = {_plain(value) for value in account_config.get("accepted_deposit_banks", [])}
        bank = _plain(extracted.get("origin_bank"))
        if not any(value and (value in bank or bank in value) for value in accepted):
            return "REVIEW", "Deposito dirigido a banco/cuenta no confirmado por Erika."
        return "READY_FOR_SHEET", "Deposito extraido con los campos obligatorios."
    if len(extracted.get("account_matches") or []) > 1:
        return "WRONG_ACCOUNT_REVIEW", "Mas de una cuenta destino coincide con el comprobante."
    if not account_key:
        return "WRONG_ACCOUNT_REVIEW", "No se identifico una cuenta receptora valida."
    account = next(
        (item for item in account_config.get("accounts", []) if item.get("key") == account_key),
        None,
    )
    if account is None:
        return "WRONG_ACCOUNT_REVIEW", "La cuenta detectada no existe en la configuracion vigente."
    return "READY_FOR_SHEET", "Transferencia extraida y cuenta receptora identificada."


def transition(
    conn,
    document_id: int,
    new_status: str,
    *,
    actor: str,
    reason: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    row = conn.execute(
        "SELECT status FROM ticket_documents WHERE document_id=%s FOR UPDATE", (document_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown ticket document {document_id}")
    previous = row["status"]
    conn.execute(
        "UPDATE ticket_documents SET status=%s,updated_at=now() WHERE document_id=%s",
        (new_status, document_id),
    )
    conn.execute(
        """INSERT INTO ticket_state_events(
             document_id,previous_status,new_status,actor,reason,evidence
           ) VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",
        (document_id, previous, new_status, actor, reason, json.dumps(evidence or {})),
    )


def queue_shadow_action(conn, document_id: int, status: str, reason: str) -> None:
    if status == "DUPLICATE_CONFIRMED":
        action_type = "WHATSAPP_REACT_DUPLICATE"
        emoji = "✖️"
    elif status == "WRONG_ACCOUNT_REVIEW":
        action_type = "WHATSAPP_REACT_WRONG_ACCOUNT"
        emoji = "❌"
    else:
        return
    conn.execute(
        """INSERT INTO action_outbox(document_id,action_type,payload,idempotency_key)
           VALUES (%s,%s,%s::jsonb,%s) ON CONFLICT(idempotency_key) DO NOTHING""",
        (
            document_id,
            action_type,
            json.dumps({"emoji": emoji, "reason": reason}),
            f"shadow:{action_type}:{document_id}",
        ),
    )


def record_duplicate_shadow_action(document_id: int, reason: str) -> None:
    with connection() as conn:
        queue_shadow_action(conn, document_id, "DUPLICATE_CONFIRMED", reason)
        conn.commit()
