#!/usr/bin/env python3
"""Tests for the generic procedure/DITA deduplication runner."""

from __future__ import annotations

import unittest
from pathlib import Path

from run_procedure_pipeline import language_family, read_documents


class DitaDocumentLoaderTests(unittest.TestCase):
    def test_map_topics_and_common_note_conref_become_one_document(self) -> None:
        dataset_root = Path(__file__).parent / "test_fixtures" / "kmt_dita"

        documents, detected_format = read_documents(dataset_root)

        self.assertEqual("dita", detected_format)
        self.assertEqual(1, len(documents))
        document = documents[0]
        self.assertEqual("KA-99999_EN/KA-99999.ditamap", document.path)
        self.assertEqual("en-CA", document.language)
        self.assertEqual("Action", document.document_type)
        self.assertEqual("2026-08-20", document.modified)
        self.assertIn("Short article summary.", document.summary)
        self.assertIn("Process the request.", document.text)
        self.assertIn("Reusable warning text.", document.text)

    def test_language_family_normalizes_dita_locale(self) -> None:
        self.assertEqual("en", language_family("en-CA"))
        self.assertEqual("fr", language_family("fr_CA"))

    def test_common_note_directory_loads_each_dita_file_as_one_node(self) -> None:
        common_notes = (
            Path(__file__).parent / "test_fixtures" / "kmt_dita" / "dita" / "common_notes"
        )

        documents, detected_format = read_documents(common_notes)

        self.assertEqual("dita-nodes", detected_format)
        self.assertEqual(1, len(documents))
        self.assertEqual("note.dita", documents[0].path)
        self.assertEqual("dita_common_node", documents[0].document_type)
        self.assertIn("Reusable warning text.", documents[0].text)


if __name__ == "__main__":
    unittest.main()
