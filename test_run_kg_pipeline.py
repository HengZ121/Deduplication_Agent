#!/usr/bin/env python3
"""Tests for DITA-native fine-grained knowledge-node construction."""

from __future__ import annotations

import unittest
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from dita_kg_chunker import (
    KnowledgeGraphBuilder,
    atomic_spans,
    chunk_dita_to_frames,
    infer_content_node_type,
    load_dita_as_document_nodes,
)
from run_kg_pipeline import parse_args
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


if __name__ == "__main__":
    unittest.main()
