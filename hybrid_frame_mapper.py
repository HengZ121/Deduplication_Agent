#!/usr/bin/env python3
"""Rule + optional transformer ranking for benefit/employment FrameNet frames."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from framenet_registry import FRAMENET_VERSION, registry


AGENT_PATTERN = re.compile(r"\b(?:the\s+)?(?:agent|officer|system|commission|service canada|client|claimant)\b", re.I)
CLIENT_PATTERN = re.compile(r"\b(?:the\s+)?(?:client|claimant|applicant|employee|worker|employer)\b", re.I)
DOCUMENT_PATTERN = re.compile(r"\b(?:document|form|statement|letter|report|record|application|file|notice|roe)\b", re.I)
BENEFIT_PATTERN = re.compile(r"\b(?:benefit|benefits|payment|allowance|entitlement|claim)\b", re.I)
MONEY_PATTERN = re.compile(r"\b(?:earnings|wages|income|payment|paid|repayment|amount|rate|\$\d+)\b", re.I)
CONDITION_PATTERN = re.compile(r"\b(?:if|when|unless|where|provided that)\s+([^.;]+)", re.I)


@dataclass(frozen=True)
class FrameRule:
    frame: str
    event_type: str
    description: str
    pattern: re.Pattern[str]
    trigger: re.Pattern[str]
    element_patterns: dict[str, re.Pattern[str]]


FRAME_RULES: tuple[FrameRule, ...] = (
    FrameRule("Deciding", "DecisionEvent", "decision, adjudication, denial, approval, or determination", re.compile(r"\b(?:decid(?:e|es|ed|ing)|determin(?:e|es|ed|ing)|deny|approve|adjudicat(?:e|es|ed|ion)|decision)\b", re.I), re.compile(r"\b(?:decid(?:e|es|ed|ing)|determin(?:e|es|ed|ing)|deny|approve|adjudicat(?:e|es|ed|ion)|decision)\b", re.I), {"Cognizer": AGENT_PATTERN, "Decision": re.compile(r"\b(?:decision|request|claim|issue|entitlement|eligibility)\b", re.I)}),
    FrameRule("Coming_to_believe", "DiagnosticInference", "infer or determine a reason from evidence", re.compile(r"\b(?:infer|determine|conclude|find|based on|reason|evidence)\b", re.I), re.compile(r"\b(?:infer|determine|conclude|find|based on)\b", re.I), {"Cognizer": AGENT_PATTERN, "Evidence": DOCUMENT_PATTERN, "Content": re.compile(r"\b(?:reason|status|eligibility|insurability|issue)\b[^.;]*", re.I)}),
    FrameRule("Contingency", "ConditionalRule", "if/when/unless condition leading to an outcome", re.compile(r"\b(?:if|when|unless|depends on|where)\b", re.I), re.compile(r"\b(?:if|when|unless|depends on|where)\b", re.I), {"Determinant": CONDITION_PATTERN, "Outcome": re.compile(r"\b(?:then|must|can|may|will|is|are)\b[^.;]*", re.I)}),
    FrameRule("Control", "ControlRequirement", "control or authority over a decision, variable, account, or process", re.compile(r"\b(?:control|authority|authorized|responsible|manage|administer|override)\b", re.I), re.compile(r"\b(?:control|authority|authorized|responsible|manage|administer|override)\b", re.I), {"Controlling_entity": AGENT_PATTERN, "Dependent_entity": re.compile(r"\b(?:claim|file|account|case|system|decision|benefit)\b", re.I)}),
    FrameRule("Claim_ownership", "ClaimOwnership", "claimant/client ownership or right to claim property/benefit", re.compile(r"\b(?:claim|claimant|entitled|entitlement|right to|eligible for)\b", re.I), re.compile(r"\b(?:claim|entitled|entitlement|eligible)\b", re.I), {"Claimant": CLIENT_PATTERN, "Property": BENEFIT_PATTERN}),
    FrameRule("Conferring_benefit", "BenefitConferral", "benefits or advantageous situation conferred on a person", re.compile(r"\b(?:benefit|benefits|paid|payable|entitled|allowance|support)\b", re.I), re.compile(r"\b(?:benefit|benefits|paid|payable|entitled|allowance|support)\b", re.I), {"Beneficiary": CLIENT_PATTERN, "Beneficial_situation": BENEFIT_PATTERN}),
    FrameRule("Information", "InformationEvent", "information, data, facts, or evidence available/recorded", re.compile(r"\b(?:information|data|fact|details|record|file|evidence)\b", re.I), re.compile(r"\b(?:information|data|fact|details|record|file|evidence)\b", re.I), {"Information": re.compile(r"\b(?:information|data|fact|details|record|file|evidence)\b[^.;]*", re.I), "Source": DOCUMENT_PATTERN}),
    FrameRule("Compliance", "ComplianceCheck", "following policy, legislation, requirements, or conditions", re.compile(r"\b(?:comply|complies|compliance|follow|meet|satisfy|according to|in accordance with|condition|requirement)\b", re.I), re.compile(r"\b(?:comply|complies|compliance|follow|meet|satisfy|according to|in accordance with)\b", re.I), {"Protagonist": CLIENT_PATTERN, "Norm": re.compile(r"\b(?:policy|legislation|condition|requirement|criteria|rule)\b[^.;]*", re.I)}),
    FrameRule("Have_as_requirement", "RequirementRule", "required condition/entity for a claim, payment, or process", re.compile(r"\b(?:require|requires|required|requirement|must have|must provide|must meet|condition)\b", re.I), re.compile(r"\b(?:require|requires|required|requirement|must have|must provide|must meet)\b", re.I), {"Dependent": re.compile(r"\b(?:claim|benefit|payment|client|claimant|application)\b", re.I), "Requirement": re.compile(r"\b(?:requires|required|requirement|condition|document|hours|weeks|statement|proof)\b[^.;]*", re.I)}),
    FrameRule("Evidence", "EvidenceSupport", "evidence supports a proposition or decision", re.compile(r"\b(?:evidence|prove|proof|support|supports|supporting|attest|verify|confirm|confirms|indicate|indicates|show|shows)\b", re.I), re.compile(r"\b(?:evidence|prove|proof|support|supports|supporting|attest|verify|confirm|confirms|indicate|indicates|show|shows)\b", re.I), {"Support": DOCUMENT_PATTERN, "Proposition": re.compile(r"\b(?:pregnancy|eligibility|reason|status|claim|issue)\b[^.;]*", re.I)}),
    FrameRule("Documents", "DocumentReference", "forms, records, letters, reports, or other documents", re.compile(r"\b(?:document|form|record|letter|report|notice|statement|application|ROE|file)\b", re.I), re.compile(r"\b(?:document|form|record|letter|report|notice|statement|application|ROE|file)\b", re.I), {"Document": DOCUMENT_PATTERN, "Bearer": CLIENT_PATTERN}),
    FrameRule("Employing", "EmploymentRelationship", "employment relationship involving employer/employee/work", re.compile(r"\b(?:employ|employer|employee|employment|work|worker|job)\b", re.I), re.compile(r"\b(?:employ|employer|employee|employment|work|worker|job)\b", re.I), {"Employee": CLIENT_PATTERN, "Employer": re.compile(r"\b(?:employer|business|company)\b", re.I)}),
    FrameRule("Being_employed", "EmploymentStatus", "state of being employed, insurable employment, or work status", re.compile(r"\b(?:employed|employment|insurable employment|work status|self-employed|unemployed)\b", re.I), re.compile(r"\b(?:employed|employment|self-employed|unemployed)\b", re.I), {"Employee": CLIENT_PATTERN, "Employer": re.compile(r"\b(?:employer|business|company)\b", re.I)}),
    FrameRule("Submitting_documents", "DocumentSubmission", "submitting/providing documents or statements to authority", re.compile(r"\b(?:submit|provide|send|file|upload|complete).{0,50}\b(?:document|form|statement|application|report|record|file)\b", re.I), re.compile(r"\b(?:submit|provide|send|file|upload|complete)\b", re.I), {"Submittor": CLIENT_PATTERN, "Documents": DOCUMENT_PATTERN, "Authority": AGENT_PATTERN}),
    FrameRule("Earnings_and_losses", "EarningsEvent", "earnings, wages, income, losses, or payable amounts", re.compile(r"\b(?:earning|earnings|wage|wages|income|loss|losses|amount|rate|paid|payment)\b", re.I), re.compile(r"\b(?:earning|earnings|wage|wages|income|loss|losses|amount|paid|payment)\b", re.I), {"Earner": CLIENT_PATTERN, "Earnings": MONEY_PATTERN}),
    FrameRule("Imposing_obligation", "ObligationImposition", "must/required duty imposed on client/officer", re.compile(r"\b(?:must|shall|requires? .+ to|required to|obligate|obligates|obligated|obligation|responsible for)\b", re.I), re.compile(r"\b(?:must|shall|requires?|required to|obligate|obligates|obligated|obligation|responsible for)\b", re.I), {"Responsible_party": AGENT_PATTERN, "Duty": re.compile(r"\b(?:must|shall|requires?|required to|obligate|obligates|obligated to)\b[^.;]*", re.I)}),
    FrameRule("Request", "RequestEvent", "client/officer request for reconsideration, information, or action", re.compile(r"\b(?:request|ask|asks|asked|application|apply|appeal)\b", re.I), re.compile(r"\b(?:request|ask|asks|asked|application|apply|appeal)\b", re.I), {"Speaker": CLIENT_PATTERN, "Message": re.compile(r"\b(?:request|application|appeal|information|reconsideration)\b[^.;]*", re.I)}),
    FrameRule("Reporting", "ReportingEvent", "reporting behavior, claimant reports, or reports to authority", re.compile(r"\b(?:report|reports|reported|reporting|declare|declaration)\b", re.I), re.compile(r"\b(?:report|reports|reported|reporting|declare|declaration)\b", re.I), {"Informer": CLIENT_PATTERN, "Authorities": AGENT_PATTERN, "Behavior": re.compile(r"\b(?:earnings|absence|availability|work|claim)\b[^.;]*", re.I)}),
    FrameRule("Resolve_problem", "ProblemResolution", "resolve, fix, correct, replace, or clear an issue", re.compile(r"\b(?:resolve|resolves|resolved|fix|fixes|correct|corrects|correcting|clear|clears|address|addresses|rectify|rectifies|reconsideration)\b", re.I), re.compile(r"\b(?:resolve|resolves|resolved|fix|fixes|correct|corrects|correcting|clear|clears|address|addresses|rectify|rectifies)\b", re.I), {"Agent": AGENT_PATTERN, "Cause": re.compile(r"\b(?:issue|problem|error|discrepancy|request)\b[^.;]*", re.I)}),
    FrameRule("Activity_finish", "ActivityCompletion", "finish/complete/end a procedure, report, or activity", re.compile(r"\b(?:complete|completes|completed|finish|finishes|finished|end|ends|ended|close|closes|closed)\b", re.I), re.compile(r"\b(?:complete|completes|completed|finish|finishes|finished|end|ends|ended|close|closes|closed)\b", re.I), {"Agent": AGENT_PATTERN, "Activity": re.compile(r"\b(?:report|task|activity|process|claim|review|application)\b[^.;]*", re.I)}),
)
FRAME_PRIORITY = {
    "Deciding": 0.08,
    "Coming_to_believe": 0.12,
    "Contingency": 0.08,
    "Control": 0.12,
    "Claim_ownership": 0.08,
    "Conferring_benefit": 0.08,
    "Information": 0.08,
    "Compliance": 0.26,
    "Have_as_requirement": 0.2,
    "Evidence": 0.18,
    "Documents": 0.1,
    "Employing": 0.12,
    "Submitting_documents": 0.24,
    "Being_employed": 0.22,
    "Imposing_obligation": 0.32,
    "Request": 0.22,
    "Reporting": 0.14,
    "Resolve_problem": 0.26,
    "Activity_finish": 0.24,
}


def _matched_text(pattern: re.Pattern[str], sentence: str) -> str | None:
    match = pattern.search(sentence)
    if not match:
        return None
    value = next((group for group in match.groups() if group), match.group(0))
    return value.strip(" ,")


def _rule_score(rule: FrameRule, sentence: str) -> float:
    match = rule.pattern.search(sentence)
    if not match:
        return 0.0
    score = 0.62
    if rule.trigger.search(sentence):
        score += 0.14
    for pattern in rule.element_patterns.values():
        if pattern.search(sentence):
            score += 0.04
    score += FRAME_PRIORITY.get(rule.frame, 0.0)
    return min(score, 0.98)


@lru_cache(maxsize=1)
def _bert_ranker() -> Any | None:
    """Load a local zero-shot classifier if available; never downloads models."""
    if os.environ.get("HYBRID_FRAME_BERT") != "1":
        return None
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    try:
        from transformers import pipeline

        return pipeline("zero-shot-classification", model="facebook/bart-large-mnli", local_files_only=True)
    except Exception:
        return None


def _bert_scores(sentence: str, rules: tuple[FrameRule, ...]) -> tuple[dict[str, float], dict[str, Any]]:
    ranker = _bert_ranker()
    if ranker is None:
        return {}, {
            "available": False,
            "method": "transformers_zero_shot",
            "model": "facebook/bart-large-mnli",
            "status": "unavailable_local_model_or_dependency",
        }
    labels = [rule.description for rule in rules]
    result = ranker(sentence, labels, multi_label=True)
    scores = {
        rule.frame: float(result["scores"][result["labels"].index(rule.description)])
        for rule in rules
        if rule.description in result["labels"]
    }
    return scores, {
        "available": True,
        "method": "transformers_zero_shot",
        "model": "facebook/bart-large-mnli",
        "status": "scored",
    }


def hybrid_frame_mapping(sentence: str, sentence_index: int, use_bert: bool = True) -> dict[str, Any] | None:
    """Return the best configured employment/benefit frame event for a sentence."""
    rule_scores = {rule.frame: _rule_score(rule, sentence) for rule in FRAME_RULES}
    matched_rules = tuple(rule for rule in FRAME_RULES if rule_scores[rule.frame] > 0)
    if not matched_rules:
        return None

    bert_scores, bert_info = _bert_scores(sentence, matched_rules) if use_bert else ({}, {"available": False, "status": "disabled"})
    ranked = []
    for rule in matched_rules:
        rule_score = rule_scores[rule.frame]
        bert_score = bert_scores.get(rule.frame)
        combined = rule_score if bert_score is None else (0.7 * rule_score) + (0.3 * bert_score)
        ranked.append((combined, rule_score, bert_score, rule))
    combined, rule_score, bert_score, rule = sorted(ranked, key=lambda item: item[0], reverse=True)[0]
    trigger = rule.trigger.search(sentence)
    elements = {
        name: {"text": text}
        for name, pattern in rule.element_patterns.items()
        if (text := _matched_text(pattern, sentence))
    }
    summary = registry.frame_summary(rule.frame)
    return {
        "eventType": rule.event_type,
        "frame": rule.frame,
        "trigger": trigger.group(0) if trigger else None,
        "triggerSpan": {"start": trigger.start(), "end": trigger.end()} if trigger else None,
        "frameElements": elements,
        "frameNet": {
            "version": FRAMENET_VERSION,
            "available": bool(summary),
            "frameId": summary["id"] if summary else None,
            "frameName": rule.frame,
            "target": registry.match_lexical_unit(sentence, rule.frame),
            "validationStatus": "hybrid_rule_bert_frame",
            "frameElementValidation": registry.validate_frame_elements(rule.frame, list(elements)),
        },
        "mappingStatus": "hybrid_rule_bert",
        "ruleCondition": None,
        "penaltyCode": None,
        "polarity": "negative" if re.search(r"\b(?:not|cannot|never|no)\b", sentence, re.I) else "positive",
        "modality": "required" if re.search(r"\b(?:must|shall|required)\b", sentence, re.I) else "asserted",
        "hybridScoring": {
            "ruleScore": round(rule_score, 4),
            "bertScore": round(bert_score, 4) if bert_score is not None else None,
            "combinedScore": round(combined, 4),
            "bert": bert_info,
            "candidateFrames": [
                {
                    "frame": item_rule.frame,
                    "eventType": item_rule.event_type,
                    "ruleScore": round(item_rule_score, 4),
                    "bertScore": round(item_bert_score, 4) if item_bert_score is not None else None,
                    "combinedScore": round(item_combined, 4),
                }
                for item_combined, item_rule_score, item_bert_score, item_rule in sorted(
                    ranked, key=lambda item: item[0], reverse=True
                )[:5]
            ],
        },
        "domainExtensions": {"hybridFrameSet": "employment_social_benefits_20"},
        "source": {"sentence_index": sentence_index, "sentence": sentence},
    }


def demo_sentences() -> str:
    return "\n".join(
        [
            "The officer decides the outcome after reviewing the facts.",
            "The officer concludes the separation reason from the facts.",
            "If the claimant has insufficient hours, the claim is held for review.",
            "The officer has authority to control the claim correction.",
            "The claimant owns the claim under the account.",
            "The allowance benefits the client during leave.",
            "The agent records information about the case notes.",
            "The office complies with the policy conditions.",
            "The application requires proof of identity from the claimant.",
            "The medical letter confirms the pregnancy status.",
            "The notice document lists the decision date.",
            "The company employs the worker under contract.",
            "The worker was employed during the calendar quarter.",
            "The client submits the application form to Service Canada.",
            "The claimant's weekly earnings are calculated for the week.",
            "The policy obligates the person to attend the interview.",
            "The claimant asks for reconsideration of the decision.",
            "The claimant reports availability for the week.",
            "The agent resolves the issue by correcting the file.",
            "The agent finishes the review before the deadline.",
        ]
    )
