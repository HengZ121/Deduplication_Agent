#!/usr/bin/env python3
"""Tests for Transformer language-prediction caching and pair filtering."""

from __future__ import annotations

import unittest

import pandas as pd

from language_detection import (
    exclude_model_detected_english_french_pairs,
    validate_language_predictions,
)


class LanguagePredictionTests(unittest.TestCase):
    def test_filter_uses_model_labels_and_confidence(self) -> None:
        predictions = pd.DataFrame(
            {
                "node_index": [0, 1, 2],
                "node_id": ["n0", "n1", "n2"],
                "predicted_language": ["en", "fr", "fr"],
                "language_confidence": [0.99, 0.98, 0.40],
                "language_model": ["test-model"] * 3,
            }
        )
        pairs = pd.DataFrame(
            {
                "item1_index": [0, 0, 1],
                "item2_index": [1, 2, 2],
                "embedding_similarity": [0.99, 0.90, 0.90],
            }
        )

        filtered, excluded_count = exclude_model_detected_english_french_pairs(
            pairs,
            predictions,
            confidence_threshold=0.90,
        )

        self.assertEqual(1, excluded_count)
        self.assertEqual(
            [(0, 2), (1, 2)],
            list(filtered[["item1_index", "item2_index"]].itertuples(index=False, name=None)),
        )

    def test_prediction_cache_must_match_nodes_and_model(self) -> None:
        comparable = pd.DataFrame({"node_id": ["n0", "n1"]})
        predictions = pd.DataFrame(
            {
                "node_index": [0, 1],
                "node_id": ["n0", "n1"],
                "predicted_language": ["en", "fr"],
                "language_confidence": [0.99, 0.98],
                "language_model": ["test-model", "test-model"],
            }
        )

        validate_language_predictions(predictions, comparable, "test-model")
        with self.assertRaisesRegex(ValueError, "different model"):
            validate_language_predictions(predictions, comparable, "other-model")


if __name__ == "__main__":
    unittest.main()
