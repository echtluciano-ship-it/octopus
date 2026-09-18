from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, PngImagePlugin

from source_identity import SourceDocument, find_exact_duplicate, identity_for_file


class SourceIdentityTests(unittest.TestCase):
    def test_same_business_operation_fields_do_not_make_a_duplicate(self) -> None:
        first = SourceDocument(
            drive_id="drive-a",
            file_name="first.jpg",
            sha256="sha-a",
            visual_sha256="pixels-a",
            operation_ref="Comite Ejecutivo|2026-09-17|1000000|50000",
        )
        second = SourceDocument(
            drive_id="drive-b",
            file_name="second.jpg",
            sha256="sha-b",
            visual_sha256="pixels-b",
            operation_ref="Comite Ejecutivo|2026-09-17|1000000|50000",
        )

        self.assertIsNone(find_exact_duplicate(second, [first]))

    def test_same_drive_id_is_a_duplicate(self) -> None:
        first = SourceDocument(drive_id="drive-a", file_name="first.jpg")
        second = SourceDocument(drive_id="drive-a", file_name="renamed.jpg")

        evidence = find_exact_duplicate(second, [first])

        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.reason, "SAME_DRIVE_ID")

    def test_same_sha256_is_a_duplicate(self) -> None:
        first = SourceDocument(drive_id="drive-a", file_name="first.jpg", sha256="same")
        second = SourceDocument(drive_id="drive-b", file_name="second.jpg", sha256="same")

        evidence = find_exact_duplicate(second, [first])

        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.reason, "SAME_SHA256")

    def test_identical_pixels_are_duplicate_even_when_file_bytes_differ(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_path = root / "first.png"
            second_path = root / "second.png"
            image = Image.new("RGB", (4, 4), color=(18, 52, 86))
            image.save(first_path)
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text("trace", "different-file-bytes")
            image.save(second_path, pnginfo=metadata)

            first = identity_for_file(first_path, drive_id="drive-a")
            second = identity_for_file(second_path, drive_id="drive-b")
            evidence = find_exact_duplicate(second, [first])

            self.assertNotEqual(first.sha256, second.sha256)
            self.assertEqual(first.visual_sha256, second.visual_sha256)
            self.assertIsNotNone(evidence)
            self.assertEqual(evidence.reason, "IDENTICAL_DECODED_PIXELS")


if __name__ == "__main__":
    unittest.main()
