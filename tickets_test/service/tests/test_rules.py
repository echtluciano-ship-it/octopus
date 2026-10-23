from __future__ import annotations

import unittest

from service.extract import parse
from service.ingest import ingest
from service.workflow import classify


CONFIG = {
    "accounts": [
        {
            "key": "principal",
            "destination_identifiers": [{"kind": "cvu", "value": "0000155300000000005630"}],
            "amount_validation": None,
        },
        {
            "key": "secondary",
            "destination_identifiers": [{"kind": "cbu", "value": "0270100010059700620013"}],
            "amount_validation": {"max_exclusive_cents": 500_000_000},
        },
    ],
    "accepted_deposit_banks": ["Banco Macro", "Banco Comafi"],
}


class ExtractionRulesTests(unittest.TestCase):
    def test_connection_updates_do_not_enter_the_ticket_inbox(self) -> None:
        result = ingest({"event": "connection.update", "instance": "test"})
        self.assertFalse(result["ticket"])
        self.assertFalse(result["event_inserted"])
        self.assertIsNone(result["event_id"])

    def test_identifier_priority_prefers_operation(self) -> None:
        result = parse(
            """Comprobante de transferencia
            Fecha: 21/10/2026
            Monto: $ 1.234.567,89
            Numero de operacion: OPERA123456
            Numero de comprobante: COMP987654
            ID Coelsa: COELSA9999
            Nombre y apellido: Persona Prueba
            CUIT: 20-12345678-9
            Banco: Banco Galicia
            Destino 0000155300000000005630""",
            CONFIG,
        )
        self.assertEqual(result["identifier_type"], "operation_number")
        self.assertEqual(result["identifier_value"], "OPERA123456")
        self.assertEqual(result["amount_cents"], 123_456_789)
        self.assertEqual(result["destination_account_key"], "principal")

    def test_amount_never_selects_or_rejects_destination_account(self) -> None:
        extraction = {
            "document_type": "transfer",
            "amount_cents": 500_000_000,
            "destination_account_key": "secondary",
            "account_matches": ["secondary"],
            "missing_fields": [],
        }
        status, reason = classify(extraction, CONFIG)
        self.assertEqual(status, "READY_FOR_SHEET")
        self.assertNotIn("monto", reason.lower())

    def test_large_amount_is_valid_when_actual_destination_is_identified(self) -> None:
        extraction = {
            "document_type": "transfer",
            "amount_cents": 5_000_000_000,
            "destination_account_key": "secondary",
            "account_matches": ["secondary"],
            "missing_fields": [],
        }
        status, _ = classify(extraction, CONFIG)
        self.assertEqual(status, "READY_FOR_SHEET")

    def test_unknown_destination_is_not_discarded(self) -> None:
        extraction = {
            "document_type": "transfer",
            "amount_cents": 100_000_000,
            "destination_account_key": None,
            "account_matches": [],
            "missing_fields": [],
        }
        status, _ = classify(extraction, CONFIG)
        self.assertEqual(status, "WRONG_ACCOUNT_REVIEW")

    def test_sender_fields_are_taken_from_origin_not_destination(self) -> None:
        result = parse(
            """Comprobante de transferencia
            Importe $ 670.145,5
            Fecha de ejecucion 20/10/2026
            Numero de comprobante 94628396
            Datos de quien recibe la transferencia
            Nombre o razon social COBROS JMC SA
            CUIT 30-71873171-9
            CBU 0000155300000000005630
            Datos de quien realizo la transferencia
            Nombre o razon social CURMONA A Y TESSIO A SS
            CUIT 30-71538573-9
            Banco Santander""",
            CONFIG,
        )
        self.assertEqual(result["amount_cents"], 67_014_550)
        self.assertEqual(result["full_name"], "CURMONA A Y TESSIO A SS")
        self.assertEqual(result["tax_id"], "30-71538573-9")

    def test_spanish_month_date_and_thousands_only_amount(self) -> None:
        result = parse(
            """Mercado Pago
            Comprobante de transferencia
            21/octubre/2026 a las 8:42
            $ 2.259.300
            Origen y destino
            Pablo Andres Machado
            CUIT/CUIL 20-29409329-0
            Cobros Jmc Sa
            CVU 0000155300000000005630
            N. de operacion 184278863117""",
            CONFIG,
        )
        self.assertEqual(result["ticket_date"].isoformat(), "2026-10-21")
        self.assertEqual(result["amount_cents"], 225_930_000)
        self.assertEqual(result["identifier_value"], "184278863117")

    def test_spanish_date_with_de_separators(self) -> None:
        result = parse(
            """DUPONDIO
            Transferencia enviada
            10 de Junio de 2026 11:48hs
            ARS $ 2.745.000,00
            De
            Li Lan
            27-93931913-7
            Para
            Verne It Group
            CBU/CVU: 0000357301000003710039
            Referencia 7A84D56A8557680""",
            CONFIG,
        )
        self.assertEqual(result["ticket_date"].isoformat(), "2026-06-10")
        self.assertEqual(result["origin_bank"], "Dupondio")
        self.assertEqual(result["destination_identifiers_seen"], ["0000357301000003710039"])

    def test_visible_unknown_destination_precedes_missing_identifier_review(self) -> None:
        extracted = parse(
            """DUPONDIO
            Transferencia enviada
            10 de Junio de 2026
            ARS $ 2.745.000,00
            De
            Li Lan
            27-93931913-7
            Para
            Verne It Group
            CBU/CVU: 0000357301000003710039""",
            CONFIG,
        )
        self.assertIn("identifier_value", extracted["missing_fields"])
        status, _ = classify(extracted, CONFIG)
        self.assertEqual(status, "WRONG_ACCOUNT_REVIEW")

    def test_us_separators_are_supported(self) -> None:
        result = parse(
            """Transferencia a terceros Otro Banco
            Numero de Operacion 274053828
            Fecha y hora 20/10/2026
            Ordenante
            ARGENTINA DISTRIBUCIONES SA
            CUIT/CUIL 30711633983
            Importe $ 7,640,400.00
            CBU/CVU destino 0000155300000000005630""",
            CONFIG,
        )
        self.assertEqual(result["amount_cents"], 764_040_000)
        self.assertEqual(result["full_name"], "ARGENTINA DISTRIBUCIONES SA")

    def test_bna_sender_is_not_replaced_by_recipient(self) -> None:
        result = parse(
            """Transferencia Inmediata
            Monto $ 873.234,00
            De:
            Apellido y Nombre
            TORRENS SELENE
            CUIT/CUIL 27445193386
            Para:
            Apellido y Nombre COBROS JMC SA
            CUIT/CUIL 30718731719
            CBU/CVU 0000155300000000005630
            Numero de operacion 46YGOW9MGVY4RP1Q9EXD8J
            20/10/2026""",
            CONFIG,
        )
        self.assertEqual(result["full_name"], "TORRENS SELENE")
        self.assertEqual(result["tax_id"], "27-44519338-6")

    def test_destination_only_receipt_does_not_invent_sender(self) -> None:
        result = parse(
            """Transferencia
            Destinatario COBROS JMC SA
            CUIT 30718731719
            Monto $1.000.000,00
            Alias ogro.prenda.catre
            Numero de transaccion 74K6DVNOP4G561R195J8LQ
            Fecha 21/10/2026""",
            CONFIG,
        )
        self.assertIsNone(result["full_name"])
        self.assertIsNone(result["tax_id"])

    def test_asterisk_operation_and_receipt_labels(self) -> None:
        operation = parse(
            """Transferencia enviada $ 3.000.000
            21/10/2026
            Envia NIVALDO JAVIER BAHAMONDE
            CUIT 20-93752096-5
            N* de operacion 43220860366
            CVU 0000155300000000005630
            Banco Galicia""",
            CONFIG,
        )
        receipt = parse(
            """Comprobante de transferencia
            Importe debitado $ 1.720.500,00
            Fecha de ejecucion 20/10/2026
            N* comprobante 95034943
            Cuenta destino 0000155300000000005630""",
            CONFIG,
        )
        self.assertEqual(operation["identifier_value"], "43220860366")
        self.assertEqual(receipt["identifier_value"], "95034943")

    def test_ambiguous_currency_symbol_is_not_used_as_amount(self) -> None:
        result = parse(
            """Comprobante de transferencia
            Enviaste
            51.348.800
            21/OCT/2026
            Cuenta origen Silvia Nelida Carranza
            CUIL 27-12640480-3
            Cuenta destino Cobros Jmc Sa
            CVU 0000155300000000005630""",
            CONFIG,
        )
        self.assertIsNone(result["amount_cents"])
        self.assertEqual(result["ticket_date"].isoformat(), "2026-10-21")

    def test_damaged_uuid_candidate_is_skipped(self) -> None:
        result = parse(
            """Comprobante de transferencia
            $58/.502
            Id. Op. 5083fdf-d868-5156-9b51-d840bcaedacc
            Comprobante de transferencia
            $587,502
            Id. Op. 5083f1df-d868-5156-9b51-d840bcaedacc""",
            CONFIG,
        )
        self.assertEqual(result["identifier_value"], "5083f1df-d868-5156-9b51-d840bcaedacc")

    def test_sender_after_standalone_de_label(self) -> None:
        result = parse(
            """Comprobante de transferencia
            Importe $617.355,00
            Numero de operacion 854273698
            Fecha y hora 19/10/2026
            ES) De
            CHEN MEIFENG
            CUIT: 27954831774
            ES) Para
            COBROS JMC SA
            CUIT: 30718731719
            CBU/CVU: 0000155300000000005630
            PVS""",
            CONFIG,
        )
        self.assertEqual(result["full_name"], "CHEN MEIFENG")
        self.assertEqual(result["tax_id"], "27-95483177-4")

    def test_check_is_manual_review(self) -> None:
        status, _ = classify(
            {"document_type": "check", "missing_fields": [], "account_matches": []}, CONFIG
        )
        self.assertEqual(status, "CHECK_REVIEW")


if __name__ == "__main__":
    unittest.main()
