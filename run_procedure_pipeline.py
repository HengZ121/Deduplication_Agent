#!/usr/bin/env python3
"""Run the procedure duplicate-detection pipeline locally.

This script is based on the drafted notebook flow:
1. load and cluster the documents,
2. find cosine-similar candidate pairs,
3. optionally ask OpenAI to classify each candidate relationship.

The notebooks were authored for Colab and an older Bible dataset. This runner
keeps the same pipeline shape while adapting the data loader to procedure.zip.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.cluster import MiniBatchKMeans
from sklearn.feature_extraction.text import TfidfVectorizer


DEFAULT_ZIP = Path("procedure.zip")
DEFAULT_OUTPUT_DIR = Path("outputs") / "procedure_pipeline"
DEFAULT_SIMILARITY_THRESHOLD = 0.45
DEFAULT_TOP_PAIRS = 500
DEFAULT_LLM_LIMIT = 25
DEFAULT_MODEL = "gpt-4o-mini"


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


def cluster_documents(df: pd.DataFrame, matrix: Any, cluster_count: int | None) -> np.ndarray:
    if cluster_count is None:
        cluster_count = min(48, max(2, round(math.sqrt(len(df)) * 1.5)))
    cluster_count = min(cluster_count, max(1, len(df)))
    model = MiniBatchKMeans(n_clusters=cluster_count, random_state=42, n_init=10, batch_size=256)
    return model.fit_predict(matrix)


def build_duplicate_pairs(
    df: pd.DataFrame,
    matrix: Any,
    threshold: float,
    top_pairs: int,
) -> pd.DataFrame:
    similarity = (matrix @ matrix.T).tocoo()
    pairs: list[dict[str, Any]] = []

    for i, j, score in zip(similarity.row, similarity.col, similarity.data):
        if i >= j or score < threshold:
            continue
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

    for row_index, row in pairs_df.head(llm_limit).iterrows():
        doc1 = str(row["item1_text"])[:llm_text_chars]
        doc2 = str(row["item2_text"])[:llm_text_chars]
        try:
            result = openai_json_request(api_key, model, doc1, doc2, timeout)
            pairs_df.at[row_index, "llm_relationship_type"] = result["relationship_type"]
            pairs_df.at[row_index, "llm_analysis"] = result["analysis"]
            time.sleep(0.1)
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
            pairs_df.at[row_index, "llm_relationship_type"] = "API_ERROR"
            pairs_df.at[row_index, "llm_analysis"] = str(exc)
    return pairs_df


def write_summary(output_dir: Path, docs_df: pd.DataFrame, pairs_df: pd.DataFrame, threshold: float) -> None:
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
        "candidate_pair_count": int(len(pairs_df)),
        "similarity_threshold": threshold,
        "outputs": [
            "procedure_documents_with_clusters.csv",
            "duplicate_pairs.csv",
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
    parser.add_argument("--clusters", type=int, default=None, help="Override the inferred cluster count.")
    parser.add_argument("--llm-limit", type=int, default=DEFAULT_LLM_LIMIT, help="Max top pairs to send to OpenAI if a key is available.")
    parser.add_argument("--llm-text-chars", type=int, default=6000, help="Max characters per document sent to OpenAI.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI chat model for optional LLM review.")
    parser.add_argument("--api-timeout", type=int, default=60)
    parser.add_argument("--require-api-key", action="store_true", help="Fail if API_KEY or OPENAI_API_KEY is not set.")
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

    print("Clustering documents...")
    docs_df["cluster_label"] = cluster_documents(docs_df, matrix, args.clusters)
    docs_df.to_csv(args.output_dir / "procedure_documents_with_clusters.csv", index=False, encoding="utf-8-sig")

    print(f"Finding candidate pairs with cosine similarity >= {args.similarity_threshold}...")
    pairs_df = build_duplicate_pairs(docs_df, matrix, args.similarity_threshold, args.top_pairs)
    pairs_df.to_csv(args.output_dir / "duplicate_pairs.csv", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    print(f"Found {len(pairs_df)} candidate pairs.")

    api_key = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")
    if args.require_api_key and not api_key:
        raise RuntimeError("API_KEY or OPENAI_API_KEY is required for this run.")
    if api_key:
        print(f"OpenAI key found; analyzing up to {args.llm_limit} top pairs with {args.model}...")
    else:
        print("No API_KEY or OPENAI_API_KEY found; skipping optional OpenAI analysis.")

    final_df = add_relationship_labels(
        pairs_df,
        api_key=api_key,
        model=args.model,
        llm_limit=args.llm_limit,
        llm_text_chars=args.llm_text_chars,
        timeout=args.api_timeout,
    )
    final_df.to_csv(args.output_dir / "llm_analyzed_duplicates.csv", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    write_summary(args.output_dir, docs_df, final_df, args.similarity_threshold)
    print(f"Done. Outputs written to {args.output_dir}")


if __name__ == "__main__":
    main()
