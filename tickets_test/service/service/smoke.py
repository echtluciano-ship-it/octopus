from __future__ import annotations

import base64
import io
import os
import time
from datetime import datetime, timezone

import requests
from PIL import Image, ImageDraw, ImageFont

from service.config import settings


def image_bytes() -> bytes:
    account = settings.account_config()["accounts"][0]
    identifier = account["destination_identifiers"][0]["value"]
    lines = (
        "COMPROBANTE DE TRANSFERENCIA",
        "Fecha: 21/10/2026",
        "Monto: $ 1.234.567,89",
        "Numero de operacion: OCTTEST987654",
        "Nombre y apellido: PERSONA PRUEBA",
        "CUIT: 20-12345678-9",
        "Banco: Banco Galicia",
        f"Cuenta destino: {identifier}",
    )
    image = Image.new("RGB", (1600, 1050), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    for index, line in enumerate(lines):
        draw.text((70, 70 + index * 110), line, fill="black", font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def payload(message_id: str, content: bytes) -> dict:
    return {
        "event": "messages.upsert",
        "instance": "octopus-tickets-test",
        "data": {
            "key": {
                "remoteJid": "120363000000000000@g.us",
                "id": message_id,
                "participant": "5491100000000@s.whatsapp.net",
            },
            "pushName": "OCTOPUS TEST",
            "messageTimestamp": int(datetime.now(timezone.utc).timestamp()),
            "message": {
                "imageMessage": {"mimetype": "image/png", "fileName": "ticket-test.png"},
                "base64": base64.b64encode(content).decode("ascii"),
            },
        },
    }


def main() -> None:
    api = os.getenv("TICKETS_SMOKE_API", "http://localhost:8000")
    headers = {"X-Octopus-Webhook-Token": settings.webhook_token}
    content = image_bytes()
    stamp = str(int(time.time()))
    recoverable_payload = payload(f"SMOKE-{stamp}-A", content)
    recoverable_payload["data"]["message"].pop("base64")
    failed = requests.post(
        f"{api}/webhooks/evolution",
        json=recoverable_payload,
        headers=headers,
        timeout=30,
    )
    if failed.status_code != 503:
        raise RuntimeError(f"Expected durable retry response, got {failed.status_code}: {failed.text}")
    failed_audit = requests.get(f"{api}/audit/reconciliation", timeout=10).json()
    if failed_audit["ingest_errors"] < 1 or failed_audit["status"] != "OK":
        raise RuntimeError(f"Early ingestion failure was not reconciled: {failed_audit}")
    first = requests.post(
        f"{api}/webhooks/evolution",
        json=payload(f"SMOKE-{stamp}-A", content),
        headers=headers,
        timeout=30,
    )
    first.raise_for_status()
    deadline = time.time() + 90
    while time.time() < deadline:
        audit = requests.get(f"{api}/audit/reconciliation", timeout=10).json()
        if audit["processed"] + audit["review"] + audit["errors"] >= 1:
            break
        time.sleep(2)
    second = requests.post(
        f"{api}/webhooks/evolution",
        json=payload(f"SMOKE-{stamp}-B", content),
        headers=headers,
        timeout=30,
    )
    second.raise_for_status()
    audit = requests.get(f"{api}/audit/reconciliation", timeout=10).json()
    if (
        audit["documents_stored"] < 2
        or audit["duplicates"] < 1
        or audit["ingest_errors"] != 0
        or audit["status"] != "OK"
    ):
        raise RuntimeError(f"Smoke test did not reconcile: {audit}")
    print(
        {
            "failed_delivery_reconciled": failed_audit,
            "first": first.json(),
            "second": second.json(),
            "audit": audit,
        }
    )


if __name__ == "__main__":
    main()
