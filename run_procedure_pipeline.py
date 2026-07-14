#!/usr/bin/env python3
"""Run the procedure duplicate-detection pipeline locally.

This script is based on the drafted notebook flow:
1. load and cluster the documents,
2. find cosine-similar candidate pairs,
3. rerank/filter candidates with a CrossEncoder,
4. optionally ask OpenAI to classify each candidate relationship.

The notebooks were authored for Colab and an older Bible dataset. This runner
keeps the same pipeline shape while adapting the data loader to procedure.zip.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import html
import json
import math
import os
import re
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer


DEFAULT_ZIP = Path("procedure.zip")
DEFAULT_OUTPUT_DIR = Path("outputs") / "procedure_pipeline"
DEFAULT_SIMILARITY_THRESHOLD = 0.45
DEFAULT_TOP_PAIRS = 500
DEFAULT_PAIR_SEARCH_BACKEND = "auto"
DEFAULT_PAIR_SEARCH_JOBS = -1
DEFAULT_UMAP_COMPONENTS = 128
DEFAULT_UMAP_JOBS = 1
DEFAULT_UMAP_RANDOM_STATE = "42"
DEFAULT_HDBSCAN_MIN_CLUSTER_SIZE = 15
DEFAULT_HDBSCAN_MIN_SAMPLES = 5
DEFAULT_HDBSCAN_CLUSTER_SELECTION_EPSILON = 0.05
DEFAULT_LLM_LIMIT = 10000
DEFAULT_LLM_WORKERS = 4
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_CROSS_ENCODER_THRESHOLD = 0.95
DEFAULT_API_KEY_FILE = Path("local_api_key.txt")


@dataclass(frozen=True)
class ProcedureDocument:
    document_id: int
    path: str
    document_type: str
    title: str
    summary: str
    language: str
    modified: str
    source: str
    text: str


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value)).replace("\xa0", " ")
    # Some metadata fields are URL/form encoded with + as spaces.
    if text.count("+") > max(2, text.count(" ") // 2):
        text = text.replace("+", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def collect_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        text = clean_text(value)
        if text:
            yield text
    elif isinstance(value, list):
        for item in value:
            yield from collect_strings(item)
    elif isinstance(value, dict):
        for key in ("heading", "title", "label", "text", "content"):
            if key in value:
                yield from collect_strings(value[key])
        for item in value.get("items", []) or []:
            yield from collect_strings(item)
        for child in value.get("children", []) or []:
            yield from collect_strings(child)
        for link in value.get("links", []) or []:
            if isinstance(link, dict):
                yield from collect_strings(link.get("text"))
        for row in value.get("rows", []) or []:
            yield from collect_strings(row)


def first_string(*values: Any) -> str:
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""


def metadata_lookup(value: Any, *keys: str) -> str:
    if isinstance(value, dict):
        return first_string(*(value.get(key) for key in keys))
    return first_string(value)


def read_procedure_documents(zip_path: Path) -> list[ProcedureDocument]:
    docs: list[ProcedureDocument] = []
    with zipfile.ZipFile(zip_path) as archive:
        json_names = sorted(name for name in archive.namelist() if name.endswith(".json"))
        for name in json_names:
            data = json.loads(archive.read(name).decode("utf-8-sig"))
            metadata = data.get("metadata", {})
            titles = metadata.get("ort.titles", {})
            summaries = metadata.get("ort.summaries", {})
            section_text = list(collect_strings(data.get("sections", [])))

            title = first_string(metadata_lookup(titles, "en_title"), metadata.get("dcterms.title"), Path(name).stem)
            summary = metadata_lookup(summaries, "en_summary", "fr_summary")
            language = first_string(metadata.get("dcterms.language"))
            modified = first_string(metadata.get("dcterms.modified"), metadata.get("dcterms.issued"))
            source = first_string(data.get("source"))
            path_parts = Path(name).parts
            document_type = path_parts[1] if len(path_parts) > 2 else ""

            text_parts = [title, summary, *section_text]
            text = clean_text(" ".join(part for part in text_parts if part))
            if not text:
                continue

            docs.append(
                ProcedureDocument(
                    document_id=len(docs),
                    path=name,
                    document_type=document_type,
                    title=title,
                    summary=summary,
                    language=language,
                    modified=modified,
                    source=source,
                    text=text,
                )
            )
    return docs


def cluster_documents_with_hdbscan(
    matrix: Any,
    umap_components: int,
    umap_jobs: int,
    umap_random_state: int | None,
    min_cluster_size: int,
    min_samples: int | None,
    cluster_selection_epsilon: float,
) -> np.ndarray:
    try:
        import hdbscan
        import umap
    except ImportError as exc:
        raise RuntimeError(
            "HDBSCAN clustering requires hdbscan and umap-learn. "
            "Install dependencies with: python -m pip install -r requirements.txt"
        ) from exc

    component_count = min(umap_components, max(2, matrix.shape[0] - 2), max(2, matrix.shape[1] - 1))
    effective_umap_jobs = 1 if umap_random_state is not None else umap_jobs
    print(
        f"Reducing vectors with UMAP to {component_count} dimensions "
        f"(n_jobs={effective_umap_jobs}, random_state={umap_random_state})..."
    )
    reducer = umap.UMAP(
        n_components=component_count,
        n_jobs=effective_umap_jobs,
        random_state=umap_random_state,
    )
    reduced = reducer.fit_transform(matrix)

    print(
        "Clustering documents with HDBSCAN "
        f"(min_cluster_size={min_cluster_size}, min_samples={min_samples}, "
        f"cluster_selection_epsilon={cluster_selection_epsilon})..."
    )
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
        cluster_selection_epsilon=cluster_selection_epsilon,
    )
    return clusterer.fit_predict(reduced)


def build_duplicate_pairs(
    df: pd.DataFrame,
    matrix: Any,
    threshold: float,
    top_pairs: int,
    backend: str = DEFAULT_PAIR_SEARCH_BACKEND,
    n_jobs: int = DEFAULT_PAIR_SEARCH_JOBS,
    within_clusters: bool = True,
) -> pd.DataFrame:
    if backend == "auto":
        backend = "faiss" if is_faiss_available() else "sklearn"
    if within_clusters:
        pair_indices: list[tuple[int, int, float]] = []
        for _, cluster_df in df.groupby("cluster_label", sort=False):
            if len(cluster_df) < 2:
                continue
            original_indices = cluster_df.index.to_numpy()
            cluster_matrix = matrix[original_indices]
            for local_i, local_j, score in find_candidate_pair_indices(cluster_matrix, threshold, backend, n_jobs):
                pair_indices.append((int(original_indices[local_i]), int(original_indices[local_j]), score))
    else:
        pair_indices = find_candidate_pair_indices(matrix, threshold, backend, n_jobs)

    pairs: list[dict[str, Any]] = []

    for i, j, score in pair_indices:
        row1 = df.iloc[int(i)]
        row2 = df.iloc[int(j)]
        pairs.append(
            {
                "cluster_label": int(row1["cluster_label"]) if row1["cluster_label"] == row2["cluster_label"] else "",
                "same_cluster": bool(row1["cluster_label"] == row2["cluster_label"]),
                "similarity": float(score),
                "item1_id": int(row1["document_id"]),
                "item2_id": int(row2["document_id"]),
                "item1_path": row1["path"],
                "item2_path": row2["path"],
                "item1_type": row1["document_type"],
                "item2_type": row2["document_type"],
                "item1_title": row1["title"],
                "item2_title": row2["title"],
                "item1_summary": row1["summary"],
                "item2_summary": row2["summary"],
                "item1_text": row1["text"],
                "item2_text": row2["text"],
            }
        )

    pairs.sort(key=lambda item: item["similarity"], reverse=True)
    return pd.DataFrame(pairs[:top_pairs])


def find_candidate_pair_indices(
    matrix: Any,
    threshold: float,
    backend: str,
    n_jobs: int,
) -> list[tuple[int, int, float]]:
    if backend == "faiss":
        return find_pairs_with_faiss(matrix, threshold)
    if backend == "sklearn":
        return find_pairs_with_sklearn(matrix, threshold, n_jobs)
    if backend == "sparse":
        return find_pairs_with_sparse_dot(matrix, threshold)
    raise ValueError(f"Unsupported pair search backend: {backend}")


def is_faiss_available() -> bool:
    try:
        import faiss  # noqa: F401
    except ImportError:
        return False
    return True


def find_pairs_with_faiss(matrix: Any, threshold: float) -> list[tuple[int, int, float]]:
    import faiss

    x = matrix.astype("float32").toarray()
    faiss.normalize_L2(x)
    index = faiss.IndexFlatIP(x.shape[1])
    index.add(x)
    lims, distances, indices = index.range_search(x, threshold)

    pairs: list[tuple[int, int, float]] = []
    for i in range(x.shape[0]):
        for score, j in zip(distances[lims[i] : lims[i + 1]], indices[lims[i] : lims[i + 1]]):
            if int(j) > i:
                pairs.append((i, int(j), float(score)))
    return pairs


def find_pairs_with_sklearn(matrix: Any, threshold: float, n_jobs: int) -> list[tuple[int, int, float]]:
    from sklearn.neighbors import NearestNeighbors

    radius = 1.0 - threshold
    try:
        distance_graph = sklearn_radius_neighbors_graph(matrix, radius, n_jobs).tocoo()
    except PermissionError:
        if n_jobs == 1:
            raise
        print("Parallel sklearn pair search was blocked by the OS; retrying with --pair-search-jobs 1.")
        distance_graph = sklearn_radius_neighbors_graph(matrix, radius, 1).tocoo()

    pairs: list[tuple[int, int, float]] = []
    for i, j, distance in zip(distance_graph.row, distance_graph.col, distance_graph.data):
        if i < j:
            pairs.append((int(i), int(j), float(1.0 - distance)))
    return pairs


def sklearn_radius_neighbors_graph(matrix: Any, radius: float, n_jobs: int) -> Any:
    from sklearn.neighbors import NearestNeighbors

    neighbors = NearestNeighbors(
        algorithm="brute",
        metric="cosine",
        n_jobs=n_jobs,
        radius=radius,
    )
    neighbors.fit(matrix)
    return neighbors.radius_neighbors_graph(matrix, mode="distance")


def find_pairs_with_sparse_dot(matrix: Any, threshold: float) -> list[tuple[int, int, float]]:
    similarity = (matrix @ matrix.T).tocoo()
    return [
        (int(i), int(j), float(score))
        for i, j, score in zip(similarity.row, similarity.col, similarity.data)
        if i < j and score >= threshold
    ]


def normalized_for_inclusion(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def heuristic_relationship(row: pd.Series) -> tuple[str, str]:
    text1 = normalized_for_inclusion(row["item1_text"])
    text2 = normalized_for_inclusion(row["item2_text"])
    similarity = float(row["similarity"])

    if text1 == text2:
        return "semantically_identical", "The normalized document text is exactly the same."
    if len(text1) > 200 and len(text2) > 200 and (text1 in text2 or text2 in text1):
        return "one_doc_included", "One normalized document text is contained in the other."
    if similarity >= 0.85:
        return "semantically_identical", "Very high TF-IDF cosine similarity; review recommended."
    if similarity >= 0.65:
        return "possible_duplicate", "High TF-IDF cosine similarity; semantic review recommended."
    return "candidate", "Above candidate threshold; needs semantic or SME review."


def sigmoid(value: Any) -> np.ndarray:
    return 1 / (1 + np.exp(-np.asarray(value, dtype=float)))


def cross_encoder_text(row: pd.Series, side: int, max_chars: int) -> str:
    title = str(row.get(f"item{side}_title", "")).strip()
    summary = str(row.get(f"item{side}_summary", "")).strip()
    text = str(row.get(f"item{side}_text", "")).strip()
    parts = [part for part in [title, summary, text[:max_chars]] if part]
    return "\n\n".join(parts)


def add_cross_encoder_scores(
    pairs_df: pd.DataFrame,
    model_name: str,
    threshold: float,
    batch_size: int,
    text_chars: int,
) -> pd.DataFrame:
    if pairs_df.empty:
        pairs_df["cross_encoder_similarity_value"] = []
        pairs_df["cross_encoder_passed"] = []
        return pairs_df

    print(f"Loading CrossEncoder model '{model_name}'...")
    doc_pairs = [
        [cross_encoder_text(row, 1, text_chars), cross_encoder_text(row, 2, text_chars)]
        for _, row in pairs_df.iterrows()
    ]

    print(f"Scoring {len(doc_pairs)} candidate pairs with CrossEncoder...")
    raw_scores = predict_cross_encoder_scores(model_name, doc_pairs, batch_size)
    pairs_df = pairs_df.copy()
    pairs_df["cross_encoder_similarity_value"] = sigmoid(raw_scores).astype(float)
    pairs_df["cross_encoder_passed"] = pairs_df["cross_encoder_similarity_value"] >= threshold
    return pairs_df.sort_values(
        ["cross_encoder_similarity_value", "similarity"],
        ascending=[False, False],
    ).reset_index(drop=True)


def predict_cross_encoder_scores(model_name: str, doc_pairs: list[list[str]], batch_size: int) -> np.ndarray:
    try:
        from sentence_transformers import CrossEncoder

        model = CrossEncoder(model_name)
        return np.asarray(model.predict(doc_pairs, batch_size=batch_size, show_progress_bar=True), dtype=float)
    except ImportError:
        return predict_cross_encoder_scores_with_transformers(model_name, doc_pairs, batch_size)


def predict_cross_encoder_scores_with_transformers(
    model_name: str,
    doc_pairs: list[list[str]],
    batch_size: int,
) -> np.ndarray:
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "CrossEncoder stage requires either sentence-transformers or transformers+torch. "
            "Install dependencies with: python -m pip install -r requirements.txt"
        ) from exc

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device)
    model.eval()

    scores: list[float] = []
    from tqdm.auto import tqdm

    for start in tqdm(range(0, len(doc_pairs), batch_size), desc="CrossEncoder scoring"):
        batch = doc_pairs[start : start + batch_size]
        encoded = tokenizer(
            [pair[0] for pair in batch],
            [pair[1] for pair in batch],
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.no_grad():
            logits = model(**encoded).logits
        batch_scores = logits.squeeze(-1).detach().cpu().numpy()
        scores.extend(np.atleast_1d(batch_scores).astype(float).tolist())
    return np.asarray(scores, dtype=float)


def read_api_key_file(path: Path) -> str | None:
    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return None

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            name, value = line.split("=", 1)
            if name.strip() in {"API_KEY", "OPENAI_API_KEY"}:
                candidate = value.strip().strip('"').strip("'")
                break
        else:
            candidate = line.strip().strip('"').strip("'")
            break
    else:
        return None

    placeholder_markers = {"paste", "your_api_key", "replace_me", "<", ">"}
    lower_candidate = candidate.lower()
    if any(marker in lower_candidate for marker in placeholder_markers):
        return None
    return candidate or None


def resolve_api_key(api_key_file: Path) -> tuple[str | None, str]:
    file_key = read_api_key_file(api_key_file)
    if file_key:
        return file_key, str(api_key_file)

    for env_name in ("API_KEY", "OPENAI_API_KEY"):
        env_key = os.environ.get(env_name)
        if env_key:
            return env_key, env_name

    return None, ""


def parse_optional_int(value: str) -> int | None:
    if value.strip().lower() in {"none", "null", ""}:
        return None
    return int(value)


def openai_json_request(api_key: str, model: str, doc1: str, doc2: str, timeout: int) -> dict[str, str]:
    prompt = {
        "role": "user",
        "content": (
            "Analyze the relationship between these two procedure documents. "
            "Return only JSON with keys relationship_type and analysis. "
            "relationship_type must be one of semantically_identical, one_doc_included, "
            "conflict_in_information, none_of_above.\n\n"
            f"Document 1:\n{doc1}\n\nDocument 2:\n{doc2}"
        ),
    }
    payload = {
        "model": model,
        "messages": [prompt],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"].get("content", "{}")
    content = content.strip()
    fenced_json = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content, re.DOTALL | re.IGNORECASE)
    if fenced_json:
        content = fenced_json.group(1).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {"relationship_type": "parse_error", "analysis": content}
    return {
        "relationship_type": str(parsed.get("relationship_type", "")),
        "analysis": str(parsed.get("analysis", "")),
    }


def add_relationship_labels(
    pairs_df: pd.DataFrame,
    api_key: str | None,
    model: str,
    llm_limit: int,
    llm_workers: int,
    llm_text_chars: int,
    timeout: int,
) -> pd.DataFrame:
    if pairs_df.empty:
        pairs_df["heuristic_relationship_type"] = []
        pairs_df["heuristic_analysis"] = []
        pairs_df["llm_relationship_type"] = []
        pairs_df["llm_analysis"] = []
        return pairs_df

    heuristic_values = pairs_df.apply(heuristic_relationship, axis=1)
    pairs_df["heuristic_relationship_type"] = [item[0] for item in heuristic_values]
    pairs_df["heuristic_analysis"] = [item[1] for item in heuristic_values]
    pairs_df["llm_relationship_type"] = "SKIPPED_NO_API_KEY" if not api_key else "SKIPPED_LIMIT"
    pairs_df["llm_analysis"] = ""

    if not api_key or llm_limit <= 0:
        return pairs_df

    from tqdm.auto import tqdm

    def classify_pair(row_index: int, row: pd.Series) -> tuple[int, str, str]:
        doc1 = str(row["item1_text"])[:llm_text_chars]
        doc2 = str(row["item2_text"])[:llm_text_chars]
        try:
            result = openai_json_request(api_key, model, doc1, doc2, timeout)
            return row_index, result["relationship_type"], result["analysis"]
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
            return row_index, "API_ERROR", str(exc)

    rows_to_classify = list(pairs_df.head(llm_limit).iterrows())
    workers = max(1, min(llm_workers, len(rows_to_classify)))
    print(f"Running OpenAI analysis with {workers} concurrent worker(s)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(classify_pair, int(row_index), row)
            for row_index, row in rows_to_classify
        ]
        for future in tqdm(
            concurrent.futures.as_completed(futures),
            total=len(futures),
            desc="OpenAI relationship analysis",
        ):
            row_index, relationship_type, analysis = future.result()
            pairs_df.at[row_index, "llm_relationship_type"] = relationship_type
            pairs_df.at[row_index, "llm_analysis"] = analysis
    return pairs_df


def write_summary(
    output_dir: Path,
    docs_df: pd.DataFrame,
    candidate_pairs_df: pd.DataFrame,
    cross_encoder_pairs_df: pd.DataFrame,
    final_df: pd.DataFrame,
    threshold: float,
    pair_search_backend: str,
    within_clusters: bool,
    hdbscan_params: dict[str, Any],
    cross_encoder_threshold: float,
) -> None:
    cluster_stats = (
        docs_df.groupby(["cluster_label", "document_type"])
        .size()
        .rename("count")
        .reset_index()
        .sort_values(["cluster_label", "count"], ascending=[True, False])
    )
    cluster_stats.to_csv(output_dir / "cluster_stats.csv", index=False, encoding="utf-8-sig")

    summary = {
        "document_count": int(len(docs_df)),
        "cluster_count": int(docs_df["cluster_label"].nunique()),
        "candidate_pair_count": int(len(candidate_pairs_df)),
        "cross_encoder_scored_pair_count": int(len(cross_encoder_pairs_df)),
        "cross_encoder_passed_pair_count": int(cross_encoder_pairs_df["cross_encoder_passed"].sum())
        if "cross_encoder_passed" in cross_encoder_pairs_df
        else 0,
        "final_pair_count": int(len(final_df)),
        "similarity_threshold": threshold,
        "pair_search_backend": pair_search_backend,
        "pair_search_within_clusters": within_clusters,
        "hdbscan": hdbscan_params,
        "cross_encoder_threshold": cross_encoder_threshold,
        "outputs": [
            "procedure_documents_with_clusters.csv",
            "duplicate_pairs.csv",
            "cross_encoder_scored_pairs.csv",
            "llm_analyzed_duplicates.csv",
            "cluster_stats.csv",
        ],
    }
    (output_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the procedure duplicate-detection pipeline.")
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP, help="Input dataset zip file.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for CSV outputs.")
    parser.add_argument("--similarity-threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD)
    parser.add_argument("--top-pairs", type=int, default=DEFAULT_TOP_PAIRS)
    parser.add_argument(
        "--pair-search-backend",
        choices=["auto", "faiss", "sklearn", "sparse"],
        default=DEFAULT_PAIR_SEARCH_BACKEND,
        help="Candidate-pair search backend. auto uses FAISS when installed, otherwise sklearn.",
    )
    parser.add_argument(
        "--pair-search-jobs",
        type=int,
        default=DEFAULT_PAIR_SEARCH_JOBS,
        help="Parallel jobs for the sklearn candidate-pair backend. -1 uses all cores.",
    )
    parser.add_argument(
        "--all-pairs",
        action="store_true",
        help="Search candidate pairs globally instead of within HDBSCAN clusters.",
    )
    parser.add_argument("--umap-components", type=int, default=DEFAULT_UMAP_COMPONENTS)
    parser.add_argument(
        "--umap-jobs",
        type=int,
        default=DEFAULT_UMAP_JOBS,
        help="Parallel jobs for UMAP. Use -1 for all cores; only applies when --umap-random-state none.",
    )
    parser.add_argument(
        "--umap-random-state",
        type=parse_optional_int,
        default=parse_optional_int(DEFAULT_UMAP_RANDOM_STATE),
        help="UMAP random seed. Use 'none' to allow UMAP parallelism.",
    )
    parser.add_argument("--hdbscan-min-cluster-size", type=int, default=DEFAULT_HDBSCAN_MIN_CLUSTER_SIZE)
    parser.add_argument("--hdbscan-min-samples", type=int, default=DEFAULT_HDBSCAN_MIN_SAMPLES)
    parser.add_argument(
        "--hdbscan-cluster-selection-epsilon",
        type=float,
        default=DEFAULT_HDBSCAN_CLUSTER_SELECTION_EPSILON,
    )
    parser.add_argument("--skip-cross-encoder", action="store_true", help="Skip CrossEncoder scoring/filtering.")
    parser.add_argument("--cross-encoder-model", default=DEFAULT_CROSS_ENCODER_MODEL)
    parser.add_argument("--cross-encoder-threshold", type=float, default=DEFAULT_CROSS_ENCODER_THRESHOLD)
    parser.add_argument("--cross-encoder-batch-size", type=int, default=16)
    parser.add_argument(
        "--cross-encoder-text-chars",
        type=int,
        default=2500,
        help="Max body-text characters per document passed to the CrossEncoder. Output CSVs still keep full text.",
    )
    parser.add_argument("--llm-limit", type=int, default=DEFAULT_LLM_LIMIT, help="Max top pairs to send to OpenAI if a key is available.")
    parser.add_argument(
        "--llm-workers",
        type=int,
        default=DEFAULT_LLM_WORKERS,
        help="Number of concurrent OpenAI API calls.",
    )
    parser.add_argument("--llm-text-chars", type=int, default=6000, help="Max characters per document sent to OpenAI.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI chat model for optional LLM review.")
    parser.add_argument(
        "--api-key-file",
        type=Path,
        default=DEFAULT_API_KEY_FILE,
        help="Local file containing the OpenAI API key. Accepts raw key text or API_KEY=...",
    )
    parser.add_argument("--api-timeout", type=int, default=60)
    parser.add_argument("--require-api-key", action="store_true", help="Fail if no API key is found in --api-key-file or env vars.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading procedure documents from {args.zip}...")
    docs = read_procedure_documents(args.zip)
    docs_df = pd.DataFrame([doc.__dict__ for doc in docs])
    print(f"Loaded {len(docs_df)} documents.")

    print("Vectorizing document text with TF-IDF...")
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.9,
        max_features=50_000,
        sublinear_tf=True,
        norm="l2",
    )
    matrix = vectorizer.fit_transform(docs_df["text"])

    docs_df["cluster_label"] = cluster_documents_with_hdbscan(
        matrix,
        umap_components=args.umap_components,
        umap_jobs=args.umap_jobs,
        umap_random_state=args.umap_random_state,
        min_cluster_size=args.hdbscan_min_cluster_size,
        min_samples=args.hdbscan_min_samples,
        cluster_selection_epsilon=args.hdbscan_cluster_selection_epsilon,
    )
    docs_df.to_csv(args.output_dir / "procedure_documents_with_clusters.csv", index=False, encoding="utf-8-sig")

    pair_backend = args.pair_search_backend
    if pair_backend == "auto":
        pair_backend = "faiss" if is_faiss_available() else "sklearn"
    print(
        f"Finding candidate pairs with cosine similarity >= {args.similarity_threshold} "
        f"using {pair_backend} backend..."
    )
    candidate_pairs_df = build_duplicate_pairs(
        docs_df,
        matrix,
        args.similarity_threshold,
        args.top_pairs,
        backend=pair_backend,
        n_jobs=args.pair_search_jobs,
        within_clusters=not args.all_pairs,
    )
    candidate_pairs_df.to_csv(args.output_dir / "duplicate_pairs.csv", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    print(f"Found {len(candidate_pairs_df)} candidate pairs.")

    if args.skip_cross_encoder:
        print("Skipping CrossEncoder stage by request.")
        cross_encoder_pairs_df = candidate_pairs_df.copy()
        cross_encoder_pairs_df["cross_encoder_similarity_value"] = cross_encoder_pairs_df["similarity"]
        cross_encoder_pairs_df["cross_encoder_passed"] = True
    else:
        cross_encoder_pairs_df = add_cross_encoder_scores(
            candidate_pairs_df,
            model_name=args.cross_encoder_model,
            threshold=args.cross_encoder_threshold,
            batch_size=args.cross_encoder_batch_size,
            text_chars=args.cross_encoder_text_chars,
        )
    cross_encoder_pairs_df.to_csv(
        args.output_dir / "cross_encoder_scored_pairs.csv",
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_MINIMAL,
    )
    pairs_df = cross_encoder_pairs_df[cross_encoder_pairs_df["cross_encoder_passed"]].copy()
    print(
        f"CrossEncoder retained {len(pairs_df)} of {len(cross_encoder_pairs_df)} pairs "
        f"with score >= {args.cross_encoder_threshold}."
    )

    api_key, api_key_source = resolve_api_key(args.api_key_file)
    if args.require_api_key and not api_key:
        raise RuntimeError(f"An API key is required. Paste it into {args.api_key_file} or set API_KEY/OPENAI_API_KEY.")
    if api_key:
        print(f"OpenAI key found from {api_key_source}; analyzing up to {args.llm_limit} top pairs with {args.model}...")
    else:
        print("No API_KEY or OPENAI_API_KEY found; skipping optional OpenAI analysis.")

    final_df = add_relationship_labels(
        pairs_df,
        api_key=api_key,
        model=args.model,
        llm_limit=args.llm_limit,
        llm_workers=args.llm_workers,
        llm_text_chars=args.llm_text_chars,
        timeout=args.api_timeout,
    )
    final_df.to_csv(args.output_dir / "llm_analyzed_duplicates.csv", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    write_summary(
        args.output_dir,
        docs_df,
        candidate_pairs_df,
        cross_encoder_pairs_df,
        final_df,
        args.similarity_threshold,
        pair_backend,
        not args.all_pairs,
        {
            "umap_components": args.umap_components,
            "umap_jobs": 1 if args.umap_random_state is not None else args.umap_jobs,
            "umap_random_state": args.umap_random_state,
            "min_cluster_size": args.hdbscan_min_cluster_size,
            "min_samples": args.hdbscan_min_samples,
            "cluster_selection_epsilon": args.hdbscan_cluster_selection_epsilon,
        },
        args.cross_encoder_threshold,
    )
    print(f"Done. Outputs written to {args.output_dir}")


if __name__ == "__main__":
    main()
