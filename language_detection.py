#!/usr/bin/env python3
"""Transformer-based language identification for deduplication nodes."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_LANGUAGE_DETECTION_MODEL = "papluca/xlm-roberta-base-language-detection"
LANGUAGE_PREDICTION_COLUMNS = [
    "node_index",
    "node_id",
    "predicted_language",
    "language_confidence",
    "language_model",
]


def predict_languages_with_transformer(
    texts: Iterable[str],
    model_name: str = DEFAULT_LANGUAGE_DETECTION_MODEL,
    batch_size: int = 32,
    max_length: int = 256,
) -> tuple[list[str], list[float]]:
    """Predict ISO language labels and confidence with a sequence classifier."""

    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "Transformer language detection requires torch and transformers."
        ) from exc

    from tqdm.auto import tqdm

    values = [str(text).strip() for text in texts]
    labels = [""] * len(values)
    confidences = [0.0] * len(values)
    nonempty_indices = [index for index, value in enumerate(values) if value]
    if not nonempty_indices:
        return labels, confidences

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading language detector '{model_name}' on {device}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device)
    model.eval()
    id2label = {
        int(index): str(label).lower()
        for index, label in model.config.id2label.items()
    }

    for start in tqdm(
        range(0, len(nonempty_indices), batch_size),
        desc="Transformer language detection",
    ):
        batch_indices = nonempty_indices[start : start + batch_size]
        encoded = tokenizer(
            [values[index] for index in batch_indices],
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.inference_mode():
            probabilities = torch.softmax(model(**encoded).logits, dim=-1)
        batch_confidences, batch_label_ids = probabilities.max(dim=-1)
        for index, label_id, confidence in zip(
            batch_indices,
            batch_label_ids.cpu().tolist(),
            batch_confidences.cpu().tolist(),
        ):
            labels[index] = id2label[int(label_id)]
            confidences[index] = float(confidence)

    del model
    if device == "cuda":
        torch.cuda.empty_cache()
    return labels, confidences


def build_language_predictions(
    comparable_df: pd.DataFrame,
    model_name: str = DEFAULT_LANGUAGE_DETECTION_MODEL,
    batch_size: int = 32,
    max_length: int = 256,
) -> pd.DataFrame:
    """Create a node-aligned table of Transformer language predictions."""

    labels, confidences = predict_languages_with_transformer(
        comparable_df["text"].fillna("").astype(str).tolist(),
        model_name=model_name,
        batch_size=batch_size,
        max_length=max_length,
    )
    return pd.DataFrame(
        {
            "node_index": np.arange(len(comparable_df), dtype=np.int64),
            "node_id": comparable_df["node_id"].astype(str).to_numpy(),
            "predicted_language": labels,
            "language_confidence": confidences,
            "language_model": model_name,
        },
        columns=LANGUAGE_PREDICTION_COLUMNS,
    )


def validate_language_predictions(
    predictions_df: pd.DataFrame,
    comparable_df: pd.DataFrame,
    model_name: str,
) -> None:
    """Ensure cached predictions correspond exactly to the current node table."""

    missing = sorted(set(LANGUAGE_PREDICTION_COLUMNS) - set(predictions_df.columns))
    if missing:
        raise ValueError(f"Language prediction cache is missing columns: {', '.join(missing)}")
    if len(predictions_df) != len(comparable_df):
        raise ValueError("Language prediction cache does not match the current node count.")
    expected_indices = np.arange(len(comparable_df), dtype=np.int64)
    actual_indices = pd.to_numeric(
        predictions_df["node_index"], errors="raise"
    ).to_numpy(dtype=np.int64)
    if not np.array_equal(actual_indices, expected_indices):
        raise ValueError("Language prediction cache node indices are not aligned.")
    if not np.array_equal(
        predictions_df["node_id"].astype(str).to_numpy(),
        comparable_df["node_id"].astype(str).to_numpy(),
    ):
        raise ValueError("Language prediction cache was created from different nodes.")
    cached_models = set(predictions_df["language_model"].astype(str))
    if cached_models != {model_name}:
        raise ValueError("Language prediction cache was created with a different model.")


def exclude_model_detected_english_french_pairs(
    pairs_df: pd.DataFrame,
    predictions_df: pd.DataFrame,
    confidence_threshold: float,
) -> tuple[pd.DataFrame, int]:
    """Exclude confident EN/FR pairs using only Transformer predictions."""

    if pairs_df.empty:
        return pairs_df.copy(), 0
    predicted = predictions_df["predicted_language"].fillna("").astype(str).str.lower().to_numpy()
    confidence = pd.to_numeric(
        predictions_df["language_confidence"], errors="raise"
    ).to_numpy(dtype=float)
    confident_language = np.where(confidence >= confidence_threshold, predicted, "")
    left_indices = pd.to_numeric(
        pairs_df["item1_index"], errors="raise"
    ).to_numpy(dtype=np.int64)
    right_indices = pd.to_numeric(
        pairs_df["item2_index"], errors="raise"
    ).to_numpy(dtype=np.int64)
    left_languages = confident_language[left_indices]
    right_languages = confident_language[right_indices]
    cross_language = ((left_languages == "en") & (right_languages == "fr")) | (
        (left_languages == "fr") & (right_languages == "en")
    )
    return pairs_df.loc[~cross_language].reset_index(drop=True), int(cross_language.sum())
