#!/usr/bin/env python3
"""Generate 50 real-text Verification mappings with local BERT evidence."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from framenet_registry import registry
from hybrid_frame_mapper import BERT_MODEL_NAME, hybrid_frame_mapping


INPUT = Path("outputs") / "data1_data2_frame_mapper_results.csv"
OUTPUT = Path("outputs") / "verification_frame_bert_mappings_50.csv"
SAMPLE_SIZE = 50
TARGET_FRAME = "Verification"
TARGET_FRAME_ID = 1230

FIELDNAMES = (
    "record_id",
    "text",
    "mapped_frames",
    "primary_frame",
    "primary_frame_id",
    "trigger",
    "verification_rule_score",
    "verification_bert_score",
    "verification_combined_score",
    "verification_candidate_rank",
    "alternative_frame",
    "alternative_rule_score",
    "alternative_bert_score",
    "alternative_combined_score",
    "inspector",
    "unconfirmed_content",
    "medium",
    "means",
    "purpose",
    "frame_elements_json",
    "bert_model",
    "bert_frame_method",
    "bert_frame_status",
    "bert_qa_status",
    "source_occurrence_count",
    "source_document_count",
    "source_documents",
)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _lexical_group(lexical_unit: str) -> str:
    if lexical_unit.startswith("verify") or lexical_unit.startswith("verification"):
        return "verify"
    if lexical_unit.startswith("confirm"):
        return "confirm"
    return "other"


def _selection_key(row: dict[str, str]) -> tuple[int, int, int, int, str]:
    """Prefer precise, readable examples while keeping selection deterministic."""
    text = row["sentence"].strip()
    return (
        int((row.get("verificationLexicalUnit") or "").endswith(".n")),
        _int(row.get("rawFrameCount"), 9999),
        abs(len(text) - 150),
        len(text),
        text.casefold(),
    )


def select_verification_texts(
    rows: Iterable[dict[str, str]],
    sample_size: int = SAMPLE_SIZE,
) -> list[dict[str, str]]:
    """Select balanced official-LU examples already discovered by FrameNet."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen: set[str] = set()
    for row in rows:
        text = (row.get("sentence") or "").strip()
        raw_frames = {item.strip() for item in (row.get("rawFrames") or "").split(";")}
        if TARGET_FRAME not in raw_frames or text in seen:
            continue
        if not 35 <= len(text) <= 420 or not 7 <= len(text.split()) <= 70:
            continue
        if row.get("status") in {"filtered_artifact", "structured_non_frame"}:
            continue
        lexical_match = registry.match_lexical_unit(text, TARGET_FRAME)
        if not lexical_match:
            continue
        row = dict(row)
        row["verificationLexicalUnit"] = lexical_match["lexicalUnit"]
        row["verificationMatchedText"] = lexical_match["text"]
        grouped[_lexical_group(lexical_match["lexicalUnit"])].append(row)
        seen.add(text)

    verify_quota = sample_size // 2
    quotas = {
        "verify": verify_quota,
        "confirm": sample_size - verify_quota,
        "other": 0,
    }
    selected: list[dict[str, str]] = []
    for group, quota in quotas.items():
        selected.extend(sorted(grouped[group], key=_selection_key)[:quota])

    if len(selected) < sample_size:
        chosen = {row["sentence"] for row in selected}
        remaining = sorted(
            (row for values in grouped.values() for row in values if row["sentence"] not in chosen),
            key=_selection_key,
        )
        selected.extend(remaining[: sample_size - len(selected)])
    if len(selected) != sample_size:
        raise RuntimeError(f"Needed {sample_size} Verification texts, found {len(selected)}")
    return selected


def _element_text(elements: dict[str, Any], name: str) -> str:
    value = elements.get(name) or {}
    return str(value.get("text") or "")


def map_row(row: dict[str, str], record_id: int) -> dict[str, Any]:
    text = row["sentence"].strip()
    event = hybrid_frame_mapping(text, record_id - 1, use_bert=True, target_frame=TARGET_FRAME)
    if event is None:
        raise RuntimeError(f"Target frame did not match record {record_id}: {text}")

    scoring = event["hybridScoring"]
    candidates = scoring["candidateFrames"]
    verification = next(item for item in candidates if item["frame"] == TARGET_FRAME)
    alternative = next((item for item in candidates if item["frame"] != TARGET_FRAME), None)
    bert_info = scoring["bertFrameScorer"]
    qa_info = event["bertElementExtraction"]
    if bert_info.get("status") != "scored" or qa_info.get("status") != "scored":
        raise RuntimeError(
            f"Local BERT was not used for record {record_id}: "
            f"frame={bert_info.get('status')}, qa={qa_info.get('status')}"
        )

    elements = event["frameElements"]
    mapped_frames = TARGET_FRAME
    if alternative:
        mapped_frames += f"; {alternative['frame']}"
    return {
        "record_id": record_id,
        "text": text,
        "mapped_frames": mapped_frames,
        "primary_frame": TARGET_FRAME,
        "primary_frame_id": event["frameNet"]["frameId"],
        "trigger": event["trigger"],
        "verification_rule_score": verification["ruleScore"],
        "verification_bert_score": verification["bertFrameScore"],
        "verification_combined_score": verification["combinedScore"],
        "verification_candidate_rank": scoring["selectedCandidateRank"],
        "alternative_frame": alternative["frame"] if alternative else "",
        "alternative_rule_score": alternative["ruleScore"] if alternative else "",
        "alternative_bert_score": alternative["bertFrameScore"] if alternative else "",
        "alternative_combined_score": alternative["combinedScore"] if alternative else "",
        "inspector": _element_text(elements, "Inspector"),
        "unconfirmed_content": _element_text(elements, "Unconfirmed_content"),
        "medium": _element_text(elements, "Medium"),
        "means": _element_text(elements, "Means"),
        "purpose": _element_text(elements, "Purpose"),
        "frame_elements_json": json.dumps(elements, ensure_ascii=False, separators=(",", ":")),
        "bert_model": BERT_MODEL_NAME,
        "bert_frame_method": bert_info["method"],
        "bert_frame_status": bert_info["status"],
        "bert_qa_status": qa_info["status"],
        "source_occurrence_count": _int(row.get("occurrenceCount")),
        "source_document_count": _int(row.get("sourceDocumentCount")),
        "source_documents": row.get("sourceDocuments") or "",
    }


def generate(input_path: Path = INPUT, output_path: Path = OUTPUT) -> dict[str, Any]:
    if not registry.available:
        raise RuntimeError("FrameNet 1.7 is required to verify the Verification frame and lexical units")
    summary = registry.frame_summary(TARGET_FRAME)
    if not summary or summary["id"] != TARGET_FRAME_ID:
        raise RuntimeError("Unexpected FrameNet Verification frame metadata")

    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        selected = select_verification_texts(csv.DictReader(handle))
    mapped = [map_row(row, index) for index, row in enumerate(selected, start=1)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(mapped)

    return {
        "rows": len(mapped),
        "output": str(output_path),
        "frame": TARGET_FRAME,
        "frameId": TARGET_FRAME_ID,
        "bertModel": BERT_MODEL_NAME,
        "alternativeFrameRows": sum(bool(row["alternative_frame"]) for row in mapped),
    }


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2))
