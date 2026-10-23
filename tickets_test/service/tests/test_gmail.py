from __future__ import annotations

import base64
import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from service import gmail


class GmailTests(unittest.TestCase):
    def test_attachment_must_stay_under_configured_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "packages"
            root.mkdir()
            inside = root / "test.zip"
            inside.write_bytes(b"zip")
            outside = base / "outside.zip"
            outside.write_bytes(b"other")
            with patch.object(gmail, "settings", SimpleNamespace(gmail_attachment_root=root)):
                self.assertTrue(gmail.attachment_evidence(inside)["sha256"])
                with self.assertRaises(ValueError):
                    gmail.attachment_evidence(outside)

    def test_build_message_preserves_attachment_and_message_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attachment = root / "tickets.zip"
            attachment.write_bytes(b"contents")
            fake_settings = SimpleNamespace(gmail_attachment_root=root)
            with patch.object(gmail, "settings", fake_settings):
                evidence = gmail.attachment_evidence(attachment)
                payload = {
                    "recipient": "oficinaoctopus13@gmail.com",
                    "subject": "Test",
                    "body": "Body",
                    "attachments": [evidence],
                }
                first = gmail.build_message(payload, "same-key")
                second = gmail.build_message(payload, "same-key")

            self.assertEqual(first["Message-ID"], second["Message-ID"])
            self.assertEqual(first["To"], "oficinaoctopus13@gmail.com")
            self.assertEqual(next(first.iter_attachments()).get_payload(decode=True), b"contents")

    def test_gmail_raw_message_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attachment = root / "tickets.zip"
            attachment.write_bytes(b"contents")
            fake_settings = SimpleNamespace(gmail_attachment_root=root)
            with patch.object(gmail, "settings", fake_settings):
                payload = {
                    "recipient": "oficinaoctopus13@gmail.com",
                    "subject": "Test",
                    "body": "Body",
                    "attachments": [gmail.attachment_evidence(attachment)],
                }
                message = gmail.build_message(payload, "key")
            raw = base64.urlsafe_b64encode(message.as_bytes())
            parsed = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw))

            self.assertEqual(parsed["Subject"], "Test")
            self.assertEqual(len(list(parsed.iter_attachments())), 1)


if __name__ == "__main__":
    unittest.main()
