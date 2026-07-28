#!/usr/bin/env python3
"""Count FrameNet lexical-unit candidate frames across procedure.zip."""

from __future__ import annotations

import argparse
import csv
import html
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
DEFAULT_SAMPLES = Path("outputs") / "framenet_candidate_frame_samples.md"
DEFAULT_HTML = Path("outputs") / "framenet_candidate_frame_samples.html"
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


def count_candidates(
    zip_path: Path,
    output_path: Path,
    samples_path: Path | None = None,
    html_path: Path | None = None,
    sample_threshold: int = 800,
    samples_per_frame: int = 10,
) -> dict[str, int]:
    started = time.time()
    index = build_lu_index()
    frame_counts: Counter[tuple[str, int]] = Counter()
    lu_counts: Counter[tuple[str, int, str, str]] = Counter()
    docs = sentences = matched_sentences = 0
    frame_samples: dict[tuple[str, int], list[str]] = {}

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
                    for frame_key in matched_this_sentence:
                        samples = frame_samples.setdefault(frame_key, [])
                        if len(samples) < samples_per_frame and sentence not in samples:
                            samples.append(sentence)

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

    sample_rows = [
        {
            "frame": frame,
            "frameId": frame_id,
            "sentenceOccurrences": frame_counts[(frame, frame_id)],
            "matchedLexicalUnitOccurrences": sum(
                value
                for (lu_frame, lu_frame_id, _lu, _pos), value in lu_counts.items()
                if lu_frame == frame and lu_frame_id == frame_id
            ),
            "samples": frame_samples.get((frame, frame_id), [])[:samples_per_frame],
        }
        for frame, frame_id in frame_counts
        if frame_counts[(frame, frame_id)] > sample_threshold
    ]
    sample_rows.sort(key=lambda item: (-item["sentenceOccurrences"], item["frame"]))
    if samples_path:
        write_samples_markdown(samples_path, sample_rows, sample_threshold, samples_per_frame)
    if html_path:
        write_samples_html(html_path, sample_rows, sample_threshold, samples_per_frame)

    return {
        "documents": docs,
        "sentences": sentences,
        "matchedSentences": matched_sentences,
        "frames": len(frame_counts),
        "framesOverSampleThreshold": len(sample_rows),
        "lexicalUnitSurfaceForms": len(index),
        "elapsedSeconds": round(time.time() - started, 2),
    }


def write_samples_markdown(
    path: Path,
    rows: list[dict[str, Any]],
    sample_threshold: int,
    samples_per_frame: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Frame Candidate Samples\n\n")
        handle.write(
            f"Frames included: sentence occurrence count greater than {sample_threshold}. "
            f"Up to {samples_per_frame} local procedure-corpus samples are shown per frame.\n\n"
        )
        handle.write(
            "These are lexical-unit candidate examples, not confirmed semantic annotations. "
            "Use them to judge whether a frame is worth deeper mapping work.\n\n"
        )
        for row in rows:
            handle.write(
                f"## {row['frame']} (#{row['frameId']})\n\n"
                f"- sentenceOccurrences: {row['sentenceOccurrences']}\n"
                f"- matchedLexicalUnitOccurrences: {row['matchedLexicalUnitOccurrences']}\n\n"
            )
            for index, sample in enumerate(row["samples"], 1):
                handle.write(f"{index}. {sample}\n")
            handle.write("\n")


def write_samples_html(
    path: Path,
    rows: list[dict[str, Any]],
    sample_threshold: int,
    samples_per_frame: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cards = []
    for row in rows:
        samples = "".join(f"<li>{html.escape(sample)}</li>" for sample in row["samples"])
        cards.append(
            "<section class='frame-card' "
            f"data-frame='{html.escape(row['frame'].lower())}'>"
            f"<h2>{html.escape(row['frame'])} <span>#{row['frameId']}</span></h2>"
            "<div class='stats'>"
            f"<span>{row['sentenceOccurrences']} sentence occurrences</span>"
            f"<span>{row['matchedLexicalUnitOccurrences']} LU matches</span>"
            "</div>"
            f"<ol>{samples}</ol>"
            "</section>"
        )
    body = "\n".join(cards)
    path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Frame Candidate Samples</title>
<style>
:root{{font-family:Inter,system-ui,sans-serif;color:#182235;background:#f5f7fb}}
body{{margin:0}}main{{max-width:1120px;margin:auto;padding:28px 20px}}
h1{{margin:0 0 8px;font-size:28px}}p{{color:#5a6578}}
.toolbar{{position:sticky;top:0;background:#f5f7fb;padding:12px 0 16px;border-bottom:1px solid #dce3ee}}
input{{width:100%;padding:11px 12px;border:1px solid #bcc8d8;border-radius:8px;font:inherit}}
.frame-card{{background:#fff;border:1px solid #dce3ee;border-radius:10px;margin:14px 0;padding:16px;box-shadow:0 8px 24px #23324a10}}
h2{{margin:0 0 8px;font-size:20px}}h2 span{{font-weight:500;color:#6b7588}}
.stats{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}}
.stats span{{background:#eef3fb;border-radius:999px;padding:4px 9px;color:#40506a;font-size:13px}}
li{{margin:7px 0;line-height:1.45}}
</style>
</head>
<body>
<main>
<h1>Frame Candidate Samples</h1>
<p>Frames with more than {sample_threshold} sentence occurrences. Up to {samples_per_frame} samples per frame. Lexical evidence only, not confirmed annotation.</p>
<div class="toolbar"><input id="filter" placeholder="Filter frames, e.g. Evidence, Activity_stop, benefit"></div>
{body}
</main>
<script>
const filter=document.querySelector('#filter'),cards=[...document.querySelectorAll('.frame-card')];
filter.addEventListener('input',()=>{{const q=filter.value.trim().toLowerCase();for(const card of cards)card.style.display=card.dataset.frame.includes(q)?'':'none'}});
</script>
</body>
</html>
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--samples-output", type=Path, default=DEFAULT_SAMPLES)
    parser.add_argument("--html-output", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--sample-threshold", type=int, default=800)
    parser.add_argument("--samples-per-frame", type=int, default=10)
    args = parser.parse_args()
    summary = count_candidates(
        args.zip,
        args.output,
        args.samples_output,
        args.html_output,
        args.sample_threshold,
        args.samples_per_frame,
    )
    summary["output"] = str(args.output)
    summary["samplesOutput"] = str(args.samples_output)
    summary["htmlOutput"] = str(args.html_output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
