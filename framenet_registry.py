#!/usr/bin/env python3
"""Authoritative FrameNet 1.7 registry backed by the NLTK corpus API."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any


FRAMENET_VERSION = "1.7"


class FrameNetRegistry:
    """Expose small, JSON-safe views of the official FrameNet corpus.

    NLTK is a corpus reader, not an automatic annotator. This class deliberately
    limits it to registry, validation, LU evidence, and exemplar responsibilities.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path(__file__).resolve().parent
        self.available = False
        self.error: str | None = None
        self._fn: Any = None
        try:
            import nltk

            for folder in (self.project_root / ".nltk_data_clean", self.project_root / ".nltk_data"):
                if folder.exists() and str(folder) not in nltk.data.path:
                    nltk.data.path.insert(0, str(folder))
            from nltk.corpus import framenet as fn

            # Force a small lookup so missing/partial corpora fail at startup.
            fn.frame("Rewards_and_punishments")
            self._fn = fn
            self.available = True
        except (ImportError, LookupError, OSError, ValueError) as error:
            self.error = str(error).strip().splitlines()[0]

    @lru_cache(maxsize=32)
    def frame_summary(self, frame_name: str) -> dict[str, Any] | None:
        if not self.available:
            return None
        try:
            frame = self._fn.frame(frame_name)
        except Exception:
            return None
        return {
            "id": frame.ID,
            "name": frame.name,
            "definition": _plain_definition(frame.definition),
            "frameElements": {
                name: {
                    "id": fe.ID,
                    "name": name,
                    "coreType": fe.coreType,
                    "definition": _plain_definition(fe.definition),
                }
                for name, fe in frame.FE.items()
            },
            "lexicalUnits": sorted(frame.lexUnit.keys()),
            "relations": [str(relation) for relation in frame.frameRelations],
        }

    @lru_cache(maxsize=64)
    def exemplars(
        self,
        frame_name: str,
        lexical_unit: str | None = None,
        limit: int = 2,
    ) -> tuple[dict[str, Any], ...]:
        if not self.available:
            return ()
        frame = self._fn.frame(frame_name)
        if lexical_unit:
            pattern = rf"^{re.escape(lexical_unit)}$"
            examples = [
                example
                for example in self._fn.exemplars(luNamePattern=pattern)
                if example.frame.name == frame_name
            ]
        else:
            examples = list(self._fn.exemplars(frame=frame))
        return tuple(
            {
                "text": example.text.strip(),
                "sentenceId": example.ID,
                "lexicalUnit": example.LU.name,
                "lexicalUnitId": example.LU.ID,
                "sourceType": "FrameNet lexicographic exemplar",
            }
            for example in examples[:limit]
        )

    def match_lexical_unit(self, sentence: str, frame_name: str) -> dict[str, Any] | None:
        """Return LU evidence when an official LU is visibly present in text."""
        summary = self.frame_summary(frame_name)
        if not summary:
            return None
        candidates: list[tuple[int, int, str, str]] = []
        for lexical_unit in summary["lexicalUnits"]:
            lemma, _, part_of_speech = lexical_unit.rpartition(".")
            surface_lemma = re.sub(r"\s*\[[^]]+\]$", "", lemma)
            for form in _surface_forms(surface_lemma, part_of_speech):
                match = re.search(rf"\b{re.escape(form)}\b", sentence, re.IGNORECASE)
                if match:
                    candidates.append((match.start(), -len(match.group(0)), lexical_unit, match.group(0)))
        if not candidates:
            return None
        start, _, lexical_unit, text = sorted(candidates)[0]
        return {"text": text, "start": start, "end": start + len(text), "lexicalUnit": lexical_unit}

    def validate_frame_elements(self, frame_name: str, names: list[str]) -> dict[str, Any]:
        summary = self.frame_summary(frame_name)
        if not summary:
            return {"valid": [], "invalid": names}
        official = summary["frameElements"]
        return {
            "valid": [name for name in names if name in official],
            "invalid": [name for name in names if name not in official],
        }

    @lru_cache(maxsize=128)
    def candidate_frames(self, sentence: str, limit: int = 8) -> tuple[dict[str, Any], ...]:
        """Return possible FrameNet frames from visible lexical-unit matches.

        This is candidate discovery only. The NLTK FrameNet reader provides the
        official frame/LU registry, but it does not disambiguate arbitrary text
        into a confirmed semantic annotation.
        """
        if not self.available:
            return ()
        matches: list[tuple[int, int, str, int, str, str, str]] = []
        try:
            lexical_units = self._fn.lus()
        except Exception:
            return ()
        for lexical_unit in lexical_units:
            name = lexical_unit.name
            lemma, _, part_of_speech = name.rpartition(".")
            surface_lemma = re.sub(r"\s*\[[^]]+\]$", "", lemma)
            if not surface_lemma or part_of_speech not in {"v", "n", "a", "adv", "prep"}:
                continue
            for form in _surface_forms(surface_lemma, part_of_speech):
                match = re.search(rf"\b{re.escape(form)}\b", sentence, re.IGNORECASE)
                if match:
                    if any(char.isupper() for char in surface_lemma) and match.group(0) != form:
                        continue
                    frame = lexical_unit.frame
                    matches.append(
                        (
                            match.start(),
                            -len(match.group(0)),
                            frame.name,
                            frame.ID,
                            name,
                            match.group(0),
                            part_of_speech,
                        )
                    )
                    break
        candidates = []
        seen_frames: set[str] = set()
        for start, neg_length, frame_name, frame_id, lu_name, text, part_of_speech in sorted(matches):
            if frame_name in seen_frames:
                continue
            seen_frames.add(frame_name)
            candidates.append(
                {
                    "frame": frame_name,
                    "frameId": frame_id,
                    "matchedLexicalUnit": lu_name,
                    "matchedText": text,
                    "partOfSpeech": part_of_speech,
                    "matchSpan": {"start": start, "end": start - neg_length},
                    "confidence": "lexical_match_candidate",
                }
            )
            if len(candidates) >= limit:
                break
        return tuple(candidates)


def _plain_definition(value: str) -> str:
    text = re.sub(r"</?[^>]+>", "", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _surface_forms(lemma: str, part_of_speech: str) -> set[str]:
    if " " in lemma:
        return {lemma}
    forms = {lemma}
    if part_of_speech == "v":
        if lemma.endswith("e"):
            forms.update({lemma + "d", lemma + "s", lemma[:-1] + "ing"})
        elif lemma.endswith("y"):
            forms.update({lemma[:-1] + "ied", lemma[:-1] + "ies", lemma + "ing"})
        else:
            forms.update({lemma + "ed", lemma + "s", lemma + "ing", lemma + "es"})
    elif part_of_speech == "n":
        forms.add(lemma + ("es" if lemma.endswith(("s", "x", "z", "ch", "sh")) else "s"))
    return forms


registry = FrameNetRegistry()
