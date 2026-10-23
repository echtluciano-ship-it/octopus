from __future__ import annotations

import argparse
import json

from service.gmail import queue_email, send_action


ERIKA = "oficinaoctopus13@gmail.com"
SUBJECT = "PRUEBA DEL SISTEMA OCTOPUS - TICKETS - 20 comprobantes"
BODY = """Hola Érika,

Te envío una prueba del sistema OCTOPUS - Tickets realizada sobre los 20 comprobantes que nos compartiste.

Resultado automático:
- 20 comprobantes recibidos y reconciliados
- 8 procesados automáticamente
- 11 enviados a REVIEW por datos que no pudieron determinarse con certeza
- 1 cuenta receptora no reconocida
- 0 comprobantes perdidos
- 0 duplicados
- 0 errores de procesamiento

El ZIP adjunto contiene los 20 comprobantes originales, las planillas generadas y el control completo con la trazabilidad de cada archivo.

La idea es que lo compares con tu trabajo manual y nos indiques qué interpretó correctamente y qué deberíamos ajustar.

Gracias,
Luciano

PRUEBA DEL SISTEMA OCTOPUS - TICKETS
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="OCTOPUS Tickets Gmail outbox")
    subparsers = parser.add_subparsers(dest="command", required=True)
    queue = subparsers.add_parser("queue-erika-test")
    queue.add_argument("attachment")
    send = subparsers.add_parser("send")
    send.add_argument("action_id", type=int)
    args = parser.parse_args()

    if args.command == "queue-erika-test":
        action_id = queue_email(
            recipient=ERIKA,
            subject=SUBJECT,
            body=BODY,
            attachments=[args.attachment],
            idempotency_key="email:erika:erika-20-2026-10-23:v1",
        )
        print(json.dumps({"action_id": action_id, "status": "QUEUED"}))
    else:
        print(json.dumps(send_action(args.action_id)))


if __name__ == "__main__":
    main()
