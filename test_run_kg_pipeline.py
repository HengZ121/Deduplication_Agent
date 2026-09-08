#!/usr/bin/env python3
"""Tests for DITA-native fine-grained knowledge-node construction."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import unittest
from unittest import mock

import pandas as pd

from dita_kg_chunker import (
    KnowledgeGraphBuilder,
    atomic_spans,
    chunk_dita_to_frames,
    infer_content_node_type,
    load_dita_as_document_nodes,
    load_dita_body_nodes,
)
from run_kg_pipeline import (
    classify_compact_pairs,
    detailed_matches,
    parse_args,
    review_borderline_pairs,
)
from run_procedure_pipeline import find_dita_root, read_dita_documents


class AtomicKnowledgeNodeTests(unittest.TestCase):
    def test_atomic_spans_create_one_node_per_sentence(self) -> None:
        spans = atomic_spans(
            "Verify the account number. If it is unavailable, contact the regional office. Record the response."
        )

        self.assertEqual(3, len(spans))

    def test_condition_and_action_types_are_inferred_from_scope(self) -> None:
        class Element:
            def get(self, _: str) -> str:
                return ""

        self.assertEqual("action", infer_content_node_type("cmd", "Open the account.", Element()))
        self.assertEqual(
            "condition",
            infer_content_node_type("p", "If the account is inactive, contact the client.", Element()),
        )


class DitaKnowledgeGraphTests(unittest.TestCase):
    def test_fixture_builds_structure_actions_and_reuse_edges(self) -> None:
        dataset_root = Path(__file__).parent / "test_fixtures" / "kmt_dita"
        articles_df = pd.DataFrame(asdict(document) for document in read_dita_documents(dataset_root))
        builder = KnowledgeGraphBuilder(find_dita_root(dataset_root), articles_df, min_comparable_words=1)

        nodes_df, edges_df = builder.build()

        node_types = set(nodes_df["node_type"])
        self.assertIn("article", node_types)
        self.assertIn("task_topic", node_types)
        self.assertIn("step", node_types)
        self.assertIn("action", node_types)
        self.assertIn("information_group", node_types)
        self.assertIn("reusable_fragment", node_types)
        self.assertIn("reusable_statement", node_types)
        self.assertIn("REUSES", set(edges_df["relationship"]))
        action_text = " ".join(nodes_df.loc[nodes_df["node_type"] == "action", "text"])
        self.assertIn("Process the request.", action_text)

    def test_document_mode_loads_one_unbroken_node_per_map(self) -> None:
        dataset_root = Path(__file__).parent / "test_fixtures" / "kmt_dita"

        nodes_df, edges_df = load_dita_as_document_nodes(dataset_root, min_comparable_words=1)

        self.assertEqual(1, len(nodes_df))
        self.assertEqual("dita_document", nodes_df.iloc[0]["node_type"])
        self.assertTrue(bool(nodes_df.iloc[0]["is_comparable"]))
        self.assertIn("Process the request.", nodes_df.iloc[0]["text"])
        self.assertIn("Reusable warning text.", nodes_df.iloc[0]["text"])
        self.assertTrue(edges_df.empty)

    def test_document_mode_loads_each_common_note_as_one_unbroken_node(self) -> None:
        common_notes = (
            Path(__file__).parent / "test_fixtures" / "kmt_dita" / "dita" / "common_notes"
        )

        nodes_df, edges_df = load_dita_as_document_nodes(common_notes, min_comparable_words=1)

        self.assertEqual(1, len(nodes_df))
        self.assertEqual("note.dita", nodes_df.iloc[0]["article_path"])
        self.assertIn("Reusable warning text.", nodes_df.iloc[0]["text"])
        self.assertTrue(bool(nodes_df.iloc[0]["is_comparable"]))
        self.assertTrue(edges_df.empty)

    def test_stale_metadata_cache_is_ignored_for_a_different_dita_input(self) -> None:
        dataset_root = Path(__file__).parent / "test_fixtures" / "kmt_dita"
        metadata_path = Path(__file__).parent / "test_fixtures" / "stale_article_metadata.csv"

        nodes_df, _ = chunk_dita_to_frames(dataset_root, metadata_path, min_comparable_words=1)

        self.assertFalse(nodes_df.empty)
        self.assertIn("Example KMT Article (Action)", set(nodes_df["article_title"]))

    def test_body_mode_extracts_plain_text_and_excludes_common_notes(self) -> None:
        dataset_root = Path(__file__).parent / "test_fixtures" / "kmt_dita"

        instances_df, nodes_df, edges_df = load_dita_body_nodes(
            dataset_root,
            "en",
            min_comparable_words=1,
        )

        self.assertEqual(2, len(instances_df))
        self.assertEqual({"conbody", "taskbody"}, set(instances_df["body_tag"]))
        self.assertTrue((instances_df["language"] == "en").all())
        self.assertTrue(instances_df["source_path"].str.startswith("KA-99999_EN/").all())
        self.assertFalse(instances_df["text"].str.contains(r"<[^>]+>", regex=True).any())
        self.assertNotIn("Reusable warning text.", " ".join(instances_df["text"]))
        self.assertNotIn("Steps", nodes_df.loc[nodes_df["article_title"] == "Steps", "text"].iloc[0])
        self.assertEqual(len(instances_df), len(nodes_df))
        self.assertTrue(edges_df.empty)


class PipelineArgumentTests(unittest.TestCase):
    def test_default_mode_chunks_dita(self) -> None:
        self.assertEqual("chunk", parse_args([]).dita_input_mode)

    def test_no_chunk_mode_processes_fresh_dita_as_documents(self) -> None:
        self.assertEqual(
            "document",
            parse_args(["--no-chunk-input-dita"]).dita_input_mode,
        )

    def test_reuse_mode_is_explicit(self) -> None:
        self.assertEqual("reuse", parse_args(["--reuse-nodes"]).dita_input_mode)

    def test_body_mode_requires_an_explicit_language_at_runtime(self) -> None:
        args = parse_args(["--body-input-dita", "--body-language", "fr"])

        self.assertEqual("body", args.dita_input_mode)
        self.assertEqual("fr", args.body_language)

    def test_transformer_language_filter_is_explicit(self) -> None:
        args = parse_args(["--exclude-cross-language-pairs"])

        self.assertTrue(args.exclude_cross_language_pairs)
        self.assertIn("language-detection", args.language_detection_model)

    def test_default_cross_encoder_borderline_floor_is_point_95(self) -> None:
        self.assertEqual(0.95, parse_args([]).cross_encoder_independent_threshold)


class CompactPairClassificationTests(unittest.TestCase):
    def test_point_95_is_borderline_but_lower_score_is_independent(self) -> None:
        comparable = pd.DataFrame(
            {
                "text": [
                    "Contact the client about the retirement application.",
                    "Review the survivor account before issuing payment.",
                    "Update the disability record in the processing system.",
                ]
            }
        )
        scored = pd.DataFrame(
            {
                "item1_index": [0, 0],
                "item2_index": [1, 2],
                "embedding_similarity": [0.70, 0.70],
                "cross_encoder_score": [0.95, 0.949999],
            }
        )

        result = classify_compact_pairs(scored, comparable, 0.995, 0.95)

        self.assertTrue(bool(result.iloc[0]["is_borderline"]))
        self.assertFalse(bool(result.iloc[1]["is_borderline"]))

    def test_encoding_only_apostrophe_difference_is_not_borderline(self) -> None:
        comparable = pd.DataFrame(
            {
                "text": [
                    "Le paiement n’est pas disponible.",
                    "Le paiement n＇est pas disponible.",
                ]
            }
        )
        scored = pd.DataFrame(
            {
                "item1_index": [0],
                "item2_index": [1],
                "embedding_similarity": [0.99],
                "cross_encoder_score": [0.97],
            }
        )

        result = classify_compact_pairs(scored, comparable, 0.995, 0.90)

        self.assertEqual("duplicate/semantic duplicate", result.iloc[0]["final_relationship_type"])
        self.assertFalse(bool(result.iloc[0]["is_borderline"]))


class DetailedMatchExportTests(unittest.TestCase):
    def test_paired_text_columns_are_adjacent_at_the_end(self) -> None:
        results = pd.DataFrame(
            {
                "item1_index": [0],
                "item2_index": [1],
                "final_relationship_type": ["duplicate/semantic duplicate"],
            }
        )
        comparable = pd.DataFrame(
            {
                "node_type": ["dita_document", "dita_document"],
                "article_path": ["first.dita", "second.dita"],
                "article_title": ["First", "Second"],
                "language": ["en", "en"],
                "topic_path": ["first", "second"],
                "source_element_path": ["/topic", "/topic"],
                "element_id": ["first", "second"],
                "conref_targets": ["", ""],
                "text": ["First passage.", "Second passage."],
            }
        )

        exported = detailed_matches(results, comparable)

        self.assertEqual(["item1_text", "item2_text"], list(exported.columns[-2:]))
        self.assertEqual("First passage.", exported.iloc[0]["item1_text"])
        self.assertEqual("Second passage.", exported.iloc[0]["item2_text"])


class LlmReviewCheckpointTests(unittest.TestCase):
    def test_completed_review_is_reused_without_a_second_api_call(self) -> None:
        results = pd.DataFrame(
            {
                "item1_index": [0],
                "item2_index": [1],
                "item1_node_id": ["n0"],
                "item2_node_id": ["n1"],
                "final_relationship_type": ["independent"],
                "final_analysis": ["pending"],
                "is_borderline": [True],
                "classification_source": ["cross_encoder_borderline_fallback"],
                "llm_review_status": ["not_reviewed"],
            }
        )
        comparable = pd.DataFrame(
            {
                "article_title": ["First", "Second"],
                "text": ["First passage.", "Second passage."],
            }
        )
        response = {
            "relationship_type": "duplicate/semantic duplicate",
            "analysis": "Same instruction.",
        }

        checkpoint = Path(__file__).parent / "test_llm_reviews_checkpoint.jsonl"
        checkpoint.unlink(missing_ok=True)
        try:
            with mock.patch("run_kg_pipeline.openai_passage_request", return_value=response) as request:
                first = review_borderline_pairs(
                    results,
                    comparable,
                    "test-key",
                    "test-model",
                    1,
                    1,
                    10,
                    checkpoint_path=checkpoint,
                )
            with mock.patch("run_kg_pipeline.openai_passage_request") as request_again:
                second = review_borderline_pairs(
                    results,
                    comparable,
                    "test-key",
                    "test-model",
                    1,
                    1,
                    10,
                    checkpoint_path=checkpoint,
                )
        finally:
            checkpoint.unlink(missing_ok=True)

        request.assert_called_once()
        request_again.assert_not_called()
        self.assertEqual("reviewed", first.iloc[0]["llm_review_status"])
        self.assertEqual("reviewed", second.iloc[0]["llm_review_status"])
        self.assertEqual("duplicate/semantic duplicate", second.iloc[0]["final_relationship_type"])


if __name__ == "__main__":
    unittest.main()
