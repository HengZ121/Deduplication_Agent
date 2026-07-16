#!/usr/bin/env python3
"""Rule-based FrameNet mapping for administrative penalty statements."""

from __future__ import annotations

import html
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z])|\n+")
EVENT_PATTERN = re.compile(
    r"\b(?P<trigger>does\s+not\s+impose|cannot\s+be\s+imposed|must\s+be\s+imposed|"
    r"is\s+not\s+imposed|is\s+imposed|imposes?|imposed|terminates?|terminated|"
    r"rescinds?|rescinded|suspends?|suspended)\b",
    re.IGNORECASE,
)
CODE_PATTERN = re.compile(
    r"(?:(?P<number>\d{1,3})\s*-\s*(?P<label>[^.;:()]{3,100}?)\s+)?"
    r"(?P<kind>disentitlement|disqualification|penalty)?\s*\(?(?P<code>D\d{1,3})\)?",
    re.IGNORECASE,
)
CONDITION_PATTERN = re.compile(
    r"\b(?:if|when|unless)\s+(?P<condition>.+?)(?=,\s+(?:the\s+)?(?:officer|agent|system|commission)\b|"
    r",\s+it\s+(?:is|can\s+be|must\s+be)\s+(?:terminated|rescinded|suspended)\b|"
    r",?\s+(?:a|an|the)\s+\d|,?\s+(?:the\s+)?(?:officer|agent)\s+(?:imposes?|terminates?|rescinds?|suspends?)\b|[.;]|$)",
    re.IGNORECASE,
)
TIME_PATTERN = re.compile(
    r"\b(?P<time>(?:starting|beginning|from|until|on)\s+(?:the\s+)?(?:date|day|Monday|Friday|week).+?)(?=[.;]|$)",
    re.IGNORECASE,
)
AGENT_PATTERN = re.compile(r"\b(the\s+(?:officer|agent|system|Commission)|Service Canada)\b", re.IGNORECASE)
EVALUEE_PATTERN = re.compile(r"\b(the\s+client|clients|the\s+claimant|claimants)\b", re.IGNORECASE)


@dataclass(frozen=True)
class SourceSpan:
    sentence_index: int
    sentence: str


def clean_text(text: str) -> str:
    """Normalize whitespace while retaining sentence boundaries."""
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_document_text(filename: str, content: bytes) -> str:
    """Extract plain text from a supported uploaded document."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        with zipfile.ZipFile(BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs = []
        for paragraph in root.iter(namespace + "p"):
            parts = [node.text or "" for node in paragraph.iter(namespace + "t")]
            if parts:
                paragraphs.append("".join(parts))
        return clean_text("\n".join(paragraphs))
    if suffix == ".json":
        value = json.loads(content.decode("utf-8-sig"))
        return clean_text(_collect_json_text(value))
    if suffix not in {".txt", ".md", ""}:
        raise ValueError("Supported formats: .txt, .md, .json, and .docx")
    return clean_text(content.decode("utf-8-sig"))


def _collect_json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_collect_json_text(item) for item in value)
    if isinstance(value, dict):
        preferred = [value[key] for key in ("title", "summary", "text", "content") if key in value]
        values = preferred or list(value.values())
        return "\n".join(_collect_json_text(item) for item in values)
    return ""


def _normalize_condition(condition: str) -> dict[str, Any]:
    condition = condition.strip(" ,")
    hours = re.search(r"(?:not\s+accumulated\s+at\s+least|fewer\s+than)\s+(\d+)\s+insurable\s+hours", condition, re.I)
    if hours:
        return {
            "text": condition,
            "expression": {
                "operator": "lessThan",
                "left": "client.accumulatedInsurableHours",
                "right": int(hours.group(1)),
                "unit": "hour",
            },
        }
    between = re.search(r"between\s+w/c\s*(\d+)\s+and\s+w/c\s*(\d+)", condition, re.I)
    if between:
        return {
            "text": condition,
            "expression": {
                "operator": "betweenInclusive",
                "left": "claim.BPCWeek",
                "lower": int(between.group(1)),
                "upper": int(between.group(2)),
            },
        }
    return {"text": condition, "expression": None, "normalizationStatus": "unresolved"}


def _event_type(trigger: str) -> tuple[str, str, str]:
    lowered = trigger.lower()
    polarity = "negative" if "not" in lowered or "cannot" in lowered else "positive"
    modality = "required" if "must" in lowered else "prohibited" if "cannot" in lowered else "asserted"
    if "terminat" in lowered:
        return "PenaltyTermination", polarity, modality
    if "rescind" in lowered:
        return "PenaltyRescission", polarity, modality
    if "suspend" in lowered:
        return "PenaltySuspension", polarity, modality
    return "Rewards_and_punishments", polarity, modality


def map_text(text: str, source_name: str = "pasted-text") -> dict[str, Any]:
    """Map penalty-related sentences to FrameNet-aligned JSON records."""
    normalized = clean_text(text)
    sentences = [item.strip() for item in SENTENCE_PATTERN.split(normalized) if item.strip()]
    events = []
    last_code: dict[str, Any] | None = None

    for index, sentence in enumerate(sentences):
        trigger_matches = list(EVENT_PATTERN.finditer(sentence))
        if not trigger_matches:
            continue
        # Lifecycle rules often mention the operation in a condition and then
        # assert it in the main clause. The final trigger is the asserted event.
        trigger_match = trigger_matches[-1]
        trigger = trigger_match.group("trigger")
        frame, polarity, modality = _event_type(trigger)
        code_match = CODE_PATTERN.search(sentence)
        penalty = None
        if code_match:
            penalty = {
                "code": code_match.group("code").upper(),
                "number": int(code_match.group("number")) if code_match.group("number") else None,
                "label": (code_match.group("label") or "").strip(" -") or None,
                "sanctionType": (code_match.group("kind") or "").lower() or None,
            }
            last_code = penalty
        elif frame != "Rewards_and_punishments":
            penalty = last_code

        agent_match = AGENT_PATTERN.search(sentence)
        evaluee_match = EVALUEE_PATTERN.search(sentence)
        condition_match = CONDITION_PATTERN.search(sentence)
        time_match = TIME_PATTERN.search(sentence)
        condition = _normalize_condition(condition_match.group("condition")) if condition_match else None

        events.append(
            {
                "frame": frame,
                "trigger": trigger,
                "frameElements": {
                    "Agent": {"text": agent_match.group(0)} if agent_match else {"text": None, "implicit": True},
                    "Evaluee": {"text": evaluee_match.group(0)} if evaluee_match else {"text": None, "implicit": True},
                    "Response": penalty,
                    "Reason": {"text": condition["text"]} if condition else None,
                    "Time": {"text": time_match.group("time")} if time_match else None,
                },
                "ruleCondition": condition,
                "penaltyCode": penalty,
                "polarity": polarity,
                "modality": modality,
                "source": asdict(SourceSpan(index, sentence)),
            }
        )

    return {
        "schemaVersion": "0.1.0",
        "sourceDocument": source_name,
        "annotationMethod": "rule-based-demo",
        "eventCount": len(events),
        "events": events,
        "warnings": [] if events else ["No supported penalty lifecycle trigger was found."],
    }
