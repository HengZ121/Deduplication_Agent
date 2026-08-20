#!/usr/bin/env python3
"""Tests for targeted Verification-frame CSV generation."""

from __future__ import annotations

import unittest

from generate_verification_frame_csv import select_verification_texts
from hybrid_frame_mapper import hybrid_frame_mapping


class VerificationFrameCsvTests(unittest.TestCase):
    def test_targeted_mapping_keeps_competing_frames(self) -> None:
        event = hybrid_frame_mapping(
            "The officer verifies the claimant's identity using the document on file.",
            0,
            use_bert=False,
            target_frame="Verification",
        )

        self.assertIsNotNone(event)
        self.assertEqual("Verification", event["frame"])
        self.assertEqual("target_frame", event["hybridScoring"]["selectionMode"])
        frames = {item["frame"] for item in event["hybridScoring"]["candidateFrames"]}
        self.assertIn("Verification", frames)
        self.assertIn("Evidence", frames)
        self.assertIn("Scrutiny", frames)
        self.assertEqual("The officer", event["frameElements"]["Inspector"]["text"])

        imperative = hybrid_frame_mapping(
            "Verify the payment destination with the client.",
            1,
            use_bert=False,
            target_frame="Verification",
        )
        self.assertIsNone(imperative["frameElements"]["Inspector"]["text"])

    def test_selector_requires_official_verification_lu(self) -> None:
        rows = [
            {
                "sentence": f"The officer verifies claimant information in record number {index} before processing.",
                "rawFrames": "Evidence; Verification",
                "status": "canonical_frame",
                "rawFrameCount": str(index + 2),
            }
            for index in range(3)
        ]
        rows.append(
            {
                "sentence": "The officer reviews the claimant information before processing.",
                "rawFrames": "Scrutiny; Verification",
                "status": "canonical_frame",
                "rawFrameCount": "1",
            }
        )

        selected = select_verification_texts(rows, sample_size=3)

        self.assertEqual(3, len(selected))
        self.assertTrue(all("verifies" in row["sentence"] for row in selected))


if __name__ == "__main__":
    unittest.main()
