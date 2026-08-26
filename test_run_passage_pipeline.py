#!/usr/bin/env python3
"""Tests for sentence-window DITA duplicate detection."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from run_passage_pipeline import (
    initial_cross_encoder_decision,
    read_dita_passage_windows,
    sentence_windows,
    split_sentences,
)


class PassageWindowTests(unittest.TestCase):
    def test_sentence_windows_overlap_and_never_exceed_five_sentences(self) -> None:
        sentences = [f"Sentence {number}." for number in range(1, 8)]

        windows = list(sentence_windows(sentences, max_sentences=5))

        self.assertEqual(3, len(windows))
        self.assertEqual((0, 5), windows[0][:2])
        self.assertEqual((2, 7), windows[-1][:2])
        self.assertTrue(all(end - start <= 5 for start, end, _ in windows))

    def test_sentence_splitter_preserves_decimal_and_french_abbreviation(self) -> None:
        sentences = split_sentences("Le taux est 2.5 %. P. ex. utilisez ce calcul. Continuez ensuite.")

        self.assertEqual(3, len(sentences))
        self.assertIn("2.5", sentences[0])
        self.assertTrue(sentences[1].startswith("P. ex."))

    def test_fixture_passages_keep_source_location_and_conref_signal(self) -> None:
        dataset_root = Path(__file__).parent / "test_fixtures" / "kmt_dita"

        passages = read_dita_passage_windows(dataset_root, max_sentences=5, min_words=1)

        self.assertGreaterEqual(len(passages), 3)
        reusable = next(passage for passage in passages if "Reusable warning text." in passage.text)
        self.assertEqual("KA-99999_EN/KA-99999.ditamap", reusable.article_path)
        self.assertEqual("info", reusable.block_type)
        self.assertTrue(reusable.contains_conref)
        self.assertIn("common_notes/note.dita#note/body", reusable.conref_targets)


class PassageRelationshipTests(unittest.TestCase):
    def test_identical_text_is_automatic_duplicate(self) -> None:
        row = pd.Series(
            {
                "item1_text": "Submit the request to the processing team.",
                "item2_text": "Submit the request to the processing team.",
                "cross_encoder_score": 0.999,
                "embedding_similarity": 1.0,
            }
        )

        relationship, _, borderline = initial_cross_encoder_decision(row, 0.995, 0.90)

        self.assertEqual("duplicate/semantic duplicate", relationship)
        self.assertFalse(borderline)

    def test_low_cross_encoder_score_is_automatic_independent(self) -> None:
        row = pd.Series(
            {
                "item1_text": "Submit a death-benefit request to the processing team.",
                "item2_text": "Update a disability-benefit contact in another system.",
                "cross_encoder_score": 0.40,
                "embedding_similarity": 0.73,
            }
        )

        relationship, _, borderline = initial_cross_encoder_decision(row, 0.995, 0.90)

        self.assertEqual("independent", relationship)
        self.assertFalse(borderline)

    def test_number_difference_forces_high_score_pair_to_borderline_review(self) -> None:
        row = pd.Series(
            {
                "item1_text": "Apply a recovery rate of 10 percent to the same account.",
                "item2_text": "Apply a recovery rate of 20 percent to the same account.",
                "cross_encoder_score": 0.999,
                "embedding_similarity": 0.99,
            }
        )

        _, _, borderline = initial_cross_encoder_decision(row, 0.995, 0.90)

        self.assertTrue(borderline)


if __name__ == "__main__":
    unittest.main()
