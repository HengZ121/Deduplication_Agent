#!/usr/bin/env python3
"""Apply domain frame canonicalization to the multi-frame sentence report."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

from domain_frame_canonicalizer import CANONICAL_DOMAIN_FRAMES, canonicalizer


DEFAULT_INPUT = Path("outputs") / "procedure_sentences_with_multiple_frames.csv"
DEFAULT_OUTPUT = Path("outputs") / "procedure_sentences_canonicalized.csv"
DEFAULT_SUMMARY = Path("outputs") / "procedure_frame_canonicalization_summary.json"


def parse_frames(value: str) -> tuple[str, ...]:
    return tuple(frame.strip() for frame in value.split(";") if frame.strip())


def canonicalize_report(
    input_path: Path,
    output_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    started = time.time()
    rows: list[dict[str, Any]] = []
    raw_frame_frequency: Counter[str] = Counter()
    canonical_frame_frequency: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    rule_counts: Counter[str] = Counter()
    structured_counts: Counter[str] = Counter()
    suppressed_counts: Counter[str] = Counter()
    raw_counts: list[int] = []
    canonical_counts: list[int] = []

    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        for source in csv.DictReader(handle):
            raw_frames = parse_frames(source["frames"])
            result = canonicalizer.canonicalize(source["sentence"], raw_frames)
            value = result.to_dict()
            raw_frame_frequency.update(raw_frames)
            canonical_frame_frequency.update(value["canonicalFrames"])
            status_counts[value["status"]] += 1
            rule_counts.update(value["rulesApplied"])
            structured_counts.update(value["structuredKnowledge"])
            suppressed_counts.update(value["explicitlySuppressedFrames"])
            raw_counts.append(len(raw_frames))
            canonical_counts.append(len(value["canonicalFrames"]))
            rows.append(
                {
                    "sentence": source["sentence"],
                    "status": value["status"],
                    "confidence": value["confidence"],
                    "canonicalFrameCount": value["canonicalFrameCount"],
                    "canonicalFrames": "; ".join(value["canonicalFrames"]),
                    "structuredKnowledge": "; ".join(value["structuredKnowledge"]),
                    "rulesApplied": "; ".join(value["rulesApplied"]),
                    "reviewCandidates": "; ".join(value["reviewCandidates"]),
                    "explicitlySuppressedFrames": "; ".join(value["explicitlySuppressedFrames"]),
                    "rawFrameCount": value["rawFrameCount"],
                    "rawFrames": source["frames"],
                    "occurrenceCount": source["occurrenceCount"],
                    "sourceDocumentCount": source["sourceDocumentCount"],
                    "sourceDocuments": source["sourceDocuments"],
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    resolved = status_counts["canonical_frame"] + status_counts["structured_non_frame"]
    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "sentences": total,
        "rawDistinctFrames": len(raw_frame_frequency),
        "approvedInventoryFrames": len(CANONICAL_DOMAIN_FRAMES),
        "observedCanonicalFrames": len(canonical_frame_frequency),
        "meanRawFramesPerSentence": round(statistics.mean(raw_counts), 2),
        "meanCanonicalFramesPerSentence": round(statistics.mean(canonical_counts), 2),
        "medianRawFramesPerSentence": statistics.median(raw_counts),
        "medianCanonicalFramesPerSentence": statistics.median(canonical_counts),
        "statusCounts": dict(status_counts),
        "resolvedSentenceRate": round(resolved / total, 4),
        "canonicalSentenceRate": round(status_counts["canonical_frame"] / total, 4),
        "structuredNonFrameRate": round(status_counts["structured_non_frame"] / total, 4),
        "reviewRate": round(status_counts["needs_review"] / total, 4),
        "topCanonicalFrames": canonical_frame_frequency.most_common(20),
        "topRules": rule_counts.most_common(25),
        "topStructuredKnowledge": structured_counts.most_common(15),
        "topExplicitlySuppressedFrames": suppressed_counts.most_common(25),
        "rawCollisionFrameOccurrences": {
            frame: raw_frame_frequency[frame]
            for frame in (
                "Assemble",
                "Come_together",
                "Grooming",
                "Cause_change_of_consistency",
                "Change_of_consistency",
                "Rate_quantification",
                "Relational_quantity",
                "Killing",
                "Unemployment_rate",
            )
        },
        "elapsedSeconds": round(time.time() - started, 2),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    print(json.dumps(canonicalize_report(args.input, args.output, args.summary_output), indent=2))


if __name__ == "__main__":
    main()
