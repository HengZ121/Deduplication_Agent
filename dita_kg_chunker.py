#!/usr/bin/env python3
"""Convert DITA structure into stable structural and atomic knowledge-graph nodes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import urllib.parse
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

import pandas as pd

from run_passage_pipeline import (
    element_conref_targets,
    normalized_passage,
    split_sentences,
    word_tokens,
)
from run_procedure_pipeline import (
    DitaTopicResolver,
    clean_text,
    direct_child,
    element_text,
    find_dita_root,
    read_dita_documents,
    read_dita_node_documents,
    xml_local_name,
)


STRUCTURAL_TAG_TO_TYPE = {
    "section": "section",
    "step": "step",
    "info": "information_group",
    "table": "table",
}
ATOMIC_TAGS = {
    "shortdesc",
    "p",
    "cmd",
    "stepresult",
    "result",
    "note",
    "li",
    "dd",
    "xref",
}
CONDITION_PREFIXES = (
    "if ",
    "when ",
    "unless ",
    "where ",
    "in the event ",
    "si ",
    "lorsque ",
    "quand ",
    "à moins ",
    "dans le cas ",
)


@dataclass(frozen=True)
class KnowledgeNode:
    node_id: str
    node_type: str
    is_structural: bool
    is_comparable: bool
    parent_node_id: str
    source_document_id: int
    article_path: str
    article_title: str
    document_type: str
    language: str
    modified: str
    topic_path: str
    source_element_path: str
    element_id: str
    sequence: int
    word_count: int
    content_hash: str
    conref_targets: str
    text: str


@dataclass(frozen=True)
class KnowledgeEdge:
    source_node_id: str
    relationship: str
    target_node_id: str
    sequence: int
    source_path: str


KNOWLEDGE_NODE_COLUMNS = [field.name for field in fields(KnowledgeNode)]
KNOWLEDGE_EDGE_COLUMNS = [field.name for field in fields(KnowledgeEdge)]


def stable_node_id(node_type: str, *parts: Any) -> str:
    key = "|".join(clean_text(part) for part in parts)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return f"{node_type}:{digest}"


def content_hash(text: str) -> str:
    return hashlib.sha1(normalized_passage(text).encode("utf-8")).hexdigest()


def direct_title(element: Any) -> str:
    return element_text(direct_child(element, "title"))


def atomic_spans(text: str, max_words: int = 80) -> list[str]:
    """Return non-overlapping statement spans, normally one sentence each."""

    spans: list[str] = []
    for sentence in split_sentences(text):
        if len(word_tokens(sentence)) <= max_words:
            spans.append(sentence)
            continue
        clauses = [clean_text(part) for part in re.split(r"\s*;\s*|\s+—\s+", sentence) if clean_text(part)]
        if len(clauses) == 1:
            token_matches = list(
                re.finditer(r"[\wÀ-ÖØ-öø-ÿ]+(?:[’'-][\wÀ-ÖØ-öø-ÿ]+)*", sentence, flags=re.UNICODE)
            )
            for start in range(0, len(token_matches), max_words):
                end = min(start + max_words, len(token_matches))
                char_start = token_matches[start].start()
                char_end = token_matches[end].start() if end < len(token_matches) else len(sentence)
                chunk = clean_text(sentence[char_start:char_end])
                if chunk:
                    spans.append(chunk)
            continue
        pending = ""
        for clause in clauses:
            candidate = clean_text(f"{pending}; {clause}" if pending else clause)
            if pending and len(word_tokens(candidate)) > max_words:
                spans.append(pending)
                pending = clause
            else:
                pending = candidate
        if pending:
            spans.append(pending)
    return spans


def infer_content_node_type(tag: str, text: str, element: Any) -> str:
    lowered = text.lower().lstrip()
    if tag == "cmd":
        return "action"
    if tag in {"stepresult", "result"}:
        return "expected_result"
    if tag == "note":
        note_type = clean_text(element.get("type")).lower()
        return note_type if note_type in {"warning", "danger", "caution", "tip", "important"} else "note"
    if tag == "li":
        return "list_item"
    if tag == "shortdesc":
        return "summary_statement"
    if tag == "xref":
        return "reference_statement"
    if lowered.startswith(CONDITION_PREFIXES):
        return "condition"
    if re.search(r"\b(must|shall|required|doit|doivent|obligatoire)\b", lowered):
        return "rule"
    return "statement"


class KnowledgeGraphBuilder:
    def __init__(self, dita_root: Path, articles_df: pd.DataFrame, min_comparable_words: int) -> None:
        self.dita_root = dita_root.resolve()
        self.articles_df = articles_df
        self.min_comparable_words = min_comparable_words
        self.resolver = DitaTopicResolver(self.dita_root)
        self.nodes: dict[str, KnowledgeNode] = {}
        self.edges: list[KnowledgeEdge] = []
        self._edge_keys: set[tuple[str, str, str, int]] = set()

    def add_node(self, node: KnowledgeNode) -> str:
        self.nodes.setdefault(node.node_id, node)
        return node.node_id

    def add_edge(
        self,
        source_node_id: str,
        relationship: str,
        target_node_id: str,
        sequence: int,
        source_path: str,
    ) -> None:
        key = (source_node_id, relationship, target_node_id, sequence)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append(
            KnowledgeEdge(
                source_node_id=source_node_id,
                relationship=relationship,
                target_node_id=target_node_id,
                sequence=sequence,
                source_path=source_path,
            )
        )

    def source_references(self, content_node_id: str, element: Any, topic_path: Path, sequence: int) -> None:
        for child in element.iter():
            href = clean_text(child.get("href"))
            if not href or xml_local_name(child.tag) != "xref":
                continue
            reference_id = stable_node_id("reference_target", topic_path.as_posix(), href)
            self.add_node(
                KnowledgeNode(
                    node_id=reference_id,
                    node_type="reference_target",
                    is_structural=True,
                    is_comparable=False,
                    parent_node_id="",
                    source_document_id=-1,
                    article_path="",
                    article_title="",
                    document_type="",
                    language="",
                    modified="",
                    topic_path=topic_path.relative_to(self.dita_root).as_posix(),
                    source_element_path=href,
                    element_id="",
                    sequence=0,
                    word_count=len(word_tokens(element_text(child))),
                    content_hash=content_hash(element_text(child)) if element_text(child) else "",
                    conref_targets="",
                    text=element_text(child) or href,
                )
            )
            self.add_edge(content_node_id, "REFERENCES", reference_id, sequence, topic_path.as_posix())

    def reusable_fragment_node(
        self,
        target: str,
        article: pd.Series,
    ) -> str:
        raw_path, _, fragment = target.partition("#")
        target_path = (self.dita_root / raw_path).resolve()
        root = self.resolver.parse_xml(target_path)
        element = self.resolver.find_fragment(root, fragment)
        text = self.resolver.expanded_element_text(element, target_path)
        node_id = stable_node_id("reusable_fragment", target)
        self.add_node(
            KnowledgeNode(
                node_id=node_id,
                node_type="reusable_fragment",
                is_structural=True,
                is_comparable=False,
                parent_node_id="",
                source_document_id=-1,
                article_path="",
                article_title="",
                document_type="",
                language=clean_text(article["language"]),
                modified="",
                topic_path=raw_path,
                source_element_path=target,
                element_id=fragment.rsplit("/", 1)[-1],
                sequence=0,
                word_count=len(word_tokens(text)),
                content_hash=content_hash(text),
                conref_targets="",
                text=text,
            )
        )
        for span_index, span in enumerate(atomic_spans(text)):
            words = word_tokens(span)
            statement_id = stable_node_id("reusable_statement", target, span_index, span)
            self.add_node(
                KnowledgeNode(
                    node_id=statement_id,
                    node_type="reusable_statement",
                    is_structural=False,
                    is_comparable=len(words) >= self.min_comparable_words,
                    parent_node_id=node_id,
                    source_document_id=-1,
                    article_path="",
                    article_title="",
                    document_type="",
                    language=clean_text(article["language"]),
                    modified="",
                    topic_path=raw_path,
                    source_element_path=target,
                    element_id=fragment.rsplit("/", 1)[-1],
                    sequence=span_index,
                    word_count=len(words),
                    content_hash=content_hash(span),
                    conref_targets="",
                    text=span,
                )
            )
            self.add_edge(node_id, "HAS_CONTENT", statement_id, span_index, target)
        return node_id

    def add_content_nodes(
        self,
        element: Any,
        parent_node_id: str,
        article: pd.Series,
        topic_path: Path,
        element_path: str,
        base_sequence: int,
    ) -> list[str]:
        tag = xml_local_name(element.tag)
        expanded_text = self.resolver.expanded_element_text(element, topic_path)
        targets = element_conref_targets(element, topic_path, self.resolver, self.dita_root)
        created: list[str] = []

        for span_index, span in enumerate(atomic_spans(expanded_text)):
            words = word_tokens(span)
            if not words:
                continue
            node_type = infer_content_node_type(tag, span, element)
            element_id = clean_text(element.get("id"))
            node_id = stable_node_id(
                node_type,
                article["path"],
                topic_path.relative_to(self.dita_root).as_posix(),
                element_id or element_path,
                span_index,
                normalized_passage(span),
            )
            self.add_node(
                KnowledgeNode(
                    node_id=node_id,
                    node_type=node_type,
                    is_structural=False,
                    is_comparable=len(words) >= self.min_comparable_words,
                    parent_node_id=parent_node_id,
                    source_document_id=int(article["document_id"]),
                    article_path=clean_text(article["path"]),
                    article_title=clean_text(article["title"]),
                    document_type=clean_text(article["document_type"]),
                    language=clean_text(article["language"]),
                    modified=clean_text(article["modified"]),
                    topic_path=topic_path.relative_to(self.dita_root).as_posix(),
                    source_element_path=element_path,
                    element_id=element_id,
                    sequence=base_sequence + span_index,
                    word_count=len(words),
                    content_hash=content_hash(span),
                    conref_targets=" | ".join(targets),
                    text=span,
                )
            )
            relationship = {
                "action": "HAS_ACTION",
                "condition": "HAS_CONDITION",
                "expected_result": "HAS_RESULT",
                "supporting_information": "HAS_INFORMATION",
            }.get(node_type, "HAS_CONTENT")
            self.add_edge(parent_node_id, relationship, node_id, base_sequence + span_index, topic_path.as_posix())
            for target in targets:
                reusable_id = self.reusable_fragment_node(target, article)
                self.add_edge(node_id, "REUSES", reusable_id, 0, topic_path.as_posix())
            self.source_references(node_id, element, topic_path, base_sequence + span_index)
            created.append(node_id)

        for previous, current in zip(created, created[1:]):
            self.add_edge(previous, "NEXT", current, 0, topic_path.as_posix())
        return created

    def add_table(
        self,
        table: Any,
        parent_node_id: str,
        article: pd.Series,
        topic_path: Path,
        element_path: str,
        sequence: int,
    ) -> str:
        title = direct_title(table) or "Table"
        table_id = stable_node_id("table", article["path"], topic_path.as_posix(), element_path, clean_text(table.get("id")))
        self.add_node(
            KnowledgeNode(
                node_id=table_id,
                node_type="table",
                is_structural=True,
                is_comparable=False,
                parent_node_id=parent_node_id,
                source_document_id=int(article["document_id"]),
                article_path=clean_text(article["path"]),
                article_title=clean_text(article["title"]),
                document_type=clean_text(article["document_type"]),
                language=clean_text(article["language"]),
                modified=clean_text(article["modified"]),
                topic_path=topic_path.relative_to(self.dita_root).as_posix(),
                source_element_path=element_path,
                element_id=clean_text(table.get("id")),
                sequence=sequence,
                word_count=len(word_tokens(title)),
                content_hash=content_hash(title),
                conref_targets="",
                text=title,
            )
        )
        self.add_edge(parent_node_id, "HAS_TABLE", table_id, sequence, topic_path.as_posix())

        header_cells: list[str] = []
        for element in table.iter():
            if xml_local_name(element.tag) == "thead":
                row = next((child for child in element.iter() if xml_local_name(child.tag) == "row"), None)
                if row is not None:
                    header_cells = [
                        self.resolver.expanded_element_text(entry, topic_path)
                        for entry in row
                        if xml_local_name(entry.tag) == "entry"
                    ]
                break

        body_rows: list[Any] = []
        for body in table.iter():
            if xml_local_name(body.tag) != "tbody":
                continue
            for row in body:
                if xml_local_name(row.tag) != "row":
                    continue
                body_rows.append(row)

        if not header_cells and body_rows:
            first_values = [
                self.resolver.expanded_element_text(entry, topic_path)
                for entry in body_rows[0]
                if xml_local_name(entry.tag) == "entry"
            ]
            if first_values and all(len(word_tokens(value)) <= 12 for value in first_values):
                header_cells = first_values
                body_rows = body_rows[1:]

        row_number = 0
        for row in body_rows:
            values = [
                self.resolver.expanded_element_text(entry, topic_path)
                for entry in row
                if xml_local_name(entry.tag) == "entry"
            ]
            record_texts: list[str] = []
            if len(values) > 1 and any(len(atomic_spans(value)) > 1 for value in values):
                key_label = header_cells[0] if header_cells else "Key"
                key_is_short = len(word_tokens(values[0])) <= 20
                if not key_is_short:
                    record_texts.extend(
                        clean_text(f"{key_label}: {span}")
                        for span in atomic_spans(values[0])
                    )
                key_text = f"{key_label}: {values[0]}" if key_is_short else ""
                for value_index, value in enumerate(values[1:], start=1):
                    value_label = header_cells[value_index] if value_index < len(header_cells) else f"Value {value_index}"
                    record_texts.extend(
                        clean_text(
                            f"{key_text} | {value_label}: {span}"
                            if key_text
                            else f"{value_label}: {span}"
                        )
                        for span in atomic_spans(value)
                    )
            else:
                parts = [
                    f"{header_cells[index]}: {value}" if index < len(header_cells) and header_cells[index] else value
                    for index, value in enumerate(values)
                    if value
                ]
                record_texts = [clean_text(" | ".join(parts))]

            bounded_record_texts: list[str] = []
            for record_text in record_texts:
                if len(word_tokens(record_text)) <= 80:
                    bounded_record_texts.append(record_text)
                    continue
                if " | " in record_text:
                    prefix, remainder = record_text.split(" | ", 1)
                    bounded_record_texts.extend(
                        clean_text(f"{prefix} | {span}")
                        for span in atomic_spans(remainder)
                    )
                else:
                    bounded_record_texts.extend(atomic_spans(record_text))

            for record_index, text in enumerate(filter(None, bounded_record_texts)):
                row_id = stable_node_id(
                    "reference_record",
                    article["path"],
                    topic_path.as_posix(),
                    element_path,
                    row_number,
                    record_index,
                    text,
                )
                words = word_tokens(text)
                self.add_node(
                    KnowledgeNode(
                        node_id=row_id,
                        node_type="reference_record",
                        is_structural=False,
                        is_comparable=len(words) >= self.min_comparable_words,
                        parent_node_id=table_id,
                        source_document_id=int(article["document_id"]),
                        article_path=clean_text(article["path"]),
                        article_title=clean_text(article["title"]),
                        document_type=clean_text(article["document_type"]),
                        language=clean_text(article["language"]),
                        modified=clean_text(article["modified"]),
                        topic_path=topic_path.relative_to(self.dita_root).as_posix(),
                        source_element_path=f"{element_path}/row[{row_number}]",
                        element_id=clean_text(row.get("id")),
                        sequence=row_number * 100 + record_index,
                        word_count=len(words),
                        content_hash=content_hash(text),
                        conref_targets="",
                        text=text,
                    )
                )
                self.add_edge(
                    table_id,
                    "HAS_RECORD",
                    row_id,
                    row_number * 100 + record_index,
                    topic_path.as_posix(),
                )
            row_number += 1
        return table_id

    def traverse(
        self,
        element: Any,
        parent_node_id: str,
        article: pd.Series,
        topic_path: Path,
        element_path: str,
        sequence: int,
    ) -> str | None:
        tag = xml_local_name(element.tag)
        if tag == "title":
            return None
        if tag == "li" and any(xml_local_name(child.tag) in {"ul", "ol"} for child in element):
            structural_id = stable_node_id(
                "list_group",
                article["path"],
                topic_path.as_posix(),
                element_path,
                clean_text(element.get("id")),
            )
            label = clean_text(element.text) or "List group"
            self.add_node(
                KnowledgeNode(
                    node_id=structural_id,
                    node_type="list_group",
                    is_structural=True,
                    is_comparable=False,
                    parent_node_id=parent_node_id,
                    source_document_id=int(article["document_id"]),
                    article_path=clean_text(article["path"]),
                    article_title=clean_text(article["title"]),
                    document_type=clean_text(article["document_type"]),
                    language=clean_text(article["language"]),
                    modified=clean_text(article["modified"]),
                    topic_path=topic_path.relative_to(self.dita_root).as_posix(),
                    source_element_path=element_path,
                    element_id=clean_text(element.get("id")),
                    sequence=sequence,
                    word_count=len(word_tokens(label)),
                    content_hash=content_hash(label),
                    conref_targets="",
                    text=label,
                )
            )
            self.add_edge(parent_node_id, "CONTAINS", structural_id, sequence, topic_path.as_posix())
            for child_index, child in enumerate(element):
                child_tag = xml_local_name(child.tag)
                self.traverse(
                    child,
                    structural_id,
                    article,
                    topic_path,
                    f"{element_path}/{child_tag}[{child_index}]",
                    child_index,
                )
            return structural_id
        if tag in ATOMIC_TAGS:
            created = self.add_content_nodes(element, parent_node_id, article, topic_path, element_path, sequence * 100)
            return created[0] if created else None
        if tag == "table":
            return self.add_table(element, parent_node_id, article, topic_path, element_path, sequence)

        next_parent = parent_node_id
        structural_id: str | None = None
        if tag in STRUCTURAL_TAG_TO_TYPE:
            node_type = STRUCTURAL_TAG_TO_TYPE[tag]
            title = direct_title(element)
            if tag == "step" and not title:
                cmd = next((child for child in element if xml_local_name(child.tag) == "cmd"), None)
                title = self.resolver.expanded_element_text(cmd, topic_path) if cmd is not None else "Step"
            title = title or node_type.replace("_", " ").title()
            structural_id = stable_node_id(node_type, article["path"], topic_path.as_posix(), element_path, clean_text(element.get("id")))
            self.add_node(
                KnowledgeNode(
                    node_id=structural_id,
                    node_type=node_type,
                    is_structural=True,
                    is_comparable=False,
                    parent_node_id=parent_node_id,
                    source_document_id=int(article["document_id"]),
                    article_path=clean_text(article["path"]),
                    article_title=clean_text(article["title"]),
                    document_type=clean_text(article["document_type"]),
                    language=clean_text(article["language"]),
                    modified=clean_text(article["modified"]),
                    topic_path=topic_path.relative_to(self.dita_root).as_posix(),
                    source_element_path=element_path,
                    element_id=clean_text(element.get("id")),
                    sequence=sequence,
                    word_count=len(word_tokens(title)),
                    content_hash=content_hash(title),
                    conref_targets="",
                    text=title,
                )
            )
            relationship = "HAS_STEP" if tag == "step" else "CONTAINS"
            self.add_edge(parent_node_id, relationship, structural_id, sequence, topic_path.as_posix())
            next_parent = structural_id

        child_structural_ids: list[str] = []
        for child_index, child in enumerate(element):
            child_tag = xml_local_name(child.tag)
            if child_tag == "title":
                continue
            child_id = self.traverse(
                child,
                next_parent,
                article,
                topic_path,
                f"{element_path}/{child_tag}[{child_index}]",
                child_index,
            )
            if child_id and self.nodes[child_id].is_structural:
                child_structural_ids.append(child_id)
        for previous, current in zip(child_structural_ids, child_structural_ids[1:]):
            self.add_edge(previous, "NEXT", current, 0, topic_path.as_posix())
        return structural_id

    def build(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        article_lookup = {clean_text(row["path"]): row for _, row in self.articles_df.iterrows()}
        for map_path in sorted(self.dita_root.rglob("*.ditamap")):
            relative_map_path = map_path.relative_to(self.dita_root).as_posix()
            article = article_lookup.get(relative_map_path)
            if article is None:
                continue
            article_id = stable_node_id("article", relative_map_path)
            self.add_node(
                KnowledgeNode(
                    node_id=article_id,
                    node_type="article",
                    is_structural=True,
                    is_comparable=False,
                    parent_node_id="",
                    source_document_id=int(article["document_id"]),
                    article_path=relative_map_path,
                    article_title=clean_text(article["title"]),
                    document_type=clean_text(article["document_type"]),
                    language=clean_text(article["language"]),
                    modified=clean_text(article["modified"]),
                    topic_path="",
                    source_element_path=relative_map_path,
                    element_id="",
                    sequence=0,
                    word_count=len(word_tokens(article["title"])),
                    content_hash=content_hash(article["title"]),
                    conref_targets="",
                    text=clean_text(article["title"]),
                )
            )
            map_root = self.resolver.parse_xml(map_path)
            seen_topics: set[Path] = set()
            topic_sequence = 0
            for topicref in map_root.iter():
                if xml_local_name(topicref.tag) != "topicref":
                    continue
                href = clean_text(topicref.get("href"))
                if not href or urllib.parse.urlparse(href).scheme:
                    continue
                topic_path, _ = self.resolver.resolve_local_reference(map_path, href)
                if topic_path in seen_topics or not topic_path.is_file():
                    continue
                seen_topics.add(topic_path)
                topic_root = self.resolver.parse_xml(topic_path)
                topic_type = xml_local_name(topic_root.tag)
                topic_title = direct_title(topic_root) or topic_path.stem
                relative_topic_path = topic_path.relative_to(self.dita_root).as_posix()
                topic_id = stable_node_id("topic", relative_topic_path)
                self.add_node(
                    KnowledgeNode(
                        node_id=topic_id,
                        node_type=f"{topic_type}_topic",
                        is_structural=True,
                        is_comparable=False,
                        parent_node_id=article_id,
                        source_document_id=int(article["document_id"]),
                        article_path=relative_map_path,
                        article_title=clean_text(article["title"]),
                        document_type=clean_text(article["document_type"]),
                        language=clean_text(article["language"]),
                        modified=clean_text(article["modified"]),
                        topic_path=relative_topic_path,
                        source_element_path=relative_topic_path,
                        element_id=clean_text(topic_root.get("id")),
                        sequence=topic_sequence,
                        word_count=len(word_tokens(topic_title)),
                        content_hash=content_hash(topic_title),
                        conref_targets="",
                        text=topic_title,
                    )
                )
                self.add_edge(article_id, "CONTAINS", topic_id, topic_sequence, relative_map_path)
                self.traverse(topic_root, topic_id, article, topic_path, topic_type, 0)
                topic_sequence += 1

        nodes_df = pd.DataFrame(asdict(node) for node in self.nodes.values())
        edges_df = pd.DataFrame(asdict(edge) for edge in self.edges)
        return nodes_df, edges_df


def load_article_metadata(input_path: Path, metadata_csv: Path | None) -> pd.DataFrame:
    required = {"document_id", "path", "document_type", "title", "language", "modified"}
    if metadata_csv is not None and metadata_csv.is_file():
        articles_df = pd.read_csv(metadata_csv, encoding="utf-8-sig", keep_default_na=False)
        dita_root = find_dita_root(input_path)
        input_paths = {
            path.relative_to(dita_root).as_posix()
            for path in dita_root.rglob("*.ditamap")
        }
        metadata_paths = set(articles_df["path"].map(clean_text)) if "path" in articles_df else set()
        if required <= set(articles_df.columns) and metadata_paths == input_paths:
            print(f"Reusing article metadata from {metadata_csv}.")
            return articles_df
        print(f"Ignoring article metadata from {metadata_csv} because it does not match this DITA input.")
    documents = read_dita_documents(input_path)
    return pd.DataFrame(asdict(document) for document in documents)


def chunk_dita_to_frames(
    input_path: Path,
    article_metadata_csv: Path | None,
    min_comparable_words: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build all structural nodes, atomic knowledge nodes, and graph edges."""

    articles_df = load_article_metadata(input_path, article_metadata_csv)
    builder = KnowledgeGraphBuilder(find_dita_root(input_path), articles_df, min_comparable_words)
    return builder.build()


def load_dita_as_document_nodes(
    input_path: Path,
    min_comparable_words: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Represent each DITA article or standalone topic as one unbroken node."""

    dita_root = find_dita_root(input_path)
    documents = (
        read_dita_documents(input_path)
        if next(dita_root.rglob("*.ditamap"), None) is not None
        else read_dita_node_documents(input_path)
    )
    nodes: list[KnowledgeNode] = []
    for document in documents:
        word_count = len(word_tokens(document.text))
        nodes.append(
            KnowledgeNode(
                node_id=stable_node_id("dita_document", document.path),
                node_type="dita_document",
                is_structural=False,
                is_comparable=word_count >= min_comparable_words,
                parent_node_id="",
                source_document_id=document.document_id,
                article_path=document.path,
                article_title=document.title,
                document_type=document.document_type,
                language=document.language,
                modified=document.modified,
                topic_path="",
                source_element_path=document.path,
                element_id="",
                sequence=0,
                word_count=word_count,
                content_hash=content_hash(document.text),
                conref_targets="",
                text=document.text,
            )
        )
    nodes_df = pd.DataFrame((asdict(node) for node in nodes), columns=KNOWLEDGE_NODE_COLUMNS)
    edges_df = pd.DataFrame(columns=KNOWLEDGE_EDGE_COLUMNS)
    return nodes_df, edges_df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chunk DITA into fine-grained knowledge-graph nodes and edges.")
    parser.add_argument("--input", type=Path, default=Path("KMT_dita"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/kmt_kg_pipeline"))
    parser.add_argument(
        "--article-metadata-csv",
        type=Path,
        default=Path("outputs/kmt_dita_pipeline/procedure_documents_with_clusters.csv"),
    )
    parser.add_argument("--min-comparable-words", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print("Building DITA-native structural and atomic knowledge nodes...")
    nodes_df, edges_df = chunk_dita_to_frames(
        args.input,
        args.article_metadata_csv,
        args.min_comparable_words,
    )
    nodes_df.to_csv(
        args.output_dir / "kg_nodes.csv",
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_MINIMAL,
    )
    edges_df.to_csv(
        args.output_dir / "kg_edges.csv",
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_MINIMAL,
    )
    print(f"Built {len(nodes_df)} nodes and {len(edges_df)} edges.")


if __name__ == "__main__":
    main()
