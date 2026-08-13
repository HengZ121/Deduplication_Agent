#!/usr/bin/env python3
"""Tests for the multi-frame procedure sentence report."""

from __future__ import annotations

import json
import unittest
import uuid
import zipfile
from pathlib import Path

from count_framenet_candidates import Candidate
from find_multi_frame_sentences import find_multi_frame_sentences, match_candidate_frames


class MultiFrameSentenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = {
            "review": [Candidate("Inspecting", 1, "review.v", "v")],
            "determine": [
                Candidate("Deciding", 2, "determine.v", "v"),
                Candidate("Coming_to_believe", 3, "determine.v", "v"),
            ],
            "submit": [Candidate("Submitting_documents", 4, "submit.v", "v")],
        }

    def test_matches_distinct_frames_and_preserves_lu_evidence(self) -> None:
        frames = match_candidate_frames("Officers review and determine claims.", self.index)
        self.assertEqual(
            ["Coming_to_believe", "Deciding", "Inspecting"],
            [frame["frame"] for frame in frames],
        )
        self.assertEqual(["determine.v"], frames[0]["lexicalUnits"])

    def test_report_keeps_only_multiple_frames_and_groups_duplicates(self) -> None:
        # The managed Windows workspace disallows Python-created temporary
        # directories, so disposable files live in the existing output folder.
        root = Path.cwd() / "outputs"
        stem = f"_test_multi_frame_{uuid.uuid4().hex}"
        archive_path = root / f"{stem}.zip"
        csv_path = root / f"{stem}.csv"
        json_path = root / f"{stem}.json"
        try:
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "one.txt",
                    "Officers review and determine claims. Clients submit documents.",
                )
                archive.writestr("two.txt", "Officers review and determine claims.")

            summary = find_multi_frame_sentences(
                archive_path,
                csv_path,
                json_path,
                lu_index=self.index,
            )
            payload = json.loads(json_path.read_text(encoding="utf-8"))

            self.assertEqual(1, summary["uniqueSentencesWithMultipleFrames"])
            self.assertEqual(2, payload["sentences"][0]["occurrenceCount"])
            self.assertEqual(["one.txt", "two.txt"], payload["sentences"][0]["sourceDocuments"])
            self.assertTrue(csv_path.exists())
        finally:
            for path in (archive_path, csv_path, json_path):
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
