#!/usr/bin/env python3
"""Rule + local BERT frame scoring + local BERT QA extraction for procedure frames."""

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


ALL_FRAME_RULES: tuple[FrameRule, ...] = (
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

REPRESENTATIVE_FRAME_NAMES = (
    "Rewards_and_punishments",
    "Scrutiny",
    "Being_employed",
    "Have_as_requirement",
    "Evidence",
    "Submitting_documents",
    "Assessing",
    "Request",
    "Receiving",
    "Activity_stop",
)
_FRAME_RULE_BY_NAME = {rule.frame: rule for rule in ALL_FRAME_RULES}
FRAME_RULES: tuple[FrameRule, ...] = tuple(_FRAME_RULE_BY_NAME[name] for name in REPRESENTATIVE_FRAME_NAMES)

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

BERT_MODEL_NAME = "deepset/bert-base-cased-squad2"

FRAME_ELEMENT_QUESTIONS = {
    "Rewards_and_punishments": {
        "Agent": "Who imposes or handles the penalty, warning, benefit, or response?",
        "Evaluee": "Who is affected by the penalty, warning, benefit, or response?",
        "Response_action": "What penalty, warning, benefit, or response action is applied?",
        "Reason": "Why is the penalty, warning, benefit, or response applied?",
        "Time": "When is the penalty, warning, benefit, or response applied?",
        "Place": "Where is the penalty, warning, benefit, or response applied?",
        "Result": "What is the result of the penalty, warning, benefit, or response?",
    },
    "Scrutiny": {
        "Cognizer": "Who reviews, checks, examines, or investigates?",
        "Phenomenon": "What is being reviewed, checked, examined, or investigated?",
        "Ground": "What evidence, record, issue, or information is used for the review?",
        "Purpose": "Why is the review, check, examination, or investigation performed?",
        "Time": "When does the review, check, examination, or investigation occur?",
        "Medium": "What medium or system is used for the review?",
    },
    "Being_employed": {
        "Employee": "Who is employed or has employment status?",
        "Employer": "Who is the employer?",
        "Position": "What position or role does the worker hold?",
        "Task": "What work or task is performed?",
        "Place_of_employment": "Where is the person employed?",
        "Time": "When is the person employed?",
        "Duration": "How long is the person employed?",
        "Compensation": "What compensation, wages, or earnings are involved?",
    },
    "Have_as_requirement": {
        "Dependent": "What claim, benefit, application, or process has a requirement?",
        "Requirement": "What is required?",
        "Required_entity": "What document, information, or condition is required?",
        "Required_individual": "Who is required to act or provide something?",
        "Condition": "Under what condition does the requirement apply?",
        "Explanation": "Why does the requirement apply?",
        "Time": "When must the requirement be satisfied?",
    },
    "Evidence": {
        "Support": "What evidence, proof, document, or support is provided?",
        "Proposition": "What fact, status, eligibility, or claim does the evidence support?",
        "Cognizer": "Who evaluates or relies on the evidence?",
        "Means": "How is the evidence provided or shown?",
        "Result": "What result does the evidence support?",
        "Domain_of_relevance": "What domain or issue is the evidence relevant to?",
    },
    "Submitting_documents": {
        "Submittor": "Who submits, files, uploads, completes, or provides the document?",
        "Authority": "Who receives the submitted document?",
        "Documents": "What document, form, statement, report, record, file, or application is submitted?",
        "Time": "When is the document submitted?",
        "Place": "Where is the document submitted?",
        "Purpose": "Why is the document submitted?",
        "Beneficiary": "Who benefits from the document submission?",
        "Explanation": "What explanation is given for the document submission?",
    },
    "Assessing": {
        "Assessor": "Who assesses, calculates, evaluates, or measures?",
        "Phenomenon": "What claim, benefit, amount, hours, earnings, or eligibility is assessed?",
        "Feature": "What feature or aspect is assessed?",
        "Value": "What value, result, amount, or conclusion is calculated?",
        "Evidence": "What evidence is used in the assessment?",
        "Standard": "What standard, policy, or decision is used for the assessment?",
        "Method": "How is the assessment or calculation performed?",
        "Time": "When does the assessment or calculation occur?",
        "Purpose": "Why is the assessment or calculation performed?",
    },
    "Request": {
        "Speaker": "Who makes the request?",
        "Addressee": "Who receives the request?",
        "Message": "What request, appeal, application, or reconsideration is made?",
        "Topic": "What is the request about?",
        "Medium": "How is the request submitted or communicated?",
        "Beneficiary": "Who benefits from the request?",
        "Time": "When is the request made or received?",
    },
    "Receiving": {
        "Recipient": "Who receives or obtains something?",
        "Donor": "Who gives or sends the received item?",
        "Theme": "What is received or obtained?",
        "Time": "When is it received or obtained?",
        "Place": "Where is it received or obtained?",
        "Means": "How is it received or obtained?",
        "Mode_of_transfer": "What mode of transfer is used?",
    },
    "Activity_stop": {
        "Agent": "Who stops, terminates, suspends, cancels, or ends the activity?",
        "Activity": "What claim, benefit, payment, report, process, or activity stops or ends?",
        "Time": "When does the activity stop or end?",
        "Explanation": "Why does the activity stop or end?",
        "Purpose": "Why is the activity stopped or ended?",
        "Result": "What is the result of stopping or ending the activity?",
        "Duration": "How long did the activity last?",
        "Means": "How is the activity stopped or ended?",
    },
}


def _matched_span(pattern: re.Pattern[str], sentence: str) -> tuple[str, int, int] | None:
    match = pattern.search(sentence)
    if not match:
        return None
    if match.groups():
        for index, group in enumerate(match.groups(), start=1):
            if group:
                start, end = match.span(index)
                return group.strip(" ,"), start, end
    return match.group(0).strip(" ,"), match.start(), match.end()


def _matched_text(pattern: re.Pattern[str], sentence: str) -> str | None:
    span = _matched_span(pattern, sentence)
    return span[0] if span else None


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
def _local_bert_qa() -> tuple[Any, Any, Any] | None:
    """Load the local BERT QA model used for frame scoring and element extraction."""
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    try:
        import torch
        from transformers import AutoModelForQuestionAnswering, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(BERT_MODEL_NAME, local_files_only=True)
        model = AutoModelForQuestionAnswering.from_pretrained(BERT_MODEL_NAME, local_files_only=True)
        model.eval()
        return tokenizer, model, torch
    except Exception:
        return None


def _mean_pool_embeddings(model: Any, tokenizer: Any, torch: Any, texts: list[str]) -> Any:
    encoded = tokenizer(texts, padding=True, truncation=True, max_length=192, return_tensors="pt")
    with torch.no_grad():
        outputs = model.bert(
            input_ids=encoded["input_ids"],
            attention_mask=encoded["attention_mask"],
            token_type_ids=encoded.get("token_type_ids"),
        )
    hidden = outputs.last_hidden_state
    mask = encoded["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
    return (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)


def _short_text(value: str | None, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


@lru_cache(maxsize=32)
def _frame_prompt(frame_name: str) -> tuple[str, dict[str, Any]]:
    rule = _FRAME_RULE_BY_NAME[frame_name]
    summary = registry.frame_summary(frame_name)
    basis = ["domain_rule_description"]
    parts = [f"Frame: {rule.frame}. Domain description: {rule.description}."]
    if summary:
        definition = _short_text(summary.get("definition"), 420)
        if definition:
            parts.append(f"Official FrameNet definition: {definition}")
            basis.append("official_framenet_frame_definition")
        lexical_units = summary.get("lexicalUnits") or []
        if lexical_units:
            parts.append(f"Official lexical units: {', '.join(lexical_units[:12])}.")
            basis.append("official_framenet_lexical_units")
    return " ".join(parts), {
        "comparisonBasis": basis,
        "exemplarsUsed": False,
        "exemplarPolicy": "Raw FrameNet exemplars are not used by default because they are general-domain and can be misleading for employment/social-benefit procedures.",
    }


def _bert_frame_scores(sentence: str, rules: tuple[FrameRule, ...]) -> tuple[dict[str, float], dict[str, Any]]:
    bert = _local_bert_qa()
    if bert is None:
        return {}, {
            "available": False,
            "method": "bert_embedding_frame_scorer",
            "model": BERT_MODEL_NAME,
            "status": "unavailable_local_model_or_dependency",
        }
    tokenizer, model, torch = bert
    prompts = [_frame_prompt(rule.frame)[0] for rule in rules]
    basis = sorted({item for rule in rules for item in _frame_prompt(rule.frame)[1]["comparisonBasis"]})
    texts = [sentence] + prompts
    embeddings = _mean_pool_embeddings(model, tokenizer, torch, texts)
    similarities = torch.nn.functional.cosine_similarity(embeddings[0].unsqueeze(0), embeddings[1:])
    values = ((similarities + 1.0) / 2.0).tolist()
    scores = {rule.frame: float(value) for rule, value in zip(rules, values)}
    return scores, {
        "available": True,
        "method": "bert_embedding_frame_scorer",
        "model": BERT_MODEL_NAME,
        "status": "scored",
        "comparisonBasis": basis,
        "exemplarsUsed": False,
        "exemplarPolicy": "Raw FrameNet exemplars are not used by default because they are general-domain and can be misleading for employment/social-benefit procedures.",
    }


def _frame_element_definition(frame_name: str, element_name: str) -> str | None:
    summary = registry.frame_summary(frame_name)
    if not summary:
        return None
    element = (summary.get("frameElements") or {}).get(element_name)
    if not element:
        return None
    return _short_text(element.get("definition"), 240)


def _qa_prompt(rule: FrameRule, element_name: str, base_question: str) -> str:
    definition = _frame_element_definition(rule.frame, element_name)
    if not definition:
        return base_question
    return (
        f"In the FrameNet frame {rule.frame}, the element {element_name} means: "
        f"{definition} {base_question}"
    )


def _bert_qa_answer(sentence: str, question: str) -> dict[str, Any] | None:
    bert = _local_bert_qa()
    if bert is None:
        return None
    tokenizer, model, torch = bert
    encoded = tokenizer(
        question,
        sentence,
        truncation="only_second",
        max_length=384,
        return_offsets_mapping=True,
        return_tensors="pt",
    )
    offsets = encoded.pop("offset_mapping")[0]
    sequence_ids = encoded.sequence_ids(0)
    with torch.no_grad():
        output = model(**encoded)
    start_logits = output.start_logits[0].clone()
    end_logits = output.end_logits[0].clone()
    for index, sequence_id in enumerate(sequence_ids):
        if sequence_id != 1:
            start_logits[index] = -1e9
            end_logits[index] = -1e9
    start_probs = torch.softmax(start_logits, dim=0)
    end_probs = torch.softmax(end_logits, dim=0)
    best: tuple[float, int, int, str] | None = None
    for start_index in torch.topk(start_probs, min(8, len(start_probs))).indices.tolist():
        for end_index in torch.topk(end_probs, min(8, len(end_probs))).indices.tolist():
            if end_index < start_index or end_index - start_index > 28:
                continue
            start, _ = offsets[start_index].tolist()
            _, end = offsets[end_index].tolist()
            if end <= start:
                continue
            text = sentence[start:end].strip(" ,")
            if len(text) < 2 or len(text) > 180:
                continue
            score = float(start_probs[start_index] * end_probs[end_index])
            if best is None or score > best[0]:
                best = (score, start, end, text)
    if best is None or best[0] < 0.015:
        return None
    score, start, end, text = best
    return {"text": text, "span": {"start": start, "end": end}, "confidence": round(score, 4)}


def _plausible_element_answer(name: str, text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    validators = {
        "Time": r"\b(?:when|week|weeks|day|date|period|before|after|during|until|effective|received|completed|starts?|ends?|january|february|march|april|may|june|july|august|september|october|november|december|\d{4})\b",
        "Place": r"\b(?:in|at|on|from|to|office|centre|center|region|fts|pscd|cra|mail|portal|site)\b",
        "Place_of_employment": r"\b(?:employer|company|business|workplace|office|site|region|province|territory)\b",
        "Documents": r"\b(?:document|form|statement|report|record|application|roe|certificate|letter|notification|file)\b",
        "Support": r"\b(?:evidence|proof|document|form|statement|report|record|certificate|letter|support)\b",
        "Evidence": r"\b(?:evidence|proof|document|form|statement|report|record|certificate|letter|support|ruling|decision)\b",
        "Medium": r"\b(?:email|mail|letter|form|application|portal|system|phone|writing|document|report)\b",
        "Means": r"\b(?:by|through|with|using|email|mail|form|application|system|phone|writing|document|report)\b",
    }
    person_like = {
        "Agent",
        "Cognizer",
        "Assessor",
        "Speaker",
        "Addressee",
        "Recipient",
        "Donor",
        "Submittor",
        "Authority",
        "Employee",
        "Employer",
        "Evaluee",
        "Judge",
        "Required_individual",
        "Beneficiary",
    }
    if name in person_like:
        return bool(
            re.search(
                r"\b(?:client|claimant|agent|officer|employer|employee|worker|system|commission|representative|requester|person|service canada|cra|level\s+\d|social services worker|pscd)\b",
                lowered,
            )
        )
    if name in validators:
        return bool(re.search(validators[name], lowered, re.I))
    return True


def _configured_element_names(rule: FrameRule) -> tuple[str, ...]:
    names = list(FRAME_ELEMENT_QUESTIONS.get(rule.frame, {}))
    for name in rule.element_patterns:
        if name not in names:
            names.append(name)
    return tuple(names)


def _extract_frame_elements(rule: FrameRule, sentence: str) -> tuple[dict[str, Any], dict[str, Any]]:
    elements: dict[str, Any] = {}
    for name in _configured_element_names(rule):
        pattern = rule.element_patterns.get(name)
        if pattern and (span := _matched_span(pattern, sentence)):
            text, start, end = span
            elements[name] = {
                "text": text,
                "span": {"start": start, "end": end},
                "implicit": False,
                "method": "rule",
            }

    qa_info = {
        "available": _local_bert_qa() is not None,
        "method": "bert_qa_span_extraction",
        "model": BERT_MODEL_NAME,
        "status": "scored" if _local_bert_qa() is not None else "unavailable_local_model_or_dependency",
        "questionBasis": [
            "frame_specific_question",
            "official_framenet_frame_element_definition_when_available",
        ],
    }
    if qa_info["available"]:
        for name, base_question in FRAME_ELEMENT_QUESTIONS.get(rule.frame, {}).items():
            if elements.get(name, {}).get("text"):
                continue
            question = _qa_prompt(rule, name, base_question)
            answer = _bert_qa_answer(sentence, question)
            if answer and _plausible_element_answer(name, answer["text"]):
                elements[name] = {
                    "text": answer["text"],
                    "span": answer["span"],
                    "implicit": False,
                    "method": "bert_qa",
                    "confidence": answer["confidence"],
                    "question": question,
                    "baseQuestion": base_question,
                    "frameElementDefinition": _frame_element_definition(rule.frame, name),
                }

    for name in _configured_element_names(rule):
        elements.setdefault(name, {"text": None, "implicit": True, "method": "not_found"})
    return elements, qa_info


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

    bert_scores, bert_info = _bert_frame_scores(sentence, matched_rules) if use_bert else ({}, {"available": False, "status": "disabled"})
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
    elements, element_extraction = _extract_frame_elements(rule, sentence)
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
            "bertFrameScore": round(bert_score, 4) if bert_score is not None else None,
            "combinedScore": round(combined, 4),
            "bertFrameScorer": bert_info,
            "candidateFrames": [
                {
                    "frame": item_rule.frame,
                    "eventType": item_rule.event_type,
                    "ruleScore": round(item_rule_score, 4),
                    "bertFrameScore": round(item_bert_score, 4) if item_bert_score is not None else None,
                    "combinedScore": round(item_combined, 4),
                }
                for item_combined, item_rule_score, item_bert_score, item_rule in sorted(
                    ranked,
                    key=_ranking_key,
                    reverse=True,
                )[:5]
            ],
        },
        "bertElementExtraction": element_extraction,
        "domainExtensions": {"hybridFrameSet": f"employment_social_benefits_{len(FRAME_RULES)}"},
        "source": {"sentence_index": sentence_index, "sentence": sentence},
    }


def demo_sentences() -> str:
    """Real procedure.zip examples used for the 10-frame static annotation demo."""
    return "\n".join(
        [
            "If fraudulent activity is suspected on an EI or EI Emergency Response Benefit (EI ERB) claim, the agent does not issue the access code.",
            "Any WIs related to an EI Emergency Response Benefit (EI ERB) claim are processed by a specialized team.",
            "After completing the detailed security check, the agent issues the original access code and sends it by mail.",
            "When a regular ROE is received with a reason for separation (RFS) K - Other or G - Mandatory retirement , or a fishing ROE is received with a RFS B - Other , an Adjudication Issue (ADJ) RFS Review WI is created.",
            "The Canada Revenue Agency (CRA) previously ruled that similar employment with the same employer was not insurable.",
            "The client reports being hired as a contractor or a sub-contractor, but the client believes he or she was an employee in insurable employment.",
            "In the case of a representative, ensure that there is no electronic document indicating that the client has recovered and no longer requires the services of the representative.",
            "In these cases, the INS3280 form is not required, and a copy of the court order is sufficient.",
            "A situation that leads officers to question clients’ availability for regular benefits should also lead officers to question clients’ ability to prove that they are otherwise available for sickness benefits.",
            "The client is providing care or support to the patient identified on the medical certificate.",
            "Clients who want another person to represent them on their claim must complete the Representative: INS3280 Appointment — Form .",
            "Once the claim is established and it is determined that regular benefits are payable, regular benefits are payable for each week the client submits a claimant’s report and:",
            "When an insurability ruling is received, the Level 1 officer calculates the claim in accordance with the CRA’s decision, referring to Processing a completed insurability ruling .",
            "When the insurability of an employment is in doubt or when an Assessment Issue (ASMT) Insurability WI is created, the officer determines if an insurability ruling is required.",
            "Legislation allows requesters to present a request for reconsideration of one or more Commission’s decisions.",
            "What personal information did the client indicate in the Personal Information section of the application?",
            "The client was receiving, or waiting to receive, payment from an employer or from another insurer or payer, including incapacity payments and severance or termination payments.",
            "Once the payment is received by PSCD, the transaction is applied to the client’s overpayment account.",
            "The simplification measure for relaxed requirements ends September 25, 2021.",
            "On the form, the social services worker indicates the start and end weeks of the AOB period as well as the amount the client receives from social services in each week.",
        ]
    )
