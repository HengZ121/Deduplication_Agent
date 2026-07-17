#!/usr/bin/env python3
"""Hybrid syntactic/domain mapping for administrative penalty statements."""

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

from dependency_parser import dependency_parser
from framenet_registry import FRAMENET_VERSION, registry


SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z])|\n+")
EVENT_PATTERN = re.compile(
    r"\b(?P<trigger>does\s+not\s+impose|cannot\s+be\s+imposed|must\s+be\s+imposed|"
    r"is\s+not\s+imposed|is\s+imposed|imposes?|imposed|terminates?|terminated|"
    r"rescinds?|rescinded|suspends?|suspended|punishes?|punished|"
    r"disciplines?|disciplined|rewards?|rewarded)\b",
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
    return "PenaltyImposition", polarity, modality


def _frame_name(event_type: str) -> str | None:
    return {
        "PenaltyImposition": "Rewards_and_punishments",
        "PenaltyTermination": "Activity_stop",
        "PenaltySuspension": "Activity_pause",
    }.get(event_type)


def _fe_value(text: str | None, implicit: bool = False) -> dict[str, Any]:
    value: dict[str, Any] = {"text": text}
    if implicit:
        value["implicit"] = True
    return value


def _choose_role(
    role_name: str,
    syntax_roles: dict[str, dict[str, Any]],
    rule_text: str | None,
) -> tuple[str | None, dict[str, Any]]:
    """Prefer a parser-derived span and retain the rule as a safe fallback."""
    parsed = syntax_roles.get(role_name)
    if parsed and parsed.get("text"):
        return parsed["text"], {
            "method": "dependency_parse",
            "relation": parsed["relation"],
            "head": parsed["head"],
            "characterSpan": {"start": parsed["start"], "end": parsed["end"]},
        }
    if rule_text:
        return rule_text, {"method": "domain_rule"}
    return None, {"method": "implicit_or_unresolved"}


def _official_frame_mapping(
    event_type: str,
    sentence: str,
    agent_text: str | None,
    evaluee_text: str | None,
    penalty: dict[str, Any] | None,
    condition: dict[str, Any] | None,
    time_text: str | None,
) -> tuple[str | None, dict[str, Any], dict[str, Any]]:
    frame_name = _frame_name(event_type)
    if not frame_name:
        return None, {}, {
            "version": FRAMENET_VERSION,
            "available": registry.available,
            "frameId": None,
            "frameName": None,
            "validationStatus": "domain_event_only",
            "message": "No exact FrameNet 1.7 frame/LU is assigned to this domain lifecycle event.",
        }

    summary = registry.frame_summary(frame_name)
    if not summary:
        return frame_name, {}, {
            "version": FRAMENET_VERSION,
            "available": False,
            "frameId": None,
            "frameName": frame_name,
            "validationStatus": "registry_unavailable",
            "message": registry.error,
        }

    penalty_text = penalty.get("text") if penalty else None
    condition_text = condition.get("text") if condition else None
    if event_type == "PenaltyImposition":
        frame_elements = {
            "Agent": _fe_value(agent_text, not bool(agent_text)),
            "Evaluee": _fe_value(evaluee_text, not bool(evaluee_text)),
            "Response_action": _fe_value(penalty_text, not bool(penalty_text)),
            "Reason": _fe_value(condition_text) if condition_text else None,
            "Time": _fe_value(time_text) if time_text else None,
        }
    else:
        activity_match = re.search(r"\b(?:the\s+)?(?:disentitlement|disqualification|penalty|D\d+)\b", sentence, re.I)
        activity_text = activity_match.group(0) if activity_match else None
        frame_elements = {
            "Agent": _fe_value(agent_text, not bool(agent_text)),
            "Activity": _fe_value(activity_text, not bool(activity_text)),
            "Explanation": _fe_value(condition_text) if condition_text else None,
            "Time": _fe_value(time_text) if time_text else None,
        }
    frame_elements = {name: value for name, value in frame_elements.items() if value is not None}
    validation = registry.validate_frame_elements(frame_name, list(frame_elements))
    lu_match = registry.match_lexical_unit(sentence, frame_name)
    status = "validated_exact_lu" if lu_match else "validated_frame_no_exact_lu"
    return frame_name, frame_elements, {
        "version": FRAMENET_VERSION,
        "available": True,
        "frameId": summary["id"],
        "frameName": summary["name"],
        "target": lu_match,
        "validationStatus": status,
        "frameElementValidation": validation,
    }


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
        event_type, polarity, modality = _event_type(trigger)
        syntax = dependency_parser.analyze(sentence, trigger_match.start(), trigger_match.end())
        syntax_roles = syntax.get("roles", {})
        code_match = CODE_PATTERN.search(sentence)
        penalty = None
        if code_match:
            penalty = {
                "text": code_match.group(0).strip(),
                "code": code_match.group("code").upper(),
                "number": int(code_match.group("number")) if code_match.group("number") else None,
                "label": (code_match.group("label") or "").strip(" -") or None,
                "sanctionType": (code_match.group("kind") or "").lower() or None,
            }
            last_code = penalty
        elif event_type != "PenaltyImposition":
            penalty = last_code

        agent_match = AGENT_PATTERN.search(sentence)
        evaluee_match = EVALUEE_PATTERN.search(sentence)
        condition_match = CONDITION_PATTERN.search(sentence)
        time_match = TIME_PATTERN.search(sentence)
        rule_condition_text = condition_match.group("condition") if condition_match else None
        agent_text, agent_evidence = _choose_role(
            "agent", syntax_roles, agent_match.group(0) if agent_match else None
        )
        evaluee_text, evaluee_evidence = _choose_role(
            "evaluee", syntax_roles, evaluee_match.group(0) if evaluee_match else None
        )
        condition_text, condition_evidence = _choose_role("condition", syntax_roles, rule_condition_text)
        time_text, time_evidence = _choose_role(
            "time", syntax_roles, time_match.group("time") if time_match else None
        )
        condition = _normalize_condition(condition_text) if condition_text else None
        frame_name, frame_elements, framenet = _official_frame_mapping(
            event_type,
            sentence,
            agent_text,
            evaluee_text,
            penalty,
            condition,
            time_text,
        )

        events.append(
            {
                "eventType": event_type,
                "frame": frame_name,
                "trigger": trigger,
                "triggerSpan": {"start": trigger_match.start(), "end": trigger_match.end()},
                "frameElements": frame_elements,
                "frameNet": framenet,
                "dependencyAnalysis": syntax,
                "extractionEvidence": {
                    "Agent": agent_evidence,
                    "Evaluee": evaluee_evidence,
                    "Condition": condition_evidence,
                    "Time": time_evidence,
                },
                "ruleCondition": condition,
                "penaltyCode": penalty,
                "polarity": polarity,
                "modality": modality,
                "domainExtensions": {
                    "penaltyCode": penalty,
                    "ruleCondition": condition,
                    "polarity": polarity,
                    "modality": modality,
                },
                "source": asdict(SourceSpan(index, sentence)),
            }
        )

    warnings = [] if events else ["No supported penalty lifecycle trigger was found."]
    if not registry.available:
        warnings.append(f"FrameNet 1.7 registry unavailable: {registry.error}")
    if not dependency_parser.available:
        warnings.append(
            f"Dependency parser unavailable; domain-rule fallback used: {dependency_parser.error}"
        )
    return {
        "schemaVersion": "0.3.1",
        "sourceDocument": source_name,
        "annotationMethod": "spacy-dependency+rule-based-domain+nltk-framenet-1.7-validation",
        "syntacticParser": {
            "provider": "spaCy",
            "model": dependency_parser.MODEL,
            "available": dependency_parser.available,
            "version": dependency_parser.version,
            "fallback": "domain rules",
        },
        "frameNetRegistry": {
            "provider": "NLTK FrameNet API",
            "version": FRAMENET_VERSION,
            "available": registry.available,
        },
        "eventCount": len(events),
        "events": events,
        "warnings": warnings,
    }
