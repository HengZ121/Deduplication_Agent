#!/usr/bin/env python3
"""Optional dependency parsing for the administrative-event mapper.

The parser supplies grammatical evidence and candidate spans. Domain semantics
remain in ``framenet_mapper``: a dependency label alone cannot decide that a
client is a FrameNet Evaluee or that D25 is an administrative penalty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SyntacticSpan:
    """Text span derived from a dependency relation."""

    text: str
    relation: str
    head: str
    start: int
    end: int


class DependencyParser:
    """Lazy spaCy wrapper with a no-parser fallback.

    Loading the model lazily keeps file conversion and imports usable in
    environments where the optional NLP dependency has not been installed.
    """

    MODEL = "en_core_web_sm"
    EVENT_LEMMAS = {"impose", "terminate", "rescind", "suspend", "punish", "discipline", "reward"}
    EVALUEE_LEMMAS = {"client", "claimant"}
    CONDITION_MARKERS = {"if", "when", "unless"}
    TIME_PREPOSITIONS = {"after", "before", "during", "from", "on", "since", "through", "until"}

    def __init__(self) -> None:
        self._nlp: Any = None
        self._load_attempted = False
        self.error: str | None = None
        self.version: str | None = None

    @property
    def available(self) -> bool:
        self._load()
        return self._nlp is not None

    def analyze(self, sentence: str, trigger_start: int, trigger_end: int) -> dict[str, Any]:
        """Parse one sentence and return candidates plus auditable token edges."""
        self._load()
        if self._nlp is None:
            return {
                "available": False,
                "model": self.MODEL,
                "status": "parser_unavailable",
                "error": self.error,
                "roles": {},
            }

        doc = self._nlp(sentence)
        trigger = self._find_trigger(doc, trigger_start, trigger_end)
        if trigger is None:
            return {
                "available": True,
                "model": self.MODEL,
                "modelVersion": self.version,
                "status": "trigger_not_aligned",
                "roles": {},
            }

        roles: dict[str, dict[str, Any]] = {}
        agent = self._agent(trigger)
        if agent:
            roles["agent"] = vars(agent)
        evaluee = self._evaluee(doc, trigger)
        if evaluee:
            roles["evaluee"] = vars(evaluee)
        condition = self._condition(trigger)
        if condition:
            roles["condition"] = vars(condition)
        time = self._time(trigger)
        if time:
            roles["time"] = vars(time)

        return {
            "available": True,
            "model": self.MODEL,
            "modelVersion": self.version,
            "status": "parsed",
            "triggerToken": {
                "index": trigger.i,
                "text": trigger.text,
                "lemma": trigger.lemma_,
                "dependency": trigger.dep_,
                "headIndex": trigger.head.i,
            },
            "roles": roles,
        }

    def _load(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True
        try:
            import spacy

            self._nlp = spacy.load(self.MODEL)
            self.version = spacy.__version__
        except (ImportError, OSError) as exc:
            self.error = str(exc)

    def _find_trigger(self, doc: Any, start: int, end: int) -> Any | None:
        aligned = [token for token in doc if token.idx < end and token.idx + len(token.text) > start]
        event_tokens = [token for token in aligned if token.lemma_.lower() in self.EVENT_LEMMAS]
        if event_tokens:
            return event_tokens[-1]
        verbs = [token for token in aligned if token.pos_ in {"VERB", "AUX"}]
        return verbs[-1] if verbs else None

    def _agent(self, trigger: Any) -> SyntacticSpan | None:
        passive = any(child.dep_ in {"auxpass", "nsubjpass"} for child in trigger.children)
        if not passive:
            subjects = [child for child in trigger.children if child.dep_ in {"nsubj", "csubj"}]
            if subjects:
                return self._span(subjects[0], "active_subject", trigger.text)

        for child in trigger.children:
            if child.dep_ == "agent" or (child.dep_ == "prep" and child.lower_ == "by"):
                objects = [item for item in child.children if item.dep_ in {"pobj", "obj"}]
                if objects:
                    return self._span(objects[0], "passive_agent", trigger.text)
        return None

    def _evaluee(self, doc: Any, trigger: Any) -> SyntacticSpan | None:
        candidates = [
            token for token in doc
            if token.lemma_.lower() in self.EVALUEE_LEMMAS and self._connected(token, trigger)
        ]
        if not candidates:
            return None
        token = min(candidates, key=lambda item: self._dependency_distance(item, trigger))
        return self._span(token, f"{token.dep_}_linked_to_trigger", trigger.text)

    def _condition(self, trigger: Any) -> SyntacticSpan | None:
        clauses = []
        for child in trigger.children:
            if child.dep_ != "advcl":
                continue
            markers = {
                item.lower_ for item in child.subtree
                if item.dep_ in {"mark", "advmod"} and item.lower_ in self.CONDITION_MARKERS
            }
            if markers:
                clauses.append((child, sorted(markers)[0]))
        if not clauses:
            return None
        clause, marker = clauses[0]
        span = self._span(clause, f"conditional_advcl:{marker}", trigger.text)
        text = span.text
        if text.lower().startswith(marker + " "):
            text = text[len(marker) + 1 :]
        return SyntacticSpan(text.strip(" ,"), span.relation, span.head, span.start, span.end)

    def _time(self, trigger: Any) -> SyntacticSpan | None:
        for child in trigger.children:
            if child.dep_ == "prep" and child.lower_ in self.TIME_PREPOSITIONS:
                return self._span(child, f"temporal_prep:{child.lower_}", trigger.text)
        for child in trigger.children:
            if child.dep_ in {"npadvmod", "advmod"} and child.ent_type_ in {"DATE", "TIME"}:
                return self._span(child, f"temporal_{child.dep_}", trigger.text)
        return None

    @staticmethod
    def _span(token: Any, relation: str, head: str) -> SyntacticSpan:
        subtree = sorted(token.subtree, key=lambda item: item.i)
        # Punctuation belongs to the sentence, not the semantic role span.
        while subtree and subtree[-1].is_punct:
            subtree.pop()
        start = subtree[0].idx
        end = subtree[-1].idx + len(subtree[-1].text)
        return SyntacticSpan(token.doc.text[start:end], relation, head, start, end)

    @staticmethod
    def _connected(token: Any, trigger: Any) -> bool:
        current = token
        for _ in range(12):
            if current == trigger:
                return True
            if current.head == current:
                break
            current = current.head
        return False

    @staticmethod
    def _dependency_distance(token: Any, trigger: Any) -> int:
        current = token
        for distance in range(12):
            if current == trigger:
                return distance
            if current.head == current:
                break
            current = current.head
        return 99

dependency_parser = DependencyParser()
