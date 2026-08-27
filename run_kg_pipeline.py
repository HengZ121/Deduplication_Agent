#!/usr/bin/env python3
"""Retrieve and classify duplicate relationships between precomputed KMT KG nodes."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import time
import urllib.error
from pathlib import Path

import numpy as np
import pandas as pd

from dita_kg_chunker import (
    KNOWLEDGE_EDGE_COLUMNS,
    KNOWLEDGE_NODE_COLUMNS,
    chunk_dita_to_frames,
    load_dita_as_document_nodes,
)
from language_detection import (
    DEFAULT_LANGUAGE_DETECTION_MODEL,
    build_language_predictions,
    exclude_model_detected_english_french_pairs,
    validate_language_predictions,
)
from run_passage_pipeline import (
    DEFAULT_EMBEDDING_MODEL,
    encode_passages,
    has_conflict_signal,
    normalized_passage,
    openai_passage_request,
    retrieve_candidate_indices,
    token_jaccard,
)
from run_procedure_pipeline import (
    DEFAULT_API_KEY_FILE,
    DEFAULT_CROSS_ENCODER_MODEL,
    DEFAULT_LLM_WORKERS,
    DEFAULT_MODEL,
    resolve_api_key,
    sigmoid,
)


DEFAULT_OUTPUT_DIR = Path("outputs/kmt_kg_pipeline")
DEFAULT_ARTICLE_METADATA_CSV = Path("outputs/kmt_dita_pipeline/procedure_documents_with_clusters.csv")
LLM_REVIEW_CHECKPOINT_NAME = "kg_llm_reviews.jsonl"


def llm_review_key(row: pd.Series, model: str) -> tuple[str, str, str]:
    """Return a stable cache key for a candidate pair and LLM model."""

    return str(row["item1_node_id"]), str(row["item2_node_id"]), model


def load_llm_review_checkpoint(path: Path) -> dict[tuple[str, str, str], dict[str, object]]:
    """Load the latest JSONL checkpoint record for every pair/model key."""

    records: dict[tuple[str, str, str], dict[str, object]] = {}
    if not path.is_file():
        return records
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            try:
                record = json.loads(line)
                key = (
                    str(record["item1_node_id"]),
                    str(record["item2_node_id"]),
                    str(record["model"]),
                )
            except (json.JSONDecodeError, KeyError, TypeError):
                # A final partial line can occur if a process is interrupted
                # during a write. Earlier complete records remain reusable.
                continue
            records[key] = record
    return records


def append_llm_review_checkpoint(path: Path, record: dict[str, object]) -> None:
    """Durably append one completed API attempt to the JSONL checkpoint."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()


def compact_candidate_pairs(
    comparable_df: pd.DataFrame,
    embeddings: np.ndarray,
    embedding_threshold: float,
    neighbors_per_node: int,
    retrieval_batch_size: int,
    max_candidates: int,
) -> pd.DataFrame:
    retrieval_df = comparable_df.rename(columns={"node_index": "passage_id"}).copy()
    pairs = retrieve_candidate_indices(
        retrieval_df,
        embeddings,
        embedding_threshold,
        neighbors_per_node,
        retrieval_batch_size,
    )
    ranked = sorted(pairs.items(), key=lambda item: item[1], reverse=True)
    if max_candidates > 0:
        ranked = ranked[:max_candidates]
    node_ids = comparable_df["node_id"].tolist()
    columns = [
        "item1_index",
        "item2_index",
        "item1_node_id",
        "item2_node_id",
        "embedding_similarity",
    ]
    return pd.DataFrame(
        (
            {
                "item1_index": pair[0],
                "item2_index": pair[1],
                "item1_node_id": node_ids[pair[0]],
                "item2_node_id": node_ids[pair[1]],
                "embedding_similarity": float(score),
            }
            for pair, score in ranked
        ),
        columns=columns,
    )


def score_candidate_pairs(
    candidates_df: pd.DataFrame,
    comparable_df: pd.DataFrame,
    model_name: str,
    batch_size: int,
    text_chars: int,
    checkpoint_path: Path | None = None,
) -> pd.DataFrame:
    if candidates_df.empty:
        result = candidates_df.copy()
        result["cross_encoder_score"] = pd.Series(dtype="float32")
        return result

    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("CrossEncoder scoring requires torch and transformers.") from exc

    from tqdm.auto import tqdm

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading CrossEncoder '{model_name}' on {device}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device)
    model.eval()
    texts = comparable_df["text"].tolist()
    titles = comparable_df["article_title"].tolist()
    start_offset = 0
    score_array: np.ndarray
    progress_path = checkpoint_path.with_suffix(".progress.json") if checkpoint_path else None
    if checkpoint_path and checkpoint_path.is_file() and progress_path and progress_path.is_file():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if int(progress.get("total_pairs", -1)) == len(candidates_df) and progress.get("model") == model_name:
            score_array = np.memmap(checkpoint_path, dtype="float32", mode="r+", shape=(len(candidates_df),))
            start_offset = int(progress.get("completed_pairs", 0))
            print(f"Resuming CrossEncoder scoring at pair {start_offset} of {len(candidates_df)}.")
        else:
            score_array = np.memmap(checkpoint_path, dtype="float32", mode="w+", shape=(len(candidates_df),))
    elif checkpoint_path:
        score_array = np.memmap(checkpoint_path, dtype="float32", mode="w+", shape=(len(candidates_df),))
    else:
        score_array = np.empty(len(candidates_df), dtype="float32")

    starts = range(start_offset, len(candidates_df), batch_size)
    for batch_number, start in enumerate(tqdm(starts, desc="CrossEncoder scoring"), start=1):
        batch = candidates_df.iloc[start : start + batch_size]
        indices1 = batch["item1_index"].to_numpy(dtype=np.int64)
        indices2 = batch["item2_index"].to_numpy(dtype=np.int64)
        left = [f"Article: {titles[index]}\nNode: {texts[index][:text_chars]}" for index in indices1]
        right = [f"Article: {titles[index]}\nNode: {texts[index][:text_chars]}" for index in indices2]
        encoded = tokenizer(
            left,
            right,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.no_grad():
            logits = model(**encoded).logits
        batch_scores = sigmoid(logits.squeeze(-1).cpu().numpy()).astype("float32")
        score_array[start : start + len(batch_scores)] = batch_scores
        if checkpoint_path and progress_path and (batch_number % 100 == 0 or start + len(batch_scores) == len(candidates_df)):
            if isinstance(score_array, np.memmap):
                score_array.flush()
            progress_path.write_text(
                json.dumps(
                    {
                        "model": model_name,
                        "total_pairs": len(candidates_df),
                        "completed_pairs": start + len(batch_scores),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
    result = candidates_df.copy()
    result["cross_encoder_score"] = np.asarray(score_array, dtype="float32")
    return result


def classify_compact_pairs(
    scored_df: pd.DataFrame,
    comparable_df: pd.DataFrame,
    duplicate_threshold: float,
    independent_threshold: float,
) -> pd.DataFrame:
    from tqdm.auto import tqdm

    texts = comparable_df["text"].tolist()
    normalized_texts = [normalized_passage(text) for text in texts]
    relationships: list[str] = []
    analyses: list[str] = []
    borderline: list[bool] = []

    for row in tqdm(scored_df.itertuples(index=False), total=len(scored_df), desc="Local classification"):
        item1_index = int(row.item1_index)
        item2_index = int(row.item2_index)
        text1 = texts[item1_index]
        text2 = texts[item2_index]
        normalized1 = normalized_texts[item1_index]
        normalized2 = normalized_texts[item2_index]
        cross_score = float(row.cross_encoder_score)
        embedding_score = float(row.embedding_similarity)
        if normalized1 == normalized2:
            relationships.append("duplicate/semantic duplicate")
            analyses.append("Normalized node text is identical.")
            borderline.append(False)
        elif (
            min(len(normalized1.split()), len(normalized2.split())) >= 5
            and normalized1 != normalized2
            and (normalized1 in normalized2 or normalized2 in normalized1)
        ):
            relationships.append("one passage included in another")
            analyses.append("One normalized node is contained in the other.")
            borderline.append(False)
        elif cross_score < independent_threshold:
            relationships.append("independent")
            analyses.append("CrossEncoder score is below the independent threshold.")
            borderline.append(False)
        else:
            lexical_overlap = token_jaccard(text1, text2)
            conflict_signal = has_conflict_signal(text1, text2)
            if (
                cross_score >= duplicate_threshold
                and embedding_score >= 0.90
                and lexical_overlap >= 0.72
                and not conflict_signal
            ):
                relationships.append("duplicate/semantic duplicate")
                analyses.append("CrossEncoder, embedding, and lexical overlap strongly support duplication.")
                borderline.append(False)
            else:
                relationships.append("independent")
                analyses.append("Ambiguous CrossEncoder result; conservative local fallback pending LLM review.")
                borderline.append(True)

    result = scored_df.copy()
    result["final_relationship_type"] = relationships
    result["final_analysis"] = analyses
    result["is_borderline"] = borderline
    result["classification_source"] = ["cross_encoder_borderline_fallback" if value else "cross_encoder" for value in borderline]
    result["llm_review_status"] = ["not_reviewed" if value else "not_needed" for value in borderline]
    return result


def review_borderline_pairs(
    results_df: pd.DataFrame,
    comparable_df: pd.DataFrame,
    api_key: str | None,
    model: str,
    llm_limit: int,
    llm_workers: int,
    api_timeout: int,
    checkpoint_path: Path | None = None,
    max_attempts: int = 5,
) -> pd.DataFrame:
    if not api_key or llm_limit <= 0:
        return results_df
    result = results_df.copy()
    borderline_indices = result.index[result["is_borderline"]].tolist()[:llm_limit]
    if not borderline_indices:
        return result

    cached_records = (
        load_llm_review_checkpoint(checkpoint_path)
        if checkpoint_path is not None
        else {}
    )
    pending_indices: list[int] = []
    reused_count = 0
    for row_index in borderline_indices:
        pair = result.loc[row_index]
        cached = cached_records.get(llm_review_key(pair, model))
        if cached and cached.get("review_status") == "reviewed":
            result.at[row_index, "final_relationship_type"] = cached["relationship_type"]
            result.at[row_index, "final_analysis"] = cached["analysis"]
            result.at[row_index, "classification_source"] = "llm_borderline"
            result.at[row_index, "llm_review_status"] = "reviewed"
            reused_count += 1
        else:
            pending_indices.append(int(row_index))
    if reused_count:
        print(f"Reused {reused_count} completed LLM reviews from checkpoint.")
    if not pending_indices:
        return result

    def detailed_row(row_index: int) -> pd.Series:
        pair = result.loc[row_index]
        node1 = comparable_df.iloc[int(pair["item1_index"])]
        node2 = comparable_df.iloc[int(pair["item2_index"])]
        return pd.Series(
            {
                "item1_article_title": node1["article_title"],
                "item1_text": node1["text"],
                "item2_article_title": node2["article_title"],
                "item2_text": node2["text"],
            }
        )

    def review(row_index: int) -> dict[str, object]:
        pair = result.loc[row_index]
        last_error = ""
        for attempt in range(1, max_attempts + 1):
            try:
                response = openai_passage_request(
                    api_key,
                    model,
                    detailed_row(row_index),
                    api_timeout,
                )
                return {
                    "pair_row_index": row_index,
                    "item1_node_id": str(pair["item1_node_id"]),
                    "item2_node_id": str(pair["item2_node_id"]),
                    "model": model,
                    "relationship_type": response["relationship_type"],
                    "analysis": response["analysis"],
                    "review_status": "reviewed",
                    "attempts": attempt,
                }
            except (
                urllib.error.URLError,
                TimeoutError,
                KeyError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < max_attempts:
                    time.sleep(min(2 ** (attempt - 1), 30))
        return {
            "pair_row_index": row_index,
            "item1_node_id": str(pair["item1_node_id"]),
            "item2_node_id": str(pair["item2_node_id"]),
            "model": model,
            "relationship_type": str(result.at[row_index, "final_relationship_type"]),
            "analysis": last_error,
            "review_status": "api_error",
            "attempts": max_attempts,
        }

    from tqdm.auto import tqdm

    workers = max(1, min(llm_workers, len(pending_indices)))
    print(
        f"Reviewing {len(pending_indices)} pending borderline node pairs "
        f"with {workers} LLM worker(s)..."
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(review, index) for index in pending_indices]
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="LLM review"):
            record = future.result()
            row_index = int(record["pair_row_index"])
            relationship = str(record["relationship_type"])
            analysis = str(record["analysis"])
            status = str(record["review_status"])
            if checkpoint_path is not None:
                append_llm_review_checkpoint(checkpoint_path, record)
            if status == "reviewed":
                result.at[row_index, "final_relationship_type"] = relationship
                result.at[row_index, "classification_source"] = "llm_borderline"
            result.at[row_index, "final_analysis"] = analysis
            result.at[row_index, "llm_review_status"] = status
    return result


def detailed_matches(results_df: pd.DataFrame, comparable_df: pd.DataFrame) -> pd.DataFrame:
    matches = results_df[results_df["final_relationship_type"] != "independent"].copy()
    if matches.empty:
        return matches
    fields = [
        "node_type",
        "article_path",
        "article_title",
        "language",
        "topic_path",
        "source_element_path",
        "element_id",
        "conref_targets",
        "text",
    ]
    left = comparable_df[fields].add_prefix("item1_")
    right = comparable_df[fields].add_prefix("item2_")
    matches = matches.merge(left, left_on="item1_index", right_index=True, how="left")
    return matches.merge(right, left_on="item2_index", right_index=True, how="left")


def write_summary(
    output_dir: Path,
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    results_df: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    counts = results_df["final_relationship_type"].value_counts().to_dict()
    if args.dita_input_mode == "chunk":
        chunking_strategy = "DITA-native structural nodes plus atomic knowledge nodes"
    elif args.dita_input_mode == "document":
        chunking_strategy = "No chunking; one complete node per DITA file/article"
    elif (
        not nodes_df.empty
        and set(nodes_df["node_type"].astype(str)) == {"dita_document"}
        and edges_df.empty
    ):
        chunking_strategy = "No chunking; reused one complete node per DITA file/article"
    else:
        chunking_strategy = "Reused precomputed node and edge tables"
    summary = {
        "dita_input_mode": args.dita_input_mode,
        "chunking_applied": args.dita_input_mode == "chunk",
        "chunking_strategy": chunking_strategy,
        "node_count": int(len(nodes_df)),
        "structural_node_count": int(nodes_df["is_structural"].sum()),
        "comparable_content_node_count": int(nodes_df["is_comparable"].sum()),
        "edge_count": int(len(edges_df)),
        "candidate_pair_count": int(len(candidates_df)),
        "borderline_pair_count": int(results_df["is_borderline"].sum()),
        "llm_reviewed_pair_count": int((results_df["llm_review_status"] == "reviewed").sum()),
        "llm_api_error_pair_count": int((results_df["llm_review_status"] == "api_error").sum()),
        "llm_not_reviewed_pair_count": int((results_df["llm_review_status"] == "not_reviewed").sum()),
        "llm_model": args.model,
        "relationship_counts": {str(key): int(value) for key, value in counts.items()},
        "embedding_model": args.embedding_model,
        "embedding_threshold": args.embedding_threshold,
        "neighbors_per_node": args.neighbors_per_node,
        "cross_encoder_model": args.cross_encoder_model,
        "cross_encoder_duplicate_threshold": args.cross_encoder_duplicate_threshold,
        "cross_encoder_independent_threshold": args.cross_encoder_independent_threshold,
        "outputs": [
            "kg_nodes.csv",
            "kg_edges.csv",
            "kg_candidate_pairs.csv",
            "kg_pair_classifications.csv",
            "kg_deduplication_matches.csv",
            "run_summary.json",
        ],
    }
    if args.exclude_cross_language_pairs:
        summary["language_pair_filter"] = {
            "enabled": True,
            "method": "Transformer sequence classification",
            "model": args.language_detection_model,
            "confidence_threshold": args.language_confidence_threshold,
            "predicted_language_counts": getattr(args, "predicted_language_counts", {}),
            "confident_language_counts": getattr(args, "confident_language_counts", {}),
            "excluded_english_french_candidate_pair_count": int(
                getattr(args, "excluded_english_french_candidate_pair_count", 0)
            ),
        }
        summary["outputs"].insert(2, "kg_language_predictions.csv")
    if (output_dir / LLM_REVIEW_CHECKPOINT_NAME).is_file():
        summary["outputs"].insert(-1, LLM_REVIEW_CHECKPOINT_NAME)
    (output_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load DITA nodes and classify similar document or chunk pairs.")
    parser.add_argument("--input", type=Path, default=Path("KMT_dita"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--article-metadata-csv", type=Path, default=DEFAULT_ARTICLE_METADATA_CSV)
    parser.add_argument("--min-comparable-words", type=int, default=5)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--embedding-batch-size", type=int, default=256)
    parser.add_argument("--embedding-threshold", type=float, default=0.68)
    parser.add_argument("--neighbors-per-node", type=int, default=20)
    parser.add_argument("--retrieval-batch-size", type=int, default=512)
    parser.add_argument("--max-candidates", type=int, default=2_000_000, help="Use 0 for no cap.")
    parser.add_argument("--cross-encoder-model", default=DEFAULT_CROSS_ENCODER_MODEL)
    parser.add_argument("--cross-encoder-batch-size", type=int, default=256)
    parser.add_argument("--cross-encoder-text-chars", type=int, default=1200)
    parser.add_argument("--cross-encoder-duplicate-threshold", type=float, default=0.995)
    parser.add_argument("--cross-encoder-independent-threshold", type=float, default=0.95)
    parser.add_argument(
        "--exclude-cross-language-pairs",
        action="store_true",
        help="Exclude confident English/French pairs using a Transformer language classifier.",
    )
    parser.add_argument("--language-detection-model", default=DEFAULT_LANGUAGE_DETECTION_MODEL)
    parser.add_argument("--language-detection-batch-size", type=int, default=32)
    parser.add_argument("--language-detection-max-length", type=int, default=256)
    parser.add_argument(
        "--language-confidence-threshold",
        type=float,
        default=0.50,
        help="Minimum Transformer probability used to exclude an English/French pair.",
    )
    parser.add_argument("--reuse-language-predictions", action="store_true")
    parser.add_argument("--llm-limit", type=int, default=0)
    parser.add_argument("--llm-workers", type=int, default=DEFAULT_LLM_WORKERS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_API_KEY_FILE)
    parser.add_argument("--api-timeout", type=int, default=60)
    input_mode = parser.add_mutually_exclusive_group()
    input_mode.add_argument(
        "--chunk-input-dita",
        dest="dita_input_mode",
        action="store_const",
        const="chunk",
        help="Build DITA-native structural and atomic nodes (default).",
    )
    input_mode.add_argument(
        "--no-chunk-input-dita",
        dest="dita_input_mode",
        action="store_const",
        const="document",
        help="Process fresh DITA without chunking: each .ditamap article becomes one comparable node.",
    )
    input_mode.add_argument(
        "--reuse-nodes",
        "--reuse-existing-nodes",
        dest="dita_input_mode",
        action="store_const",
        const="reuse",
        help="Reuse existing kg_nodes.csv and kg_edges.csv from --output-dir.",
    )
    parser.set_defaults(dita_input_mode="chunk")
    parser.add_argument("--reuse-candidates", action="store_true")
    parser.add_argument("--reuse-cross-encoder-scores", action="store_true")
    parser.add_argument(
        "--stop-after-chunking",
        "--stop-after-node-building",
        dest="stop_after_chunking",
        action="store_true",
    )
    parser.add_argument("--stop-after-retrieval", action="store_true")
    return parser.parse_args(argv)


def validate_node_tables(nodes_df: pd.DataFrame, edges_df: pd.DataFrame) -> None:
    """Fail early when reused or generated node tables do not match the pipeline schema."""

    missing_node_columns = sorted(set(KNOWLEDGE_NODE_COLUMNS) - set(nodes_df.columns))
    missing_edge_columns = sorted(set(KNOWLEDGE_EDGE_COLUMNS) - set(edges_df.columns))
    if missing_node_columns:
        raise ValueError(f"kg_nodes.csv is missing required columns: {', '.join(missing_node_columns)}")
    if missing_edge_columns:
        raise ValueError(f"kg_edges.csv is missing required columns: {', '.join(missing_edge_columns)}")
    if nodes_df.empty:
        raise ValueError("No DITA nodes were produced. Check that --input contains .ditamap files.")


def validate_candidate_table(candidates_df: pd.DataFrame, comparable_df: pd.DataFrame) -> None:
    """Ensure cached candidates still refer to the currently loaded node table."""

    required = {
        "item1_index",
        "item2_index",
        "item1_node_id",
        "item2_node_id",
        "embedding_similarity",
    }
    missing = sorted(required - set(candidates_df.columns))
    if missing:
        raise ValueError(f"kg_candidate_pairs.csv is missing required columns: {', '.join(missing)}")
    if candidates_df.empty:
        return
    left_indices = pd.to_numeric(candidates_df["item1_index"], errors="raise").to_numpy(dtype=np.int64)
    right_indices = pd.to_numeric(candidates_df["item2_index"], errors="raise").to_numpy(dtype=np.int64)
    if left_indices.min() < 0 or right_indices.min() < 0:
        raise ValueError("Candidate node indices cannot be negative.")
    if left_indices.max() >= len(comparable_df) or right_indices.max() >= len(comparable_df):
        raise ValueError("Cached candidate indices do not fit the currently loaded node table.")
    node_ids = comparable_df["node_id"].astype(str).to_numpy()
    left_matches = node_ids[left_indices] == candidates_df["item1_node_id"].astype(str).to_numpy()
    right_matches = node_ids[right_indices] == candidates_df["item2_node_id"].astype(str).to_numpy()
    if not bool(left_matches.all() and right_matches.all()):
        raise ValueError(
            "Cached candidates were created from different nodes. Rerun without --reuse-candidates."
        )


def validate_scored_table(scored_df: pd.DataFrame, candidates_df: pd.DataFrame) -> None:
    """Ensure cached CrossEncoder scores remain aligned with candidate rows."""

    required = {"item1_index", "item2_index", "cross_encoder_score"}
    missing = sorted(required - set(scored_df.columns))
    if missing:
        raise ValueError(f"kg_cross_encoder_scores.csv is missing required columns: {', '.join(missing)}")
    if len(scored_df) != len(candidates_df):
        raise ValueError(
            "CrossEncoder scores do not match the filtered candidate table. "
            "Rerun without --reuse-cross-encoder-scores."
        )
    pair_columns = ["item1_index", "item2_index"]
    scored_pairs = scored_df[pair_columns].apply(pd.to_numeric, errors="raise").to_numpy(dtype=np.int64)
    candidate_pairs = candidates_df[pair_columns].apply(pd.to_numeric, errors="raise").to_numpy(dtype=np.int64)
    if not np.array_equal(scored_pairs, candidate_pairs):
        raise ValueError(
            "Cached CrossEncoder score rows are not aligned with candidate rows. "
            "Rerun without --reuse-cross-encoder-scores."
        )


def main() -> None:
    args = parse_args()
    if not 0.0 <= args.language_confidence_threshold <= 1.0:
        raise ValueError("--language-confidence-threshold must be between 0 and 1.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = args.output_dir / "kg_nodes.csv"
    edges_path = args.output_dir / "kg_edges.csv"

    if args.dita_input_mode == "chunk":
        print("Building DITA-native structural and atomic knowledge nodes...")
        nodes_df, edges_df = chunk_dita_to_frames(
            args.input,
            args.article_metadata_csv,
            args.min_comparable_words,
        )
        nodes_df.to_csv(nodes_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
        edges_df.to_csv(edges_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
        print(f"Built {len(nodes_df)} nodes and {len(edges_df)} edges.")
    elif args.dita_input_mode == "document":
        print("Loading one comparable node per DITA article without chunking...")
        nodes_df, edges_df = load_dita_as_document_nodes(args.input, args.min_comparable_words)
        nodes_df.to_csv(nodes_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
        edges_df.to_csv(edges_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
        print(f"Built {len(nodes_df)} document-level nodes without chunking.")
    else:
        if not nodes_path.is_file() or not edges_path.is_file():
            raise FileNotFoundError(
                "--reuse-nodes requires existing kg_nodes.csv and kg_edges.csv in --output-dir."
            )
        print("Reusing existing knowledge nodes and edges...")
        nodes_df = pd.read_csv(nodes_path, encoding="utf-8-sig", keep_default_na=False)
        edges_df = pd.read_csv(edges_path, encoding="utf-8-sig", keep_default_na=False)

    validate_node_tables(nodes_df, edges_df)

    comparable_df = nodes_df[nodes_df["is_comparable"].astype(str).str.lower().isin({"true", "1"})].copy()
    comparable_df = comparable_df.reset_index(drop=True)
    comparable_df["node_index"] = np.arange(len(comparable_df), dtype=np.int64)
    print(f"Found {len(comparable_df)} comparable content nodes.")
    if args.stop_after_chunking:
        print("Stopping after node construction/loading by request.")
        return
    if comparable_df.empty:
        raise ValueError(
            "No comparable content nodes were produced. Lower --min-comparable-words or inspect kg_nodes.csv."
        )

    language_predictions_df: pd.DataFrame | None = None
    if args.exclude_cross_language_pairs:
        prediction_path = args.output_dir / "kg_language_predictions.csv"
        if args.reuse_language_predictions and prediction_path.is_file():
            print("Reusing Transformer language predictions...")
            language_predictions_df = pd.read_csv(prediction_path, encoding="utf-8-sig")
        else:
            language_predictions_df = build_language_predictions(
                comparable_df,
                model_name=args.language_detection_model,
                batch_size=args.language_detection_batch_size,
                max_length=args.language_detection_max_length,
            )
        validate_language_predictions(
            language_predictions_df,
            comparable_df,
            args.language_detection_model,
        )
        language_predictions_df.to_csv(prediction_path, index=False, encoding="utf-8-sig")
        predicted_counts = language_predictions_df["predicted_language"].value_counts()
        args.predicted_language_counts = {
            str(language): int(count) for language, count in predicted_counts.items()
        }
        confident_mask = (
            pd.to_numeric(language_predictions_df["language_confidence"], errors="raise")
            >= args.language_confidence_threshold
        )
        confident_counts = language_predictions_df.loc[
            confident_mask,
            "predicted_language",
        ].value_counts()
        args.confident_language_counts = {
            str(language): int(count) for language, count in confident_counts.items()
        }
        print(
            "Transformer language predictions: "
            + ", ".join(f"{language}={count}" for language, count in predicted_counts.items())
        )

    candidate_path = args.output_dir / "kg_candidate_pairs.csv"
    if args.reuse_candidates and candidate_path.is_file():
        print("Reusing candidate pairs...")
        candidates_df = pd.read_csv(candidate_path, encoding="utf-8-sig")
    else:
        embeddings = encode_passages(comparable_df, args.embedding_model, args.embedding_batch_size)
        candidates_df = compact_candidate_pairs(
            comparable_df,
            embeddings,
            args.embedding_threshold,
            args.neighbors_per_node,
            args.retrieval_batch_size,
            args.max_candidates,
        )
    excluded_candidate_count = 0
    if language_predictions_df is not None:
        candidates_df, excluded_candidate_count = exclude_model_detected_english_french_pairs(
            candidates_df,
            language_predictions_df,
            args.language_confidence_threshold,
        )
    args.excluded_english_french_candidate_pair_count = excluded_candidate_count
    candidates_df.to_csv(candidate_path, index=False, encoding="utf-8-sig")
    if language_predictions_df is None:
        print(f"Retained {len(candidates_df)} compact candidate pairs.")
    else:
        print(
            f"Retained {len(candidates_df)} compact candidate pairs after excluding "
            f"{excluded_candidate_count} Transformer-detected English/French pairs."
        )
    validate_candidate_table(candidates_df, comparable_df)
    if args.stop_after_retrieval:
        print("Stopping after candidate retrieval by request.")
        return

    scored_path = args.output_dir / "kg_cross_encoder_scores.csv"
    if args.reuse_cross_encoder_scores and scored_path.is_file():
        print("Reusing CrossEncoder scores...")
        scored_df = pd.read_csv(scored_path, encoding="utf-8-sig")
    else:
        scored_df = score_candidate_pairs(
            candidates_df,
            comparable_df,
            args.cross_encoder_model,
            args.cross_encoder_batch_size,
            args.cross_encoder_text_chars,
            checkpoint_path=args.output_dir / "kg_cross_encoder_scores.checkpoint.dat",
        )
    excluded_scored_count = 0
    if language_predictions_df is not None:
        scored_df, excluded_scored_count = exclude_model_detected_english_french_pairs(
            scored_df,
            language_predictions_df,
            args.language_confidence_threshold,
        )
    validate_scored_table(scored_df, candidates_df)
    scored_df.to_csv(scored_path, index=False, encoding="utf-8-sig")
    if excluded_scored_count:
        print(
            f"Excluded {excluded_scored_count} Transformer-detected English/French pairs "
            "from cached CrossEncoder scores."
        )

    results_df = classify_compact_pairs(
        scored_df,
        comparable_df,
        args.cross_encoder_duplicate_threshold,
        args.cross_encoder_independent_threshold,
    )
    api_key, api_key_source = resolve_api_key(args.api_key_file)
    if args.llm_limit > 0 and api_key:
        print(f"Local API key loaded from {api_key_source}; reviewing only borderline pairs.")
    results_df = review_borderline_pairs(
        results_df,
        comparable_df,
        api_key,
        args.model,
        args.llm_limit,
        args.llm_workers,
        args.api_timeout,
        checkpoint_path=args.output_dir / LLM_REVIEW_CHECKPOINT_NAME,
    )
    results_df.to_csv(
        args.output_dir / "kg_pair_classifications.csv",
        index=False,
        encoding="utf-8-sig",
    )
    detailed_df = detailed_matches(results_df, comparable_df)
    detailed_df.to_csv(
        args.output_dir / "kg_deduplication_matches.csv",
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_MINIMAL,
    )
    write_summary(args.output_dir, nodes_df, edges_df, candidates_df, results_df, args)
    print(f"Done. Knowledge-graph outputs were written to {args.output_dir}.")


if __name__ == "__main__":
    main()
