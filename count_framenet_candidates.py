#!/usr/bin/env python3
"""Count FrameNet lexical-unit candidate frames across procedure.zip."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framenet_mapper import SENTENCE_PATTERN, clean_text, extract_document_text
from framenet_registry import registry


TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z'-]*|\d+")
DEFAULT_ZIP = Path("procedure.zip")
DEFAULT_OUTPUT = Path("outputs") / "framenet_candidate_frame_counts.csv"
STOP_FORMS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "for",
    "from",
    "if",
    "in",
    "is",
    "it",
    "may",
    "must",
    "of",
    "on",
    "or",
    "the",
    "to",
    "when",
    "with",
}


@dataclass(frozen=True)
class Candidate:
    frame: str
    frame_id: int
    lexical_unit: str
    part_of_speech: str


def surface_forms(lemma: str, part_of_speech: str) -> set[str]:
    """Mirror the mapper's lightweight FrameNet surface-form expansion."""
    if " " in lemma:
        return {lemma.lower()}
    forms = {lemma.lower()}
    if part_of_speech == "v":
        if lemma.endswith("e"):
            forms.update({lemma + "d", lemma + "s", lemma[:-1] + "ing"})
        elif lemma.endswith("y"):
            forms.update({lemma[:-1] + "ied", lemma[:-1] + "ies", lemma + "ing"})
        else:
            forms.update({lemma + "ed", lemma + "s", lemma + "ing", lemma + "es"})
    elif part_of_speech == "n":
        forms.add(lemma + ("es" if lemma.endswith(("s", "x", "z", "ch", "sh")) else "s"))
    return {form.lower() for form in forms}


def build_lu_index() -> dict[str, list[Candidate]]:
    if not registry.available:
        raise RuntimeError(f"FrameNet registry unavailable: {registry.error}")

    index: dict[str, list[Candidate]] = {}
    for lexical_unit in registry._fn.lus():
        name = lexical_unit.name
        lemma, _, part_of_speech = name.rpartition(".")
        surface_lemma = re.sub(r"\s*\[[^]]+\]$", "", lemma)
        if not surface_lemma or part_of_speech not in {"v", "n", "a", "adv", "prep"}:
            continue
        for form in surface_forms(surface_lemma, part_of_speech):
            if len(form) < 3 or form in STOP_FORMS:
                continue
            index.setdefault(form, []).append(
                Candidate(
                    frame=lexical_unit.frame.name,
                    frame_id=lexical_unit.frame.ID,
                    lexical_unit=name,
                    part_of_speech=part_of_speech,
                )
            )
    return index


def sentence_forms(sentence: str, max_phrase_tokens: int = 4) -> set[str]:
    tokens = [match.group(0).lower() for match in TOKEN_PATTERN.finditer(sentence)]
    forms = {token for token in tokens if len(token) >= 3 and token not in STOP_FORMS}
    for width in range(2, max_phrase_tokens + 1):
        for start in range(0, len(tokens) - width + 1):
            phrase = " ".join(tokens[start : start + width])
            if all(part not in STOP_FORMS for part in phrase.split()):
                forms.add(phrase)
    return forms


def collect_json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(collect_json_text(item) for item in value)
    if isinstance(value, dict):
        preferred = [value[key] for key in ("title", "summary", "text", "content", "description") if key in value]
        values = preferred or list(value.values())
        return "\n".join(collect_json_text(item) for item in values)
    return ""


def extract_member_text(name: str, content: bytes) -> str:
    if Path(name).suffix.lower() == ".json":
        try:
            return clean_text(collect_json_text(json.loads(content.decode("utf-8-sig"))))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return extract_document_text(name, content)
    return extract_document_text(name, content)


def count_candidates(zip_path: Path, output_path: Path) -> dict[str, int]:
    started = time.time()
    index = build_lu_index()
    frame_counts: Counter[tuple[str, int]] = Counter()
    lu_counts: Counter[tuple[str, int, str, str]] = Counter()
    docs = sentences = matched_sentences = 0

    with zipfile.ZipFile(zip_path) as archive:
        members = [name for name in archive.namelist() if not name.endswith("/")]
        for name in members:
            if Path(name).suffix.lower() not in {".json", ".txt", ".md", ".docx"}:
                continue
            try:
                text = extract_member_text(name, archive.read(name))
            except Exception:
                continue
            if not text:
                continue
            docs += 1
            for sentence in (item.strip() for item in SENTENCE_PATTERN.split(text) if item.strip()):
                sentences += 1
                matched_this_sentence: set[tuple[str, int]] = set()
                matched_lus: set[tuple[str, int, str, str]] = set()
                for form in sentence_forms(sentence):
                    for candidate in index.get(form, ()):
                        frame_key = (candidate.frame, candidate.frame_id)
                        lu_key = (
                            candidate.frame,
                            candidate.frame_id,
                            candidate.lexical_unit,
                            candidate.part_of_speech,
                        )
                        matched_this_sentence.add(frame_key)
                        matched_lus.add(lu_key)
                if matched_this_sentence:
                    matched_sentences += 1
                    frame_counts.update(matched_this_sentence)
                    lu_counts.update(matched_lus)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "frame",
                "frameId",
                "sentenceOccurrences",
                "matchedLexicalUnitOccurrences",
            ]
        )
        for (frame, frame_id), count in sorted(frame_counts.items(), key=lambda item: (-item[1], item[0])):
            lu_total = sum(
                value
                for (lu_frame, lu_frame_id, _lu, _pos), value in lu_counts.items()
                if lu_frame == frame and lu_frame_id == frame_id
            )
            writer.writerow([frame, frame_id, count, lu_total])

    return {
        "documents": docs,
        "sentences": sentences,
        "matchedSentences": matched_sentences,
        "frames": len(frame_counts),
        "lexicalUnitSurfaceForms": len(index),
        "elapsedSeconds": round(time.time() - started, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = count_candidates(args.zip, args.output)
    summary["output"] = str(args.output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
