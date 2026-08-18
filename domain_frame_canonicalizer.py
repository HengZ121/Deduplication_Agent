#!/usr/bin/env python3
"""Canonicalize broad FrameNet lexical candidates into a domain frame inventory.

The raw corpus scan is intentionally high recall: a visible lexical-unit form
adds every FrameNet frame that licenses that form.  This module is the precision
layer.  It keeps raw candidates as audit evidence while emitting only frames
that are useful in the employment-benefit procedure domain.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable


FRAME_INVENTORY_VERSION = "procedure-domain-v1"

# This list is deliberately smaller than the complete FrameNet registry and the
# experimental ALL_FRAME_RULES catalog.  A frame enters this inventory only when
# it represents an operational distinction that the procedure corpus may need.
CANONICAL_DOMAIN_FRAMES = frozenset(
    {
        "Activity_finish",
        "Activity_resume",
        "Activity_stop",
        "Assessing",
        "Be_in_agreement_on_action",
        "Being_employed",
        "Cause_change",
        "Cause_to_start",
        "Coming_to_believe",
        "Communication",
        "Deciding",
        "Deny_or_grant_permission",
        "Evidence",
        "Giving",
        "Have_as_requirement",
        "Imposing_obligation",
        "Make_agreement_on_action",
        "Meet_specifications",
        "Receiving",
        "Replacing",
        "Reporting",
        "Request",
        "Resolve_problem",
        "Rewards_and_punishments",
        "Scrutiny",
        "Submitting_documents",
    }
)

MEETING_FALSE_SENSES = {
    "Assemble",
    "Come_together",
    "Make_acquaintance",
    "Meet_with_response",
    "Response",
}
FILE_FALSE_SENSES = {"Grooming", "Placing", "Giving_in"}
CONSISTENCY_FALSE_SENSES = {"Cause_change_of_consistency", "Change_of_consistency"}
RATE_FRAMES = {
    "Assessing",
    "Price_per_unit",
    "Proportion",
    "Rate_quantification",
    "Relational_quantity",
    "Speed_description",
}
CHANGE_FALSE_SENSES = {
    "Change_of_consistency",
    "Change_tool",
    "Exchange",
    "Exchange_currency",
    "Replacing",
}
STOP_FALSE_SENSES = {"Halt", "Killing", "Process_stop"}
WORK_FALSE_SENSES = {"Labor_product", "Unemployment_rate", "Work", "Working_a_post"}
AMALGAMATION_FRAMES = {"Amalgamation", "Cause_to_amalgamate"}
HISTORY_FRAMES = {"History", "Individual_history"}
SERVED_FALSE_SENSES = {"Function", "Serving_in_capacity"}


@dataclass(frozen=True)
class CanonicalizationResult:
    """JSON-safe result for one unique procedure sentence."""

    status: str
    canonical_frames: tuple[str, ...]
    structured_knowledge: tuple[str, ...]
    rules_applied: tuple[str, ...]
    explicitly_suppressed_frames: tuple[str, ...]
    out_of_inventory_frames: tuple[str, ...]
    review_candidates: tuple[str, ...]
    raw_frame_count: int
    canonical_frame_count: int
    confidence: str

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        return {
            "status": value["status"],
            "canonicalFrames": list(value["canonical_frames"]),
            "structuredKnowledge": list(value["structured_knowledge"]),
            "rulesApplied": list(value["rules_applied"]),
            "explicitlySuppressedFrames": list(value["explicitly_suppressed_frames"]),
            "outOfInventoryFrames": list(value["out_of_inventory_frames"]),
            "reviewCandidates": list(value["review_candidates"]),
            "rawFrameCount": value["raw_frame_count"],
            "canonicalFrameCount": value["canonical_frame_count"],
            "confidence": value["confidence"],
            "inventoryVersion": FRAME_INVENTORY_VERSION,
        }


class DomainFrameCanonicalizer:
    """Apply domain word-sense rules and a controlled frame inventory."""

    UI_ARTIFACT = re.compile(
        r"\b(?:search\s+by\s+activity\s+show\s+all|click\s+(?:the|on)|navigation\s+menu)\b|"
        r"\bselect\s+the\s+reason\s+for\s+issuing\b|"
        r"\breason\s+for\s+issuing\s+(?:a\s+)?(?:manual|amended)\b|"
        r"\|\s*procedure/",
        re.I,
    )
    MEET_STANDARD = re.compile(
        r"\bmeet(?:s|ing)?\b.{0,70}\b(?:condition|criteria|criterion|requirement|standard|eligibility|entitlement)\b|"
        r"\b(?:condition|criteria|criterion|requirement|standard)\b.{0,45}\b(?:is|are|be|been|were)?\s*met\b",
        re.I,
    )
    DOCUMENT_ACTION = re.compile(
        r"\b(?:submi(?:t|ts|tted|tting)|provide(?:s|d|ing)?|send(?:s|ing)?|sent|"
        r"upload(?:s|ed|ing)?|file(?:s|d|ing)?|complete(?:s|d|ing)?)\b.{0,90}"
        r"\b(?:document|form|statement|application|report|record|claim|ROE|file)s?\b",
        re.I,
    )
    ADMIN_FILE = re.compile(
        r"\b(?:file|files|filed|filing)\b.{0,80}\b(?:claim|case|record|application|report|task|review|information|issue)\b|"
        r"\b(?:claim|case|record|application|report|task)\b.{0,80}\b(?:file|files|filed|filing)\b",
        re.I,
    )
    ADMIN_SET = re.compile(
        r"\bset(?:s|ting)?\b.{0,70}\b(?:conditions?|dates?|values?|codes?|tasks?|windows?|counters?|fields?|claims?|payments?|weeks?|amounts?)\b|"
        r"\b(?:conditions?|dates?|values?|codes?|tasks?|windows?|counters?|fields?)\b.{0,60}\bset\s+out\b",
        re.I,
    )
    RATE_QUANTITY = re.compile(
        r"\b(?:benefit|tax|repayment|premium|weekly|payment|deduction|unemployment|interest)\s+rates?\b|"
        r"\brates?\b.{0,70}\b(?:per\s+(?:week|day|hour|cent)|percentage|percent|amount|dollar|\$)\b|"
        r"\b(?:percentage|percent|amount|dollar|\$)\b.{0,70}\brates?\b",
        re.I,
    )
    WAITING_PERIOD_SERVED = re.compile(
        r"\b(?:waiting\s+period|\bWP\b).{0,55}\bserv(?:e|es|ed|ing)\b|"
        r"\bserv(?:e|es|ed|ing)\b.{0,55}\b(?:waiting\s+period|\bWP\b)",
        re.I,
    )
    REPORT_HISTORY = re.compile(
        r"\b(?:e-report|report|payment|claim|transaction|work\s+item|medical)\s+history\b|"
        r"\bhistory\s+(?:screen|tab|record|report|page)\b",
        re.I,
    )
    COMBINED_QUANTITY = re.compile(
        r"\b(?:combined?|combination)\b.{0,70}\b(?:total|weeks?|amount|payments?|earnings?|rate|percentage|hours?)\b|"
        r"\b(?:total|weeks?|amount|payments?|earnings?|rate|percentage|hours?)\b.{0,70}\bcombined?\b",
        re.I,
    )
    DETERMINE = re.compile(r"\bdetermin(?:e|es|ed|ing|ation)\b", re.I)
    EVIDENCE_CONTEXT = re.compile(
        r"\b(?:based\s+on|evidence|letter|document|record|prefix|indicator|information|facts?|proof|shows?|indicates?)\b",
        re.I,
    )
    ASSESSMENT_CONTEXT = re.compile(
        r"\b(?:assess|calculate|recalculate|evaluate|measure|estimate)(?:s|d|ed|ing|ment|tion)?\b|"
        r"\b(?:amount|rate|earnings|hours|weeks|income)\b",
        re.I,
    )
    DECISION_CONTEXT = re.compile(
        r"\b(?:decid|adjudicat|approv|den|decision|whether|eligibility|entitlement|request|claim|issue)\w*\b",
        re.I,
    )
    IMPOSED_DUTY = re.compile(
        r"\b(?:officer|agent|client|claimant|system|commission)\b.{0,55}\b(?:must|shall|required\s+to|responsible\s+for)\b|"
        r"\b(?:must|shall|required\s+to)\b",
        re.I,
    )
    OBJECTIVE_REQUIREMENT = re.compile(
        r"\b(?:requires?|required|requirement|must\s+have|must\s+provide|condition|prerequisite)\b.{0,90}"
        r"\b(?:documents?|proof|statements?|forms?|hours?|weeks?|conditions?|eligibility|entitlement|claims?|benefits?|payments?|applications?)\b",
        re.I,
    )
    CAUSED_CHANGE = re.compile(
        r"\b(?:officer|agent|system|commission|service\s+canada)\b.{0,65}"
        r"\b(?:change|changes|changed|update|updates|updated|modify|modifies|modified|set|sets|replace|replaces|replaced)\b",
        re.I,
    )
    STOP_ACTIVITY = re.compile(
        r"\b(?:stop|stops|stopped|terminate|terminates|terminated|suspend|suspends|suspended|"
        r"cancel|cancels|cancelled|cease|ceases|ceased|close|closes|closed)\b.{0,85}"
        r"\b(?:claim|benefit|payment|report|activity|process|entitlement|disentitlement|task|application)\b|"
        r"\b(?:claim|benefit|payment|report|activity|process|entitlement|disentitlement|task|application)\b.{0,85}"
        r"\b(?:stop|stops|stopped|terminate|terminated|suspend|suspended|cancel|cancelled|cease|closed)\b",
        re.I,
    )
    # A bare occurrence of "employment" is deliberately excluded: the corpus
    # frequently uses it inside the program name "Employment Insurance", which
    # does not assert that anyone is employed.  The contextual alternatives
    # below require either an employment role/status or a change in that status.
    EMPLOYMENT_STATUS = re.compile(
        r"\b(?:employed|unemployed|self[- ]employed|insurable\s+employment|"
        r"employment\s+(?:status|relationship)|employer[- ]employee\s+relationship)\b|"
        r"\b(?:accept|accepts|accepted|start|starts|started|begin|begins|began|leave|leaves|left|"
        r"lose|loses|lost|end|ends|ended|cease|ceases|ceased|terminate|terminates|terminated)\b"
        r".{0,45}\bemployment\b|"
        r"\bemployment\b.{0,45}\b(?:begin|begins|began|start|starts|started|end|ends|ended|"
        r"cease|ceases|ceased|terminate|terminates|terminated|insurable)\b",
        re.I,
    )
    # "Apply for" is only a Request sense when there is an applicant or a
    # request-like domain object.  This avoids treating statements such as
    # "extensions apply for the first four weeks" as applications.
    REQUEST_ACTION = re.compile(
        r"\b(?:request|requests|requested|requesting|ask|asks|asked|asking|appeal|appeals|"
        r"appealed|appealing|application|applications)\b|"
        r"\b(?:client|claimant|person|individual|worker|employee|employer|applicant|they|he|she|you)\b"
        r".{0,45}\bappl(?:y|ies|ied|ying)\s+for\b|"
        r"\bappl(?:y|ies|ied|ying)\s+for\s+(?:benefits?|(?:a|the)\s+(?:new\s+)?claim|"
        r"reconsideration|permission|approval|parental|sickness|maternity|conversion)\b",
        re.I,
    )
    ESTIMATE = re.compile(r"\b(?:estimate|estimates|estimated|estimating|estimation)\b", re.I)
    RESUME = re.compile(r"\b(?:resume|resumes|resumed|resuming|restart|restarts|restarted|restarting)\b", re.I)
    MAKE_AGREEMENT = re.compile(
        r"\b(?:enter(?:s|ed|ing)?\s+into|make|makes|made|reach|reaches|reached|negotiate|negotiates|negotiated)"
        r"\b.{0,45}\bagreement\b",
        re.I,
    )
    HAVE_AGREEMENT = re.compile(
        r"\b(?:existing|valid|under|pursuant\s+to|part\s+of|have|has|had)\b.{0,45}\bagreement\b|"
        r"\bagreement\b",
        re.I,
    )

    FALLBACK_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("Scrutiny", re.compile(r"\b(?:review|examine|verify|investigate|check)\w*\b.{0,80}\b(?:claim|file|record|document|information|issue|case)\b", re.I)),
        ("Request", REQUEST_ACTION),
        ("Receiving", re.compile(r"\b(?:receive|obtain|get|receipt)\w*\b.{0,65}\b(?:benefit|payment|document|letter|notice|information|request|ROE|statement)\b", re.I)),
        ("Evidence", re.compile(r"\b(?:evidence|proof|attest|verify|confirm|indicate|show)\w*\b", re.I)),
        ("Rewards_and_punishments", re.compile(r"\b(?:penalty|disentitlement|disqualification|sanction|fine|warning|punish|reward)\w*\b", re.I)),
        ("Communication", re.compile(r"\b(?:communicate|communicates|communicated|communicating|advise|advises|advised|advising|inform|informs|informed|informing|explain|explains|explained|explaining|contact|contacts|contacted|contacting)\b", re.I)),
        ("Reporting", re.compile(r"\b(?:report|declare|declaration)\w*\b.{0,70}\b(?:earnings|absence|availability|work|claim|income)\b", re.I)),
        ("Activity_finish", re.compile(r"\b(?:finish|complete|end|close)\w*\b.{0,70}\b(?:report|task|activity|process|claim|review|application)\b", re.I)),
        ("Cause_to_start", re.compile(r"\b(?:start|establish|create|open|register|activate)\w*\b.{0,70}\b(?:claim|benefit\s+period|work\s+item|case|file|application|task)\b", re.I)),
        ("Giving", re.compile(r"\b(?:issue|grant|pay|provide|give)\w*\b.{0,70}\b(?:benefit|payment|notice|letter|document|code|information)\b", re.I)),
        ("Deny_or_grant_permission", re.compile(r"\b(?:allowed|authorized|permission|may)\b.{0,70}\b(?:officer|agent|client|claimant|commission|service\s+canada)\b|\b(?:officer|agent|commission)\b.{0,70}\b(?:allowed|authorized|may)\b", re.I)),
        ("Resolve_problem", re.compile(r"\b(?:resolve|fix|correct|clear|address|rectify)\w*\b.{0,70}\b(?:issue|problem|error|discrepancy|request)\b", re.I)),
    )

    def canonicalize(self, sentence: str, raw_frames: Iterable[str]) -> CanonicalizationResult:
        raw = {frame for frame in raw_frames if frame}
        canonical: set[str] = set()
        structured: set[str] = set()
        applied: list[str] = []
        explicit_suppressed: set[str] = set()
        used_fallback = False

        def add_rule(
            name: str,
            *,
            frames: Iterable[str] = (),
            suppress: Iterable[str] = (),
            knowledge: Iterable[str] = (),
        ) -> None:
            applied.append(name)
            canonical.update(frame for frame in frames if frame in CANONICAL_DOMAIN_FRAMES)
            explicit_suppressed.update(raw & set(suppress))
            structured.update(knowledge)

        if self.UI_ARTIFACT.search(sentence):
            return CanonicalizationResult(
                status="filtered_artifact",
                canonical_frames=(),
                structured_knowledge=(),
                rules_applied=("filter_ui_artifact",),
                explicitly_suppressed_frames=tuple(sorted(raw)),
                out_of_inventory_frames=tuple(sorted(raw - CANONICAL_DOMAIN_FRAMES)),
                review_candidates=(),
                raw_frame_count=len(raw),
                canonical_frame_count=0,
                confidence="high",
            )

        if self.RATE_QUANTITY.search(sentence):
            add_rule(
                "rate_is_structured_quantity",
                suppress=RATE_FRAMES,
                knowledge=("rate_or_ratio",),
            )
        if self.WAITING_PERIOD_SERVED.search(sentence):
            add_rule(
                "waiting_period_served_is_domain_state",
                suppress=SERVED_FALSE_SENSES,
                knowledge=("waiting_period_state",),
            )
        if self.REPORT_HISTORY.search(sentence):
            add_rule(
                "history_label_is_record_reference",
                suppress=HISTORY_FRAMES,
                knowledge=("record_history_reference",),
            )
        if self.COMBINED_QUANTITY.search(sentence):
            add_rule(
                "combined_total_is_structured_quantity",
                suppress=AMALGAMATION_FRAMES,
                knowledge=("aggregate_quantity",),
            )

        if self.MEET_STANDARD.search(sentence):
            add_rule(
                "meet_standard_not_social_meeting",
                frames=("Meet_specifications",),
                suppress=MEETING_FALSE_SENSES,
            )
        if self.DOCUMENT_ACTION.search(sentence):
            add_rule(
                "administrative_document_submission",
                frames=("Submitting_documents",),
                suppress=FILE_FALSE_SENSES,
            )
        elif self.ADMIN_FILE.search(sentence):
            add_rule(
                "administrative_file_not_grooming_or_placement",
                suppress=FILE_FALSE_SENSES,
                knowledge=("administrative_file_reference",),
            )
        if self.ADMIN_SET.search(sentence):
            add_rule(
                "administrative_set_not_consistency_change",
                suppress=CONSISTENCY_FALSE_SENSES,
                knowledge=("administrative_setting",),
            )

        if self.DETERMINE.search(sentence):
            if self.EVIDENCE_CONTEXT.search(sentence):
                add_rule(
                    "determine_from_evidence",
                    frames=("Coming_to_believe",),
                    suppress=("Control", "Contingency", "Deciding"),
                )
            elif self.ASSESSMENT_CONTEXT.search(sentence):
                add_rule(
                    "determine_numeric_or_eligibility_assessment",
                    frames=("Assessing",),
                    suppress=("Control", "Contingency", "Coming_to_believe"),
                )
            elif self.DECISION_CONTEXT.search(sentence):
                add_rule(
                    "determine_administrative_decision",
                    frames=("Deciding",),
                    suppress=("Control", "Contingency", "Coming_to_believe"),
                )

        if self.IMPOSED_DUTY.search(sentence):
            add_rule("explicit_procedural_duty", frames=("Imposing_obligation",))
        if self.OBJECTIVE_REQUIREMENT.search(sentence):
            add_rule(
                "objective_prerequisite",
                frames=("Have_as_requirement",),
                suppress=("Needing",),
            )
        if self.CAUSED_CHANGE.search(sentence) and not self.ADMIN_SET.search(sentence):
            add_rule(
                "agent_causes_administrative_change",
                frames=("Cause_change",),
                suppress=CHANGE_FALSE_SENSES,
            )
        if self.STOP_ACTIVITY.search(sentence):
            add_rule(
                "stop_procedure_or_entitlement",
                frames=("Activity_stop",),
                suppress=STOP_FALSE_SENSES,
            )
        if self.EMPLOYMENT_STATUS.search(sentence) and not self.RATE_QUANTITY.search(sentence):
            add_rule(
                "employment_status",
                frames=("Being_employed",),
                suppress=WORK_FALSE_SENSES,
            )
        if self.ESTIMATE.search(sentence):
            add_rule(
                "estimate_is_domain_assessment",
                frames=("Assessing",),
                suppress=("Estimating", "Estimated_value"),
            )
        if self.RESUME.search(sentence):
            add_rule(
                "resume_activity_or_process",
                frames=("Activity_resume",),
                suppress=("Process_resume",),
            )
        if self.MAKE_AGREEMENT.search(sentence):
            add_rule(
                "agreement_formation",
                frames=("Make_agreement_on_action",),
                suppress=("Be_in_agreement_on_action",),
            )
        elif self.HAVE_AGREEMENT.search(sentence):
            add_rule(
                "existing_agreement_state",
                frames=("Be_in_agreement_on_action",),
                suppress=("Make_agreement_on_action",),
            )

        # These fallback rules are intentionally high precision.  They can add
        # several frames when a sentence genuinely expresses several events;
        # the goal is a controlled inventory, not an artificial one-frame cap.
        for frame, pattern in self.FALLBACK_RULES:
            if frame not in canonical and pattern.search(sentence):
                canonical.add(frame)
                applied.append(f"fallback_{frame}")
                used_fallback = True

        out_of_inventory = raw - CANONICAL_DOMAIN_FRAMES
        review_candidates = (raw & CANONICAL_DOMAIN_FRAMES) - canonical - explicit_suppressed
        if canonical:
            status = "canonical_frame"
            confidence = "medium" if used_fallback and not any(not rule.startswith("fallback_") for rule in applied) else "high"
        elif structured:
            status = "structured_non_frame"
            confidence = "high"
        elif review_candidates:
            status = "needs_review"
            confidence = "low"
        else:
            status = "no_domain_frame"
            confidence = "low"

        return CanonicalizationResult(
            status=status,
            canonical_frames=tuple(sorted(canonical)),
            structured_knowledge=tuple(sorted(structured)),
            rules_applied=tuple(applied),
            explicitly_suppressed_frames=tuple(sorted(explicit_suppressed)),
            out_of_inventory_frames=tuple(sorted(out_of_inventory)),
            review_candidates=tuple(sorted(review_candidates)),
            raw_frame_count=len(raw),
            canonical_frame_count=len(canonical),
            confidence=confidence,
        )


canonicalizer = DomainFrameCanonicalizer()
