#!/usr/bin/env python3
"""Tests for sentence-window DITA duplicate detection."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from run_passage_pipeline import (
    initial_cross_encoder_decision,
    is_cluster_relationship,
    normalized_passage,
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
    def test_unicode_apostrophe_variants_normalize_to_identical_text(self) -> None:
        self.assertEqual(
            normalized_passage("Le paiement n’est pas disponible."),
            normalized_passage("Le paiement n＇est pas disponible."),
        )
        self.assertEqual(
            normalized_passage("La demande n'est pas complète."),
            normalized_passage("La demande n ’est pas complète."),
        )

    def test_compatibility_width_dash_and_zero_width_mark_are_ignored(self) -> None:
        self.assertEqual(
            normalized_passage("Ｍise-à-jour du dossier"),
            normalized_passage("Mise‑à‑jour\u200b du dossier"),
        )

    def test_identical_text_is_automatic_exact_content(self) -> None:
        row = pd.Series(
            {
                "item1_text": "Submit the request to the processing team.",
                "item2_text": "Submit the request to the processing team.",
                "cross_encoder_score": 0.999,
                "embedding_similarity": 1.0,
            }
        )

        relationship, _, borderline = initial_cross_encoder_decision(row, 0.995, 0.90)

        self.assertEqual("exact content", relationship)
        self.assertFalse(borderline)

    def test_strong_scores_on_different_text_are_a_variant_not_exact(self) -> None:
        row = pd.Series(
            {
                "item1_text": "The agent must review the ROE and the existing records of decision on file.",
                "item2_text": "The officer must review the ROE and the existing records of decision on file.",
                "cross_encoder_score": 0.999,
                "embedding_similarity": 0.98,
            }
        )

        relationship, _, borderline = initial_cross_encoder_decision(row, 0.995, 0.90)

        self.assertEqual("variant candidate", relationship)
        self.assertFalse(borderline)

    def test_new_and_legacy_labels_that_form_clusters(self) -> None:
        self.assertTrue(is_cluster_relationship("exact content"))
        self.assertTrue(is_cluster_relationship("variant candidate"))
        self.assertTrue(is_cluster_relationship("duplicate/semantic duplicate"))
        self.assertFalse(is_cluster_relationship("partial overlap"))
        self.assertFalse(is_cluster_relationship("conflicting information"))
        self.assertFalse(is_cluster_relationship("related"))

    def test_low_cross_encoder_score_is_automatic_related(self) -> None:
        row = pd.Series(
            {
                "item1_text": "Submit a death-benefit request to the processing team.",
                "item2_text": "Update a disability-benefit contact in another system.",
                "cross_encoder_score": 0.40,
                "embedding_similarity": 0.73,
            }
        )

        relationship, _, borderline = initial_cross_encoder_decision(row, 0.995, 0.90)

        self.assertEqual("related", relationship)
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
