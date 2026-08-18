#!/usr/bin/env python3
"""Find unique procedure.zip sentences with multiple FrameNet candidates.

FrameNet's NLTK corpus reader is a lexical registry, not a semantic parser.  The
frames written by this script are therefore *candidate* frames supported by a
visible FrameNet lexical-unit surface form.  Keeping that distinction in the
output prevents a polysemous word from being mistaken for a confirmed frame.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from count_framenet_candidates import (
    Candidate,
    build_lu_index,
    extract_member_text,
    is_meaningful_sentence,
    normalize_sentence,
    sentence_forms,
)
from framenet_mapper import SENTENCE_PATTERN


DEFAULT_ZIP = Path("procedure.zip")
DEFAULT_CSV = Path("outputs") / "procedure_sentences_with_multiple_frames.csv"
SUPPORTED_SUFFIXES = {".json", ".txt", ".md", ".docx"}


def match_candidate_frames(
    sentence: str,
    lu_index: dict[str, list[Candidate]],
) -> list[dict[str, Any]]:
    """Return every distinct candidate frame and all of its lexical evidence."""
    evidence_by_frame: dict[tuple[str, int], dict[str, set[str]]] = defaultdict(
        lambda: {
            "matchedForms": set(),
            "lexicalUnits": set(),
            "partsOfSpeech": set(),
        }
    )

    # The index and sentence form generator are shared with the corpus-wide
    # frame counter, so both reports use exactly the same matching semantics.
    for form in sentence_forms(sentence):
        for candidate in lu_index.get(form, ()):
            evidence = evidence_by_frame[(candidate.frame, candidate.frame_id)]
            evidence["matchedForms"].add(form)
            evidence["lexicalUnits"].add(candidate.lexical_unit)
            evidence["partsOfSpeech"].add(candidate.part_of_speech)

    return [
        {
            "frame": frame,
            "frameId": frame_id,
            "matchedForms": sorted(evidence["matchedForms"]),
            "lexicalUnits": sorted(evidence["lexicalUnits"]),
            "partsOfSpeech": sorted(evidence["partsOfSpeech"]),
            "confidence": "lexical_match_candidate",
        }
        for (frame, frame_id), evidence in sorted(
            evidence_by_frame.items(), key=lambda item: (item[0][0], item[0][1])
        )
    ]


def normalize_zip_paths(zip_paths: Path | Sequence[Path]) -> tuple[Path, ...]:
    """Return a validated, non-empty archive sequence for pipeline processing."""
    paths = (zip_paths,) if isinstance(zip_paths, Path) else tuple(zip_paths)
    if not paths:
        raise ValueError("At least one input zip file is required.")
    return paths


def iter_archive_sentences(zip_paths: Path | Sequence[Path]) -> Iterable[tuple[str, str]]:
    """Yield traceable source members and sentences from one or more archives."""
    paths = normalize_zip_paths(zip_paths)
    qualify_source = len(paths) > 1
    for zip_path in paths:
        with zipfile.ZipFile(zip_path) as archive:
            for name in archive.namelist():
                if name.endswith("/") or Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
                    continue
                try:
                    text = extract_member_text(name, archive.read(name))
                except Exception:
                    # One malformed member should not prevent analysis of the
                    # remaining files in a heterogeneous source export.
                    continue
                if not text:
                    continue
                # Archive qualification prevents same-named members from two
                # data sources being collapsed in the provenance columns.
                source_document = f"{zip_path.name}::{name}" if qualify_source else name
                for sentence in (part.strip() for part in SENTENCE_PATTERN.split(text)):
                    if sentence:
                        yield source_document, sentence


def find_multi_frame_sentences(
    zip_path: Path | Sequence[Path],
    csv_path: Path,
    json_path: Path | None = None,
    lu_index: dict[str, list[Candidate]] | None = None,
    meaningful_only: bool = True,
) -> dict[str, Any]:
    """Analyze the archive, write multi-frame sentences, and return run metadata."""
    started = time.time()
    zip_paths = normalize_zip_paths(zip_path)
    index = lu_index if lu_index is not None else build_lu_index()
    sentence_records: dict[str, dict[str, Any]] = {}
    raw_occurrences = 0

    for source_document, sentence in iter_archive_sentences(zip_paths):
        raw_occurrences += 1
        normalized = normalize_sentence(sentence)
        if not normalized:
            continue
        record = sentence_records.get(normalized)
        if record is None:
            record = {
                "sentence": sentence,
                "normalizedSentence": normalized,
                "occurrenceCount": 0,
                "sourceDocuments": set(),
            }
            sentence_records[normalized] = record
        record["occurrenceCount"] += 1
        record["sourceDocuments"].add(source_document)

    rows: list[dict[str, Any]] = []
    eligible_unique_sentences = 0
    matched_unique_sentences = 0
    for record in sentence_records.values():
        passes_policy_filter = is_meaningful_sentence(record["sentence"])
        if meaningful_only and not passes_policy_filter:
            continue
        eligible_unique_sentences += 1
        frames = match_candidate_frames(record["sentence"], index)
        if frames:
            matched_unique_sentences += 1
        if len(frames) <= 1:
            continue
        rows.append(
            {
                "sentence": record["sentence"],
                "normalizedSentence": record["normalizedSentence"],
                "frameCount": len(frames),
                "frames": frames,
                "occurrenceCount": record["occurrenceCount"],
                "sourceDocuments": sorted(record["sourceDocuments"]),
                "passesPolicySentenceFilter": passes_policy_filter,
            }
        )

    rows.sort(key=lambda row: (-row["frameCount"], row["normalizedSentence"]))
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "sentence",
                "frameCount",
                "frames",
                "frameIds",
                "occurrenceCount",
                "sourceDocumentCount",
                "sourceDocuments",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["sentence"],
                    row["frameCount"],
                    "; ".join(frame["frame"] for frame in row["frames"]),
                    "; ".join(str(frame["frameId"]) for frame in row["frames"]),
                    row["occurrenceCount"],
                    len(row["sourceDocuments"]),
                    "; ".join(row["sourceDocuments"]),
                ]
            )

    summary = {
        "input": str(zip_paths[0]) if len(zip_paths) == 1 else [str(path) for path in zip_paths],
        "archiveCount": len(zip_paths),
        "matchingMethod": "FrameNet 1.7 visible lexical-unit surface-form candidates",
        "rawSentenceOccurrences": raw_occurrences,
        "uniqueExtractedSentenceFragments": len(sentence_records),
        "meaningfulPolicyFilterApplied": meaningful_only,
        "eligibleUniqueSentences": eligible_unique_sentences,
        "uniqueSentencesWithAnyFrame": matched_unique_sentences,
        "uniqueSentencesWithMultipleFrames": len(rows),
        "lexicalUnitSurfaceForms": len(index),
        "csvOutput": str(csv_path),
        "jsonOutput": str(json_path) if json_path else None,
        "elapsedSeconds": round(time.time() - started, 2),
    }
    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps({"summary": summary, "sentences": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--zip",
        type=Path,
        action="append",
        dest="zip_paths",
        help="Input dataset zip file. Repeat this option to combine multiple sources.",
    )
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional detailed JSON output with lexical-unit evidence.",
    )
    parser.add_argument(
        "--include-all-fragments",
        action="store_true",
        help="Include headings, navigation labels, and other non-policy fragments.",
    )
    args = parser.parse_args()
    summary = find_multi_frame_sentences(
        args.zip_paths or [DEFAULT_ZIP],
        args.csv_output,
        args.json_output,
        meaningful_only=not args.include_all_fragments,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
