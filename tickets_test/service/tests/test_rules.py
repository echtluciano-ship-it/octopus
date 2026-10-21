from __future__ import annotations

import unittest

from service.extract import parse
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

    def test_exact_five_million_remains_pending(self) -> None:
        extraction = {
            "document_type": "transfer",
            "amount_cents": 500_000_000,
            "destination_account_key": "secondary",
            "account_matches": ["secondary"],
            "missing_fields": [],
        }
        status, reason = classify(extraction, CONFIG)
        self.assertEqual(status, "REVIEW")
        self.assertIn("PENDING_RULE", reason)

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

    def test_check_is_manual_review(self) -> None:
        status, _ = classify(
            {"document_type": "check", "missing_fields": [], "account_matches": []}, CONFIG
        )
        self.assertEqual(status, "CHECK_REVIEW")


if __name__ == "__main__":
    unittest.main()
