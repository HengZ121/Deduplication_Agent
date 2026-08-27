#!/usr/bin/env python3
"""Detect duplicate or conflicting passages in an extracted DITA dataset.

The document-level runner remains the broad discovery stage. This companion
runner works at a smaller granularity: meaningful DITA blocks are split into
overlapping windows containing at most five sentences, multilingual embeddings
retrieve likely cross-article matches, and a CrossEncoder makes the primary
relationship decision. Only ambiguous pairs are sent to the configured LLM.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from run_procedure_pipeline import (
    DEFAULT_API_KEY_FILE,
    DEFAULT_CROSS_ENCODER_MODEL,
    DEFAULT_LLM_WORKERS,
    DEFAULT_MODEL,
    DitaTopicResolver,
    clean_text,
    find_dita_root,
    language_family,
    predict_cross_encoder_scores,
    read_dita_documents,
    resolve_api_key,
    sigmoid,
    xml_local_name,
)


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_OUTPUT_DIR = Path("outputs/kmt_passage_pipeline")
FINAL_RELATIONSHIP_TYPES = {
    "duplicate/semantic duplicate",
    "one passage included in another",
    "conflicting information",
    "independent",
}

# These elements are useful comparison units and are treated as atomic. The
# traversal stops at a matching parent so nested <p> content is not duplicated.
ATOMIC_DITA_BLOCKS = {
    "shortdesc",
    "p",
    "li",
    "note",
    "cmd",
    "info",
    "stepresult",
    "result",
    "entry",
    "dd",
}


@dataclass(frozen=True)
class PassageWindow:
    passage_id: int
    source_document_id: int
    article_path: str
    article_title: str
    document_type: str
    language: str
    modified: str
    topic_path: str
    block_index: int
    block_type: str
    element_id: str
    sentence_start: int
    sentence_end: int
    sentence_count: int
    word_count: int
    contains_conref: bool
    conref_targets: str
    text: str


UNICODE_PUNCTUATION_TRANSLATION = str.maketrans(
    {
        # Apostrophe-like characters commonly introduced by Office, PDF, and
        # full-width encodings. Treat them as the same contraction marker.
        "\u2018": "'",
        "\u2019": "'",
        "\u201b": "'",
        "\u02bc": "'",
        "\u2032": "'",
        "\uff07": "'",
        "\u00b4": "'",
        "`": "'",
        # Hyphen/dash variants are equivalent inside compound word tokens.
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\ufe63": "-",
        "\uff0d": "-",
    }
)


def normalize_unicode_text(text: str) -> str:
    """Canonicalize compatibility glyphs without removing linguistic accents."""

    value = unicodedata.normalize("NFKC", clean_text(text)).translate(
        UNICODE_PUNCTUATION_TRANSLATION
    )
    # Zero-width and directional formatting characters are display metadata,
    # not content. Removing them prevents visually identical text from being
    # treated as a different node.
    value = "".join(character for character in value if unicodedata.category(character) != "Cf")
    # Some exports insert spaces on one or both sides of an apostrophe or
    # hyphen inside a word (for example ``n 'est``). Collapse only when both
    # neighbours are word characters so ordinary punctuation spacing remains
    # unchanged.
    value = re.sub(r"(?<=\w)\s*'\s*(?=\w)", "'", value)
    value = re.sub(r"(?<=\w)\s*-\s*(?=\w)", "-", value)
    return clean_text(value)


def word_tokens(text: str) -> list[str]:
    """Return canonical Unicode word tokens suitable for English and French."""

    value = normalize_unicode_text(text).casefold()
    return re.findall(r"[\wÀ-ÖØ-öø-ÿ]+(?:['-][\wÀ-ÖØ-öø-ÿ]+)*", value, flags=re.UNICODE)


def normalized_passage(text: str) -> str:
    return " ".join(word_tokens(text))


def split_sentences(text: str) -> list[str]:
    """Split English or French prose without requiring a downloaded tokenizer."""

    value = clean_text(text)
    if not value:
        return []

    # DITA blocks already provide a strong boundary. Within each block, split
    # on terminal punctuation while avoiding common abbreviations and decimals.
    protected = value
    abbreviations = {"e.g.", "i.e.", "etc.", "p. ex.", "c.-à-d.", "M.", "Mme.", "Dr."}
    for abbreviation in abbreviations:
        protected = re.sub(
            re.escape(abbreviation),
            lambda match: match.group(0).replace(".", "<prd>"),
            protected,
            flags=re.IGNORECASE,
        )
    protected = re.sub(r"(?<=\d)\.(?=\d)", "<prd>", protected)
    pieces = re.split(r"(?<=[.!?…])(?:[\"'»”)]*)\s+", protected)
    return [clean_text(piece.replace("<prd>", ".")) for piece in pieces if clean_text(piece)]


def sentence_windows(sentences: list[str], max_sentences: int) -> Iterable[tuple[int, int, str]]:
    """Yield overlapping windows capped at ``max_sentences``.

    Short structural blocks remain intact. Longer blocks use a one-sentence
    stride so a duplicated passage cannot disappear at an arbitrary boundary.
    """

    if max_sentences < 1:
        raise ValueError("max_sentences must be at least 1")
    if not sentences:
        return
    if len(sentences) <= max_sentences:
        yield 0, len(sentences), clean_text(" ".join(sentences))
        return
    for start in range(0, len(sentences) - max_sentences + 1):
        end = start + max_sentences
        yield start, end, clean_text(" ".join(sentences[start:end]))


def iter_atomic_blocks(root: Any) -> Iterable[Any]:
    """Yield non-overlapping semantic block elements in document order."""

    def walk(element: Any) -> Iterable[Any]:
        if xml_local_name(element.tag) in ATOMIC_DITA_BLOCKS:
            yield element
            return
        for child in element:
            yield from walk(child)

    yield from walk(root)


def element_conref_targets(
    element: Any,
    topic_path: Path,
    resolver: DitaTopicResolver,
    dita_root: Path,
) -> list[str]:
    targets: list[str] = []
    for child in element.iter():
        conref = clean_text(child.get("conref"))
        if not conref:
            continue
        target_path, fragment = resolver.resolve_local_reference(topic_path, conref)
        target_name = target_path.relative_to(dita_root.resolve()).as_posix()
        targets.append(f"{target_name}#{fragment}" if fragment else target_name)
    return sorted(set(targets))


def read_dita_passage_windows(
    input_path: Path,
    max_sentences: int = 5,
    min_words: int = 12,
) -> list[PassageWindow]:
    """Load cross-article comparison windows from the referenced DITA topics."""

    dita_root = find_dita_root(input_path)
    article_documents = read_dita_documents(input_path)
    article_by_path = {document.path: document for document in article_documents}
    resolver = DitaTopicResolver(dita_root)
    passages: list[PassageWindow] = []

    for map_path in sorted(dita_root.rglob("*.ditamap")):
        article_path = map_path.relative_to(dita_root).as_posix()
        article = article_by_path.get(article_path)
        if article is None:
            continue
        map_root = resolver.parse_xml(map_path)
        seen_topic_paths: set[Path] = set()
        block_index = 0

        for topicref in map_root.iter():
            if xml_local_name(topicref.tag) != "topicref":
                continue
            href = clean_text(topicref.get("href"))
            if not href or urllib.parse.urlparse(href).scheme:
                continue
            topic_path, _ = resolver.resolve_local_reference(map_path, href)
            if topic_path in seen_topic_paths or not topic_path.is_file():
                continue
            seen_topic_paths.add(topic_path)
            topic_root = resolver.parse_xml(topic_path)
            topic_relative_path = topic_path.relative_to(dita_root.resolve()).as_posix()

            for element in iter_atomic_blocks(topic_root):
                block_text = resolver.expanded_element_text(element, topic_path)
                sentences = split_sentences(block_text)
                conref_targets = element_conref_targets(element, topic_path, resolver, dita_root)
                element_id = clean_text(element.get("id"))
                for sentence_start, sentence_end, window_text in sentence_windows(sentences, max_sentences):
                    tokens = word_tokens(window_text)
                    if len(tokens) < min_words:
                        continue
                    passages.append(
                        PassageWindow(
                            passage_id=len(passages),
                            source_document_id=article.document_id,
                            article_path=article.path,
                            article_title=article.title,
                            document_type=article.document_type,
                            language=article.language,
                            modified=article.modified,
                            topic_path=topic_relative_path,
                            block_index=block_index,
                            block_type=xml_local_name(element.tag),
                            element_id=element_id,
                            sentence_start=sentence_start,
                            sentence_end=sentence_end,
                            sentence_count=sentence_end - sentence_start,
                            word_count=len(tokens),
                            contains_conref=bool(conref_targets),
                            conref_targets=" | ".join(conref_targets),
                            text=window_text,
                        )
                    )
                block_index += 1
    return passages


def encode_passages(
    passages_df: pd.DataFrame,
    model_name: str,
    batch_size: int,
) -> np.ndarray:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return encode_passages_with_transformers(passages_df, model_name, batch_size)

    print(f"Loading multilingual embedding model '{model_name}' with sentence-transformers...")
    model = SentenceTransformer(model_name)
    print(f"Encoding {len(passages_df)} passage windows...")
    embeddings = model.encode(
        passages_df["text"].tolist(),
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return np.asarray(embeddings, dtype="float32")


def encode_passages_with_transformers(
    passages_df: pd.DataFrame,
    model_name: str,
    batch_size: int,
) -> np.ndarray:
    """Mean-pool a sentence-transformer model using the base Transformers API."""

    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("Passage retrieval requires torch and transformers.") from exc

    from tqdm.auto import tqdm

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading multilingual embedding model '{model_name}' with Transformers on {device}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name).to(device)
    model.eval()
    texts = passages_df["text"].tolist()
    batches: list[np.ndarray] = []

    for start in tqdm(range(0, len(texts), batch_size), desc="Passage embedding"):
        batch = texts[start : start + batch_size]
        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.no_grad():
            hidden = model(**encoded).last_hidden_state
            attention_mask = encoded["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
            pooled = (hidden * attention_mask).sum(dim=1) / attention_mask.sum(dim=1).clamp(min=1e-9)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
        batches.append(pooled.cpu().numpy().astype("float32"))
    embeddings = np.concatenate(batches, axis=0)
    del model
    if device == "cuda":
        torch.cuda.empty_cache()
    return embeddings


def exact_candidate_indices(
    passages_df: pd.DataFrame,
    max_group_links: int = 100,
) -> dict[tuple[int, int], float]:
    """Link repeated normalized passages without expanding large boilerplate groups quadratically."""

    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in passages_df.iterrows():
        normalized = normalized_passage(str(row["text"]))
        if normalized:
            groups[(language_family(row["language"]), normalized)].append(int(index))

    pairs: dict[tuple[int, int], float] = {}
    for indices in groups.values():
        if len(indices) < 2:
            continue
        representatives: dict[int, int] = {}
        for index in indices:
            document_id = int(passages_df.iloc[index]["source_document_id"])
            representatives.setdefault(document_id, index)
        unique_indices = list(representatives.values())
        if len(unique_indices) < 2:
            continue
        # A star links the whole reuse family with O(n) pairs. The cap avoids a
        # ubiquitous boilerplate sentence dominating the result set.
        anchor = unique_indices[0]
        for index in unique_indices[1 : max_group_links + 1]:
            pair = (min(anchor, index), max(anchor, index))
            pairs[pair] = 1.0
    return pairs


def retrieve_candidate_indices(
    passages_df: pd.DataFrame,
    embeddings: np.ndarray,
    threshold: float,
    neighbors_per_passage: int,
    retrieval_batch_size: int,
) -> dict[tuple[int, int], float]:
    try:
        import faiss
    except ImportError:
        return retrieve_candidate_indices_with_torch(
            passages_df,
            embeddings,
            threshold,
            neighbors_per_passage,
            retrieval_batch_size,
        )

    candidate_scores = exact_candidate_indices(passages_df)
    language_groups = passages_df.groupby(passages_df["language"].map(language_family), sort=False).groups

    for language, group_indices in language_groups.items():
        indices = np.asarray(list(group_indices), dtype=np.int64)
        if len(indices) < 2:
            continue
        group_embeddings = np.ascontiguousarray(embeddings[indices], dtype="float32")
        index = faiss.IndexFlatIP(group_embeddings.shape[1])
        index.add(group_embeddings)
        search_count = min(len(indices), max(neighbors_per_passage + 20, 25))
        scores, neighbors = index.search(group_embeddings, search_count)

        for local_i, (row_scores, row_neighbors) in enumerate(zip(scores, neighbors)):
            global_i = int(indices[local_i])
            document_i = int(passages_df.iloc[global_i]["source_document_id"])
            accepted = 0
            for score, local_j in zip(row_scores, row_neighbors):
                if local_j < 0 or float(score) < threshold:
                    continue
                global_j = int(indices[int(local_j)])
                if global_j == global_i:
                    continue
                if int(passages_df.iloc[global_j]["source_document_id"]) == document_i:
                    continue
                pair = (min(global_i, global_j), max(global_i, global_j))
                candidate_scores[pair] = max(candidate_scores.get(pair, -1.0), float(score))
                accepted += 1
                if accepted >= neighbors_per_passage:
                    break
        print(f"Retrieved {len(candidate_scores)} unique candidate pairs after language group {language!r}.")
    return candidate_scores


def retrieve_candidate_indices_with_torch(
    passages_df: pd.DataFrame,
    embeddings: np.ndarray,
    threshold: float,
    neighbors_per_passage: int,
    retrieval_batch_size: int,
) -> dict[tuple[int, int], float]:
    """Retrieve exact top-k neighbors in GPU/CPU batches when FAISS is unavailable."""

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Passage retrieval requires either faiss-cpu or torch.") from exc

    from tqdm.auto import tqdm

    device = "cuda" if torch.cuda.is_available() else "cpu"
    candidate_scores = exact_candidate_indices(passages_df)
    language_groups = passages_df.groupby(passages_df["language"].map(language_family), sort=False).groups
    document_ids = passages_df["source_document_id"].to_numpy(dtype=np.int64)

    for language, group_indices in language_groups.items():
        indices = np.asarray(list(group_indices), dtype=np.int64)
        if len(indices) < 2:
            continue
        corpus = torch.from_numpy(np.ascontiguousarray(embeddings[indices])).to(device)
        search_count = min(len(indices), max(neighbors_per_passage + 20, 25))
        description = f"Neighbor search {language or 'unknown'}"

        for start in tqdm(range(0, len(indices), retrieval_batch_size), desc=description):
            end = min(start + retrieval_batch_size, len(indices))
            similarities = corpus[start:end] @ corpus.T
            row_scores, row_neighbors = torch.topk(similarities, k=search_count, dim=1)
            score_rows = row_scores.cpu().numpy()
            neighbor_rows = row_neighbors.cpu().numpy()

            for offset, (scores, neighbors) in enumerate(zip(score_rows, neighbor_rows)):
                global_i = int(indices[start + offset])
                document_i = int(document_ids[global_i])
                accepted = 0
                for score, local_j in zip(scores, neighbors):
                    if float(score) < threshold:
                        continue
                    global_j = int(indices[int(local_j)])
                    if global_j == global_i or int(document_ids[global_j]) == document_i:
                        continue
                    pair = (min(global_i, global_j), max(global_i, global_j))
                    candidate_scores[pair] = max(candidate_scores.get(pair, -1.0), float(score))
                    accepted += 1
                    if accepted >= neighbors_per_passage:
                        break
            del similarities, row_scores, row_neighbors
        del corpus
        if device == "cuda":
            torch.cuda.empty_cache()
        print(f"Retrieved {len(candidate_scores)} unique candidate pairs after language group {language!r}.")
    return candidate_scores


def candidate_pair_record(
    passages_df: pd.DataFrame,
    index1: int,
    index2: int,
    embedding_similarity: float,
) -> dict[str, Any]:
    row1 = passages_df.iloc[index1]
    row2 = passages_df.iloc[index2]
    record: dict[str, Any] = {
        "embedding_similarity": float(embedding_similarity),
        "normalized_equal": normalized_passage(row1["text"]) == normalized_passage(row2["text"]),
        "shared_conref_target": bool(
            set(filter(None, str(row1["conref_targets"]).split(" | ")))
            & set(filter(None, str(row2["conref_targets"]).split(" | ")))
        ),
    }
    fields = [
        "passage_id",
        "source_document_id",
        "article_path",
        "article_title",
        "document_type",
        "language",
        "modified",
        "topic_path",
        "block_index",
        "block_type",
        "element_id",
        "sentence_start",
        "sentence_end",
        "sentence_count",
        "word_count",
        "contains_conref",
        "conref_targets",
        "text",
    ]
    for side, row in ((1, row1), (2, row2)):
        for field in fields:
            record[f"item{side}_{field}"] = row[field]
    return record


def build_candidate_pairs(
    passages_df: pd.DataFrame,
    embeddings: np.ndarray,
    threshold: float,
    neighbors_per_passage: int,
    retrieval_batch_size: int,
    max_candidates: int,
) -> pd.DataFrame:
    candidate_scores = retrieve_candidate_indices(
        passages_df,
        embeddings,
        threshold,
        neighbors_per_passage,
        retrieval_batch_size,
    )
    ranked = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)[:max_candidates]
    return pd.DataFrame(
        candidate_pair_record(passages_df, pair[0], pair[1], score)
        for pair, score in ranked
    )


def add_cross_encoder_scores(
    pairs_df: pd.DataFrame,
    model_name: str,
    batch_size: int,
    text_chars: int,
) -> pd.DataFrame:
    if pairs_df.empty:
        pairs_df["cross_encoder_score"] = []
        return pairs_df

    def passage_context(row: pd.Series, side: int) -> str:
        title = clean_text(row[f"item{side}_article_title"])
        text = clean_text(row[f"item{side}_text"])[:text_chars]
        return f"Article: {title}\nPassage: {text}"

    doc_pairs = [
        [passage_context(row, 1), passage_context(row, 2)]
        for _, row in pairs_df.iterrows()
    ]
    print(f"Scoring {len(doc_pairs)} passage pairs with CrossEncoder '{model_name}'...")
    raw_scores = predict_cross_encoder_scores(model_name, doc_pairs, batch_size)
    result = pairs_df.copy()
    result["cross_encoder_score"] = sigmoid(raw_scores).astype(float)
    return result.sort_values(
        ["cross_encoder_score", "embedding_similarity"],
        ascending=[False, False],
    ).reset_index(drop=True)


def token_jaccard(text1: str, text2: str) -> float:
    tokens1 = set(word_tokens(text1))
    tokens2 = set(word_tokens(text2))
    if not tokens1 or not tokens2:
        return 0.0
    return len(tokens1 & tokens2) / len(tokens1 | tokens2)


def contains_passage(text1: str, text2: str, minimum_words: int = 12) -> bool:
    normalized1 = normalized_passage(text1)
    normalized2 = normalized_passage(text2)
    shorter, longer = sorted((normalized1, normalized2), key=len)
    return len(shorter.split()) >= minimum_words and shorter != longer and shorter in longer


def has_conflict_signal(text1: str, text2: str) -> bool:
    numbers1 = set(re.findall(r"\b\d+(?:[.,]\d+)?%?\b", text1))
    numbers2 = set(re.findall(r"\b\d+(?:[.,]\d+)?%?\b", text2))
    negations = (" not ", " no ", " never ", " ne ", " n’", " n'", " pas ", " jamais ")
    padded1 = f" {text1.lower()} "
    padded2 = f" {text2.lower()} "
    negation_mismatch = any((token in padded1) != (token in padded2) for token in negations)
    return bool(numbers1 and numbers2 and numbers1 != numbers2) or negation_mismatch


def initial_cross_encoder_decision(
    row: pd.Series,
    duplicate_threshold: float,
    independent_threshold: float,
) -> tuple[str, str, bool]:
    text1 = str(row["item1_text"])
    text2 = str(row["item2_text"])
    score = float(row["cross_encoder_score"])
    embedding_score = float(row["embedding_similarity"])
    jaccard = token_jaccard(text1, text2)

    if normalized_passage(text1) == normalized_passage(text2):
        return "duplicate/semantic duplicate", "Normalized passage text is identical.", False
    if contains_passage(text1, text2):
        return "one passage included in another", "One normalized passage is contained in the other.", False

    conflict_signal = has_conflict_signal(text1, text2)
    if score >= duplicate_threshold and embedding_score >= 0.90 and jaccard >= 0.72 and not conflict_signal:
        return (
            "duplicate/semantic duplicate",
            "CrossEncoder, embedding, and lexical-overlap scores all strongly support duplication.",
            False,
        )
    if score <= independent_threshold:
        return "independent", "CrossEncoder score is below the independent threshold.", False

    reasons = ["CrossEncoder score falls in the review band"]
    if conflict_signal:
        reasons.append("numbers or negation differ")
    if jaccard < 0.72:
        reasons.append("lexical overlap is not strong enough for automatic duplicate labeling")
    return "independent", "; ".join(reasons) + ".", True


def openai_passage_request(
    api_key: str,
    model: str,
    row: pd.Series,
    timeout: int,
) -> dict[str, str]:
    prompt = {
        "role": "user",
        "content": (
            "Classify the relationship between the two passages. Return only JSON with keys "
            "relationship_type and analysis. relationship_type must be exactly one of:\n"
            "- duplicate/semantic duplicate: same scoped fact or instruction, even if reworded;\n"
            "- one passage included in another: one passage's substantive information is contained in the other;\n"
            "- conflicting information: the same exact scoped case has mutually incompatible claims;\n"
            "- independent: related wording, templates, or different scopes without duplication or contradiction.\n"
            "Different systems, actions, roles, benefits, objects, years, or scenarios are independent. A missing "
            "detail alone is not a conflict. Judge the passage relationship, using article titles only as scope context.\n\n"
            f"Passage 1 article: {row['item1_article_title']}\n"
            f"Passage 1: {row['item1_text']}\n\n"
            f"Passage 2 article: {row['item2_article_title']}\n"
            f"Passage 2: {row['item2_text']}"
        ),
    }
    payload = {
        "model": model,
        "messages": [prompt],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"].get("content", "{}").strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content, re.DOTALL | re.IGNORECASE)
    if fenced:
        content = fenced.group(1).strip()
    parsed = json.loads(content)
    relationship_type = clean_text(parsed.get("relationship_type"))
    analysis = clean_text(parsed.get("analysis"))
    if relationship_type not in FINAL_RELATIONSHIP_TYPES:
        raise ValueError(f"Unexpected relationship_type: {relationship_type!r}")
    return {"relationship_type": relationship_type, "analysis": analysis}


def classify_relationships(
    pairs_df: pd.DataFrame,
    api_key: str | None,
    model: str,
    duplicate_threshold: float,
    independent_threshold: float,
    llm_limit: int,
    llm_workers: int,
    api_timeout: int,
) -> pd.DataFrame:
    result = pairs_df.copy()
    initial = result.apply(
        initial_cross_encoder_decision,
        axis=1,
        duplicate_threshold=duplicate_threshold,
        independent_threshold=independent_threshold,
    )
    result["final_relationship_type"] = [item[0] for item in initial]
    result["final_analysis"] = [item[1] for item in initial]
    result["is_borderline"] = [item[2] for item in initial]
    result["classification_source"] = ["cross_encoder_borderline_fallback" if item[2] else "cross_encoder" for item in initial]

    borderline_indices = result.index[result["is_borderline"]].tolist()
    result["llm_review_status"] = "not_needed"
    if borderline_indices:
        result.loc[borderline_indices, "llm_review_status"] = "not_reviewed_limit" if api_key else "not_reviewed_no_key"
    if not api_key or llm_limit <= 0 or not borderline_indices:
        return result

    # Review the most relevant ambiguous pairs first. All remaining pairs keep
    # the conservative CrossEncoder fallback label and are explicitly marked.
    review_indices = borderline_indices[:llm_limit]
    result.loc[review_indices, "llm_review_status"] = "pending"

    def review(row_index: int) -> tuple[int, str, str, str]:
        try:
            response = openai_passage_request(api_key, model, result.loc[row_index], api_timeout)
            return row_index, response["relationship_type"], response["analysis"], "reviewed"
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
            return row_index, result.at[row_index, "final_relationship_type"], str(exc), "api_error"

    from tqdm.auto import tqdm

    workers = max(1, min(llm_workers, len(review_indices)))
    print(f"Reviewing {len(review_indices)} borderline pairs with {workers} LLM worker(s)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(review, int(index)) for index in review_indices]
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="LLM review"):
            row_index, relationship_type, analysis, status = future.result()
            if status == "reviewed":
                result.at[row_index, "final_relationship_type"] = relationship_type
                result.at[row_index, "classification_source"] = "llm_borderline"
            result.at[row_index, "final_analysis"] = analysis
            result.at[row_index, "llm_review_status"] = status
    return result


def write_summary(
    output_dir: Path,
    passages_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    results_df: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    relationship_counts = (
        results_df["final_relationship_type"].value_counts().to_dict()
        if "final_relationship_type" in results_df
        else {}
    )
    summary = {
        "input_format": "dita",
        "comparison_unit": "structural DITA block sentence window",
        "max_window_sentences": args.max_window_sentences,
        "minimum_window_words": args.min_window_words,
        "passage_window_count": int(len(passages_df)),
        "source_article_count": int(passages_df["source_document_id"].nunique()),
        "candidate_pair_count": int(len(candidates_df)),
        "embedding_model": args.embedding_model,
        "embedding_threshold": args.embedding_threshold,
        "neighbors_per_passage": args.neighbors_per_passage,
        "cross_encoder_model": args.cross_encoder_model,
        "cross_encoder_duplicate_threshold": args.cross_encoder_duplicate_threshold,
        "cross_encoder_independent_threshold": args.cross_encoder_independent_threshold,
        "borderline_pair_count": int(results_df["is_borderline"].sum()) if "is_borderline" in results_df else 0,
        "llm_reviewed_pair_count": int((results_df["llm_review_status"] == "reviewed").sum())
        if "llm_review_status" in results_df
        else 0,
        "relationship_counts": {str(key): int(value) for key, value in relationship_counts.items()},
        "outputs": [
            "passage_windows.csv",
            "passage_candidate_pairs.csv",
            "passage_deduplication_results.csv",
            "run_summary.json",
        ],
    }
    (output_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect duplicate passages in extracted DITA articles.")
    parser.add_argument("--input", type=Path, default=Path("KMT_dita"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-window-sentences", type=int, default=5)
    parser.add_argument("--min-window-words", type=int, default=12)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--embedding-batch-size", type=int, default=128)
    parser.add_argument("--embedding-threshold", type=float, default=0.72)
    parser.add_argument("--neighbors-per-passage", type=int, default=5)
    parser.add_argument("--retrieval-batch-size", type=int, default=512)
    parser.add_argument("--max-candidates", type=int, default=500)
    parser.add_argument("--cross-encoder-model", default=DEFAULT_CROSS_ENCODER_MODEL)
    parser.add_argument("--cross-encoder-batch-size", type=int, default=32)
    parser.add_argument("--cross-encoder-text-chars", type=int, default=2500)
    parser.add_argument("--cross-encoder-duplicate-threshold", type=float, default=0.995)
    parser.add_argument("--cross-encoder-independent-threshold", type=float, default=0.90)
    parser.add_argument("--llm-limit", type=int, default=100)
    parser.add_argument("--llm-workers", type=int, default=DEFAULT_LLM_WORKERS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_API_KEY_FILE)
    parser.add_argument("--api-timeout", type=int, default=60)
    parser.add_argument("--require-api-key", action="store_true")
    parser.add_argument(
        "--reuse-passage-windows",
        action="store_true",
        help="Reuse passage_windows.csv from --output-dir instead of reparsing DITA.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_window_sentences < 1 or args.max_window_sentences > 5:
        raise ValueError("--max-window-sentences must be between 1 and 5")
    if not 0 <= args.cross_encoder_independent_threshold < args.cross_encoder_duplicate_threshold <= 1:
        raise ValueError("CrossEncoder thresholds must satisfy 0 <= independent < duplicate <= 1")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    passage_csv_path = args.output_dir / "passage_windows.csv"
    if args.reuse_passage_windows and passage_csv_path.is_file():
        print(f"Reusing extracted passage windows from {passage_csv_path}...")
        passages_df = pd.read_csv(passage_csv_path, encoding="utf-8-sig", keep_default_na=False)
    else:
        print(f"Extracting passage windows from {args.input}...")
        passages = read_dita_passage_windows(
            args.input,
            max_sentences=args.max_window_sentences,
            min_words=args.min_window_words,
        )
        if len(passages) < 2:
            raise ValueError(f"At least two passage windows are required; extracted {len(passages)}")
        passages_df = pd.DataFrame(asdict(passage) for passage in passages)
        passages_df.to_csv(
            passage_csv_path,
            index=False,
            encoding="utf-8-sig",
            quoting=csv.QUOTE_MINIMAL,
        )
    print(f"Extracted {len(passages_df)} passage windows from {passages_df['source_document_id'].nunique()} articles.")

    embeddings = encode_passages(passages_df, args.embedding_model, args.embedding_batch_size)
    candidates_df = build_candidate_pairs(
        passages_df,
        embeddings,
        threshold=args.embedding_threshold,
        neighbors_per_passage=args.neighbors_per_passage,
        retrieval_batch_size=args.retrieval_batch_size,
        max_candidates=args.max_candidates,
    )
    candidates_df.to_csv(
        args.output_dir / "passage_candidate_pairs.csv",
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_MINIMAL,
    )
    print(f"Retained {len(candidates_df)} candidate pairs for CrossEncoder scoring.")

    scored_df = add_cross_encoder_scores(
        candidates_df,
        model_name=args.cross_encoder_model,
        batch_size=args.cross_encoder_batch_size,
        text_chars=args.cross_encoder_text_chars,
    )
    api_key, api_key_source = resolve_api_key(args.api_key_file)
    if args.require_api_key and not api_key:
        raise RuntimeError(f"An API key is required in {args.api_key_file} or API_KEY/OPENAI_API_KEY.")
    if api_key:
        print(f"Local API key loaded from {api_key_source}; only borderline pairs will use the LLM.")
    results_df = classify_relationships(
        scored_df,
        api_key=api_key,
        model=args.model,
        duplicate_threshold=args.cross_encoder_duplicate_threshold,
        independent_threshold=args.cross_encoder_independent_threshold,
        llm_limit=args.llm_limit,
        llm_workers=args.llm_workers,
        api_timeout=args.api_timeout,
    )
    results_df.to_csv(
        args.output_dir / "passage_deduplication_results.csv",
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_MINIMAL,
    )
    write_summary(args.output_dir, passages_df, candidates_df, results_df, args)
    print(f"Done. Passage-level results were written to {args.output_dir}.")


if __name__ == "__main__":
    main()
