#!/usr/bin/env python3
"""Rule + optional transformer ranking for benefit/employment FrameNet frames."""

from __future__ import annotations

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
    FrameRule("Submitting_documents", "DocumentSubmission", "submitting/providing documents or statements to authority", re.compile(r"\b(?:submit|submits|submitted|provide|provides|provided|send|sends|sent|file|files|filed|upload|uploads|uploaded|complete|completes|completed).{0,50}\b(?:document|form|statement|application|report|record|file)\b", re.I), re.compile(r"\b(?:submit|submits|submitted|provide|provides|provided|send|sends|sent|file|files|filed|upload|uploads|uploaded|complete|completes|completed)\b", re.I), {"Submittor": CLIENT_PATTERN, "Documents": DOCUMENT_PATTERN, "Authority": AGENT_PATTERN}),
    FrameRule("Earnings_and_losses", "EarningsEvent", "earnings, wages, income, losses, or payable amounts", re.compile(r"\b(?:earning|earnings|wage|wages|income|loss|losses|amount|rate|paid|payment)\b", re.I), re.compile(r"\b(?:earning|earnings|wage|wages|income|loss|losses|amount|paid|payment)\b", re.I), {"Earner": CLIENT_PATTERN, "Earnings": MONEY_PATTERN}),
    FrameRule("Imposing_obligation", "ObligationImposition", "must/required duty imposed on client/officer", re.compile(r"\b(?:must|shall|requires? .+ to|required to|obligate|obligates|obligated|obligation|responsible for)\b", re.I), re.compile(r"\b(?:must|shall|requires?|required to|obligate|obligates|obligated|obligation|responsible for)\b", re.I), {"Responsible_party": AGENT_PATTERN, "Duty": re.compile(r"\b(?:must|shall|requires?|required to|obligate|obligates|obligated to)\b[^.;]*", re.I)}),
    FrameRule("Request", "RequestEvent", "client/officer request for reconsideration, information, or action", re.compile(r"\b(?:request|ask|asks|asked|application|apply|appeal)\b", re.I), re.compile(r"\b(?:request|ask|asks|asked|application|apply|appeal)\b", re.I), {"Speaker": CLIENT_PATTERN, "Message": re.compile(r"\b(?:request|application|appeal|information|reconsideration)\b[^.;]*", re.I)}),
    FrameRule("Reporting", "ReportingEvent", "reporting behavior, claimant reports, or reports to authority", re.compile(r"\b(?:report|reports|reported|reporting|declare|declaration)\b", re.I), re.compile(r"\b(?:report|reports|reported|reporting|declare|declaration)\b", re.I), {"Informer": CLIENT_PATTERN, "Authorities": AGENT_PATTERN, "Behavior": re.compile(r"\b(?:earnings|absence|availability|work|claim)\b[^.;]*", re.I)}),
    FrameRule("Resolve_problem", "ProblemResolution", "resolve, fix, correct, replace, or clear an issue", re.compile(r"\b(?:resolve|resolves|resolved|fix|fixes|correct|corrects|correcting|clear|clears|address|addresses|rectify|rectifies|reconsideration)\b", re.I), re.compile(r"\b(?:resolve|resolves|resolved|fix|fixes|correct|corrects|correcting|clear|clears|address|addresses|rectify|rectifies)\b", re.I), {"Agent": AGENT_PATTERN, "Cause": re.compile(r"\b(?:issue|problem|error|discrepancy|request)\b[^.;]*", re.I)}),
    FrameRule("Activity_finish", "ActivityCompletion", "finish/complete/end a procedure, report, or activity", re.compile(r"\b(?:complete|completes|completed|finish|finishes|finished|end|ends|ended|close|closes|closed)\b", re.I), re.compile(r"\b(?:complete|completes|completed|finish|finishes|finished|end|ends|ended|close|closes|closed)\b", re.I), {"Agent": AGENT_PATTERN, "Activity": re.compile(r"\b(?:report|task|activity|process|claim|review|application)\b[^.;]*", re.I)}),
    FrameRule("Rewards_and_punishments", "SanctionOrBenefitResponse", "penalty, disentitlement, fine, warning, benefit, reward, or sanction response", re.compile(r"\b(?:penalty|penalties|punish|punished|fine|fined|sanction|disentitlement|disqualification|violation|warning|reward|benefit)\b", re.I), re.compile(r"\b(?:penalty|penalties|punish|punished|fine|fined|sanction|disentitlement|disqualification|violation|warning|reward|benefit)\b", re.I), {"Agent": AGENT_PATTERN, "Evaluee": CLIENT_PATTERN, "Response_action": re.compile(r"\b(?:penalty|disentitlement|disqualification|warning|violation|fine|benefit)\b[^.;]*", re.I), "Reason": CONDITION_PATTERN}),
    FrameRule("Scrutiny", "ReviewOrInvestigation", "review, examine, verify, investigate, or scrutinize a claim/file", re.compile(r"\b(?:review|reviews|reviewing|examine|examines|examining|verify|verifies|verifying|investigate|investigates|investigation|scrutiny|check|checks|checking)\b", re.I), re.compile(r"\b(?:review|reviews|reviewing|examine|examines|examining|verify|verifies|verifying|investigate|investigates|investigation|scrutiny|check|checks|checking)\b", re.I), {"Cognizer": AGENT_PATTERN, "Ground": re.compile(r"\b(?:claim|file|record|document|information|issue|case)\b[^.;]*", re.I)}),
    FrameRule("Assessing", "AssessmentEvent", "assess, calculate, recalculate, evaluate, or measure entitlement/benefit amount", re.compile(r"\b(?:assess|assesses|assessed|assessment|calculate|calculates|calculated|calculation|recalculate|recalculation|evaluate|evaluates|evaluation|measure|measures)\b", re.I), re.compile(r"\b(?:assess|assesses|assessed|assessment|calculate|calculates|calculated|calculation|recalculate|recalculation|evaluate|evaluates|evaluation|measure|measures)\b", re.I), {"Assessor": AGENT_PATTERN, "Phenomenon": re.compile(r"\b(?:claim|benefit|entitlement|amount|rate|hours|earnings|eligibility)\b[^.;]*", re.I)}),
    FrameRule("Judgment", "JudgmentEvent", "judging something as eligible, valid, acceptable, contentious, or appropriate", re.compile(r"\b(?:eligible|ineligible|valid|invalid|acceptable|unacceptable|contentious|appropriate|reasonable|fraudulent|suitable)\b", re.I), re.compile(r"\b(?:eligible|ineligible|valid|invalid|acceptable|unacceptable|contentious|appropriate|reasonable|fraudulent|suitable)\b", re.I), {"Judge": AGENT_PATTERN, "Evaluee": CLIENT_PATTERN, "Reason": CONDITION_PATTERN}),
    FrameRule("Cause_to_start", "StartProcedureOrClaim", "start, establish, create, open, register, or activate a claim/procedure", re.compile(r"\b(?:start|starts|started|establish|establishes|established|create|creates|created|open|opens|opened|register|registers|registered|activate|activates|activated)\b", re.I), re.compile(r"\b(?:start|starts|started|establish|establishes|established|create|creates|created|open|opens|opened|register|registers|registered|activate|activates|activated)\b", re.I), {"Cause": AGENT_PATTERN, "Effect": re.compile(r"\b(?:claim|benefit period|work item|WI|case|file|application)\b[^.;]*", re.I)}),
    FrameRule("Receiving", "ReceiptEvent", "receive, obtain, or get documents, benefits, payments, information, or requests", re.compile(r"\b(?:receive|receives|received|receiving|obtain|obtains|obtained|get|gets|got|receipt)\b", re.I), re.compile(r"\b(?:receive|receives|received|receiving|obtain|obtains|obtained|get|gets|got|receipt)\b", re.I), {"Recipient": CLIENT_PATTERN, "Theme": re.compile(r"\b(?:benefit|payment|document|letter|notice|information|request|ROE|statement)\b[^.;]*", re.I)}),
    FrameRule("Communication", "CommunicationEvent", "communicate, advise, inform, explain, contact, or send information", re.compile(r"\b(?:communicate|communicates|advise|advises|advised|inform|informs|informed|explain|explains|explained|contact|contacts|contacted|send|sends|sent)\b", re.I), re.compile(r"\b(?:communicate|communicates|advise|advises|advised|inform|informs|informed|explain|explains|explained|contact|contacts|contacted|send|sends|sent)\b", re.I), {"Speaker": AGENT_PATTERN, "Addressee": CLIENT_PATTERN, "Message": re.compile(r"\b(?:information|decision|notice|letter|rights|requirement|reason)\b[^.;]*", re.I)}),
    FrameRule("Change_position_on_a_scale", "AmountOrDurationChange", "increase, decrease, reduce, extend, shorten, or adjust an amount/duration", re.compile(r"\b(?:increase|increases|increased|decrease|decreases|decreased|reduce|reduces|reduced|extend|extends|extended|shorten|shortens|adjust|adjusts|adjusted|maximum|minimum)\b", re.I), re.compile(r"\b(?:increase|increases|increased|decrease|decreases|decreased|reduce|reduces|reduced|extend|extends|extended|shorten|shortens|adjust|adjusts|adjusted|maximum|minimum)\b", re.I), {"Item": re.compile(r"\b(?:benefit|payment|period|week|amount|rate|hours|earnings|claim)\b[^.;]*", re.I)}),
    FrameRule("Giving", "IssuanceOrPayment", "issue, grant, pay, provide, or give a benefit/payment/document", re.compile(r"\b(?:issue|issues|issued|grant|grants|granted|pay|pays|paid|provide|provides|provided|give|gives|given)\b", re.I), re.compile(r"\b(?:issue|issues|issued|grant|grants|granted|pay|pays|paid|provide|provides|provided|give|gives|given)\b", re.I), {"Donor": AGENT_PATTERN, "Recipient": CLIENT_PATTERN, "Theme": re.compile(r"\b(?:benefit|payment|notice|letter|document|code|information)\b[^.;]*", re.I)}),
    FrameRule("Activity_stop", "StopProcedureOrEntitlement", "stop, terminate, suspend, cancel, cease, or end a claim/activity/benefit", re.compile(r"\b(?:stop|stops|stopped|terminate|terminates|terminated|suspend|suspends|suspended|cancel|cancels|cancelled|cease|ceases|ceased|end|ends|ended)\b", re.I), re.compile(r"\b(?:stop|stops|stopped|terminate|terminates|terminated|suspend|suspends|suspended|cancel|cancels|cancelled|cease|ceases|ceased|end|ends|ended)\b", re.I), {"Agent": AGENT_PATTERN, "Activity": re.compile(r"\b(?:claim|benefit|payment|report|activity|process|entitlement|disentitlement)\b[^.;]*", re.I), "Time": re.compile(r"\b(?:on|until|before|after|effective)\b[^.;]*", re.I)}),
)
FRAME_PRIORITY = {
    "Deciding": 0.08,
    "Coming_to_believe": 0.12,
    "Contingency": 0.22,
    "Control": 0.12,
    "Claim_ownership": 0.08,
    "Conferring_benefit": 0.08,
    "Information": 0.08,
    "Compliance": 0.26,
    "Have_as_requirement": 0.2,
    "Evidence": 0.18,
    "Documents": 0.1,
    "Employing": 0.12,
    "Submitting_documents": 0.38,
    "Being_employed": 0.22,
    "Imposing_obligation": 0.32,
    "Request": 0.22,
    "Reporting": 0.14,
    "Resolve_problem": 0.26,
    "Activity_finish": 0.24,
    "Rewards_and_punishments": 0.36,
    "Scrutiny": 0.3,
    "Assessing": 0.32,
    "Judgment": 0.28,
    "Cause_to_start": 0.28,
    "Receiving": 0.2,
    "Communication": 0.2,
    "Change_position_on_a_scale": 0.3,
    "Giving": 0.18,
    "Activity_stop": 0.34,
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
    return min(score, 1.0)


def _cosine(left: Any, right: Any) -> float:
    left_norm = sum(float(item) * float(item) for item in left) ** 0.5
    right_norm = sum(float(item) * float(item) for item in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return sum(float(a) * float(b) for a, b in zip(left, right)) / (left_norm * right_norm)


@lru_cache(maxsize=1)
def _local_cross_encoder() -> tuple[Any, Any, Any] | None:
    """Load a cached local BERT cross-encoder; never downloads models."""
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
        tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(model_name, local_files_only=True)
        model.eval()
        return tokenizer, model, torch
    except Exception:
        return None


def _bert_scores(sentence: str, rules: tuple[FrameRule, ...]) -> tuple[dict[str, float], dict[str, Any]]:
    cross_encoder = _local_cross_encoder()
    if cross_encoder is None:
        return {}, {
            "available": False,
            "method": "bert_cross_encoder",
            "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
            "status": "unavailable_local_model_or_dependency",
        }
    tokenizer, model, torch = cross_encoder
    pairs = [(sentence, rule.description) for rule in rules]
    encoded = tokenizer(pairs, padding=True, truncation=True, return_tensors="pt")
    with torch.no_grad():
        logits = model(**encoded).logits.reshape(-1)
        values = torch.sigmoid(logits).tolist()
    scores = {rule.frame: float(value) for rule, value in zip(rules, values)}
    return scores, {
        "available": True,
        "method": "bert_cross_encoder",
        "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "status": "scored",
    }


def _ranking_key(item: tuple[float, float, float | None, FrameRule]) -> tuple[float, float, float]:
    """Rank candidate frames without letting tiny BERT noise override exact rule matches."""
    combined, rule_score, _bert_score, rule = item
    return (round(combined, 3), rule_score, FRAME_PRIORITY.get(rule.frame, 0.0))


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
        combined = rule_score if bert_score is None else (0.9 * rule_score) + (0.1 * bert_score)
        ranked.append((combined, rule_score, bert_score, rule))
    combined, rule_score, bert_score, rule = sorted(
        ranked,
        key=_ranking_key,
        reverse=True,
    )[0]
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
                    ranked,
                    key=_ranking_key,
                    reverse=True,
                )[:5]
            ],
        },
        "domainExtensions": {"hybridFrameSet": f"employment_social_benefits_{len(FRAME_RULES)}"},
        "source": {"sentence_index": sentence_index, "sentence": sentence},
    }


def demo_sentences() -> str:
    """Real procedure.zip examples used for the static annotation demo."""
    return "\n".join(
        [
            "Are there any SROCs, records of decision (RODs) or other documents related to the ASMT Best weeks WI?",
            "The arrival or placement week (APW) is determined by the parent’s relationship to the child.",
            "To determine whether a client has proven availability and to facilitate adjudication and fact-finding, the Level 2 officer answers the following questions:",
            "In this situation, the Level 1 officer initiates fact-finding with the client to determine which procedure to choose.",
            "The agent does not accept requests to reissue an access code from a third party, unless it is from the designated representative.",
            "A subsequent claim is deemed to have been filed in a timely manner when:",
            "The Cheque Redemption Control Directorate’s Imaging site is the database used to store and view imaged documents.",
            "Is there any referred training information from the client, the province or territory, or another designated authority?",
            "They cannot just choose to have someone else take care of their claim.",
            "Once a claim is finalized, the system links Parental Client Records for all clients who are sharing parental benefits for the same child.",
            "Once determined, the dual payment amount is recouped from the client’s weekly net payable EI benefits and reimbursed to the social services agency.",
            "For active claims, AOB information is accessible through the Assignment of Benefits link on the Summary tab in FTS.",
            "For additional information, refer to Appointment of representative — Limited physical or mental capacity .",
            "For more details on shareholders of a corporation, refer to Insurability Policy — Shareholders who are Employees of the Corporation .",
            "The tax credit code represents the client’s personal tax situation according to the following list:",
            "EI benefits arising from employment that are tax exempt according to CRA are also exempt from taxation.",
            "In the case of a representative, ensure that there is no electronic document indicating that the client has recovered and no longer requires the services of the representative.",
            "In these cases, the INS3280 form is not required, and a copy of the court order is sufficient.",
            "A situation that leads officers to question clients’ availability for regular benefits should also lead officers to question clients’ ability to prove that they are otherwise available for sickness benefits.",
            "The client is providing care or support to the patient identified on the medical certificate.",
            "This BRAC recoupment transaction is identified as document type RW - Recoupments/Withhold with 9552 in the Entry office .",
            "The COR WI displays the name of the rejected letter and identifies what caused the rejection.",
            "The officer refers to the CRA all other enquiries about insurability, whether from an employee, an employer or their representative.",
            "To decide between the two, the CRA looks at the relationship between the worker and the payer.",
            "The Canada Revenue Agency (CRA) previously ruled that similar employment with the same employer was not insurable.",
            "The client reports being hired as a contractor or a sub-contractor, but the client believes he or she was an employee in insurable employment.",
            "Clients who want another person to represent them on their claim must complete the Representative: INS3280 Appointment — Form .",
            "If a client no longer needs to be represented, the representative and client must submit notification in writing to have the representative removed and allow the client to manage the claim.",
            "Generally, a dual payment amount that has been reimbursed to social services cannot be retroactively modified.",
            "The system generates an MPS payment transaction (T072) using a 3-digit code as a week code.",
            "For more information, the agent refers to Determining if an issue must be referred to Integrity for more information.",
            "A detailed security check must be conducted with the client before providing information or issuing an access code.",
            "Legislation allows requesters to present a request for reconsideration of one or more Commission’s decisions.",
            "What personal information did the client indicate in the Personal Information section of the application?",
            "If clients do not complete their claimant’s reports on time, the claimant’s reports are considered late and are screened out.",
            "The SM30 program then produces quality control reports from the information compiled.",
            "The reconsideration process is not for resolving complaints or misunderstandings.",
            "For more information, the processing officer refers to Reconsideration: CCB claims — Instructions .",
            "When clients lose or forget their access code, they are unable to access TIS or complete electronic claimant’s reports.",
            "When a ruling is required, the Level 1 officer completes the ruling request and sends it along with supporting documentation to the general delivery email box in the officer’s region.",
            "If fraudulent activity is suspected on an EI or EI Emergency Response Benefit (EI ERB) claim, the agent does not issue the access code.",
            "Any WIs related to an EI Emergency Response Benefit (EI ERB) claim are processed by a specialized team.",
            "After completing the detailed security check, the agent issues the original access code and sends it by mail.",
            "When a regular ROE is received with a reason for separation (RFS) K - Other or G - Mandatory retirement , or a fishing ROE is received with a RFS B - Other , an Adjudication Issue (ADJ) RFS Review WI is created.",
            "When an insurability ruling is received, the Level 1 officer calculates the claim in accordance with the CRA’s decision, referring to Processing a completed insurability ruling .",
            "When the insurability of an employment is in doubt or when an Assessment Issue (ASMT) Insurability WI is created, the officer determines if an insurability ruling is required.",
            "March 24, 2021 — This procedure has been updated to include fraudulent EI claims ( more information ).",
            "Jurisprudence has held that good cause is simply doing what a reasonable person would do to satisfy themselves as to their rights and obligations under the EIA.",
            "The system cannot create a link between the ROE and the matching period of employment reported on the initial EI application.",
            "Pilot project no. 24 applies to separation monies paid due to a separation from employment on claims with a BPC or an allocation start date between March 30, 2025 and October 10, 2026.",
            "The client was receiving, or waiting to receive, payment from an employer or from another insurer or payer, including incapacity payments and severance or termination payments.",
            "Once the payment is received by PSCD, the transaction is applied to the client’s overpayment account.",
            "The Non-complex officer encrypts the email and attachments and sends them to the CRA rulings office.",
            "Once the transaction is approved from the BR05 screen, the system generates an OP transaction and sends it to PSCD.",
            "The dual payment amount is recouped at 100% of the weekly net payable EI benefits , unless there is a minimum living allowance in effect.",
            "Is the client’s willingness to work subject to restrictions (expectations which greatly reduce chances of obtaining employment)?",
            "To ensure the confidentiality of information relating to a claim for benefits, the system issues an access code.",
            "However, it is possible for a Service Canada agent to replace the original access code or issue a temporary one.",
            "The simplification measure for relaxed requirements ends September 25, 2021.",
            "On the form, the social services worker indicates the start and end weeks of the AOB period as well as the amount the client receives from social services in each week.",
        ]
    )
