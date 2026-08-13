#!/usr/bin/env python3
"""Rank FrameNet pairs that may be interchangeable in the procedure corpus.

The input contains lexical candidate frames, not gold semantic annotations.
Accordingly, this analysis requires four kinds of evidence before recommending
consolidation: repeated co-occurrence, balanced sentence overlap, the same
lexical trigger, and semantic similarity between official FrameNet records.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer

from find_multi_frame_sentences import match_candidate_frames
from count_framenet_candidates import build_lu_index
from framenet_registry import _plain_definition, registry
from framenet_mapper import EXPOSITORY_RULES
from hybrid_frame_mapper import FRAME_RULES


DEFAULT_INPUT = Path("outputs") / "procedure_sentences_with_multiple_frames.csv"
DEFAULT_OUTPUT = (
    Path("outputs")
    / "019ff91b-7d05-7643-8f3b-9fe2b738766a"
    / "frame_exchangeability_analysis.json"
)
MIN_PAIR_OCCURRENCES = 10


def parse_frame_names(value: str) -> tuple[str, ...]:
    """Parse the report's ordered, semicolon-delimited frame-name field."""
    return tuple(frame.strip() for frame in value.split(";") if frame.strip())


def official_frame_metadata(frame_names: set[str]) -> dict[str, dict[str, Any]]:
    """Load compact semantic metadata for every frame represented in the CSV."""
    metadata: dict[str, dict[str, Any]] = {}
    for name in sorted(frame_names):
        frame = registry._fn.frame(name)
        lexical_units = sorted(frame.lexUnit.keys())
        lemmas = {
            re.sub(r"\s*\[[^]]+\]$", "", lexical_unit.rpartition(".")[0]).lower()
            for lexical_unit in lexical_units
        }
        relations = []
        for relation in frame.frameRelations:
            relations.append(
                {
                    "type": relation.type.name,
                    "superFrame": relation.superFrameName,
                    "subFrame": relation.subFrameName,
                }
            )
        metadata[name] = {
            "frameId": frame.ID,
            "definition": _plain_definition(frame.definition),
            "lexicalUnits": lexical_units,
            "lemmas": lemmas,
            "relations": relations,
        }
    return metadata


def direct_relations(
    frame_a: str,
    frame_b: str,
    metadata: dict[str, dict[str, Any]],
) -> list[str]:
    """Return official direct relation types connecting a pair in either direction."""
    relation_types = {
        relation["type"]
        for relation in metadata[frame_a]["relations"]
        if {relation["superFrame"], relation["subFrame"]} == {frame_a, frame_b}
    }
    relation_types.update(
        relation["type"]
        for relation in metadata[frame_b]["relations"]
        if {relation["superFrame"], relation["subFrame"]} == {frame_a, frame_b}
    )
    return sorted(relation_types)


def semantic_similarity_context(
    metadata: dict[str, dict[str, Any]],
) -> tuple[dict[str, int], Any]:
    """Create normalized TF-IDF vectors from names, definitions, and LU lemmas."""
    names = sorted(metadata)
    documents = []
    for name in names:
        details = metadata[name]
        readable_name = name.replace("_", " ")
        # Repeat the official definition once so generic LU lists cannot drown
        # out the semantic description for frames with many lexical units.
        definition = details["definition"]
        documents.append(
            f"{readable_name}. {definition} {definition} "
            + " ".join(sorted(details["lemmas"]))
        )
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    vectors = vectorizer.fit_transform(documents)
    return {name: index for index, name in enumerate(names)}, vectors


def classify_pair(
    score: float,
    occurrences: int,
    overlap: float,
    jaccard: float,
    same_trigger_rate: float,
    semantic_similarity: float,
    relations: list[str],
) -> tuple[str, str]:
    """Apply conservative, auditable exchangeability thresholds."""
    if (
        occurrences >= 20
        and overlap >= 0.55
        and jaccard >= 0.30
        and same_trigger_rate >= 0.70
        and semantic_similarity >= 0.35
        and score >= 0.58
    ):
        return (
            "High-priority review",
            "High balanced overlap, mostly the same lexical trigger, and similar FrameNet semantics.",
        )
    if (
        occurrences >= 15
        and overlap >= 0.35
        and same_trigger_rate >= 0.55
        and semantic_similarity >= 0.25
        and score >= 0.46
    ):
        return (
            "Secondary review",
            "Material overlap and shared-trigger evidence; manual domain review is still required.",
        )
    if relations and semantic_similarity >= 0.25:
        return (
            "Related but distinct",
            "FrameNet links the frames, but corpus overlap or trigger evidence is too weak for substitution.",
        )
    return (
        "Not exchangeable",
        "Co-occurrence is better explained by different triggers, weak overlap, or dissimilar semantics.",
    )


def analyze(input_path: Path, output_path: Path) -> dict[str, Any]:
    lu_index = build_lu_index()
    sentences: list[dict[str, Any]] = []
    frame_frequency: Counter[str] = Counter()
    pair_frequency: Counter[tuple[str, str]] = Counter()
    shared_trigger_frequency: Counter[tuple[str, str]] = Counter()
    frame_names: set[str] = set()
    frame_mismatch_count = 0

    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        for source_row in csv.DictReader(handle):
            sentence = source_row["sentence"]
            expected_frames = parse_frame_names(source_row["frames"])
            matches = match_candidate_frames(sentence, lu_index)
            forms_by_frame = {
                match["frame"]: set(match["matchedForms"])
                for match in matches
            }
            if set(expected_frames) != set(forms_by_frame):
                frame_mismatch_count += 1
            frames = tuple(sorted(set(expected_frames)))
            frame_names.update(frames)
            frame_frequency.update(frames)
            for pair in combinations(frames, 2):
                pair_frequency[pair] += 1
                if forms_by_frame.get(pair[0], set()) & forms_by_frame.get(pair[1], set()):
                    shared_trigger_frequency[pair] += 1
            sentences.append(
                {
                    "sentence": sentence,
                    "frames": frames,
                    "formsByFrame": forms_by_frame,
                    "occurrenceCount": int(source_row["occurrenceCount"]),
                    "sourceDocuments": source_row["sourceDocuments"],
                }
            )

    metadata = official_frame_metadata(frame_names)
    vector_positions, semantic_vectors = semantic_similarity_context(metadata)
    domain_frames = {rule.frame for rule in FRAME_RULES}
    domain_frames.update(
        rule["frame"] for rule in EXPOSITORY_RULES if rule.get("frame")
    )

    ranked_pairs: list[dict[str, Any]] = []
    for pair, occurrences in pair_frequency.items():
        if occurrences < MIN_PAIR_OCCURRENCES:
            continue
        frame_a, frame_b = pair
        frequency_a = frame_frequency[frame_a]
        frequency_b = frame_frequency[frame_b]
        conditional_b_given_a = occurrences / frequency_a
        conditional_a_given_b = occurrences / frequency_b
        overlap = occurrences / min(frequency_a, frequency_b)
        jaccard = occurrences / (frequency_a + frequency_b - occurrences)
        same_trigger_rate = shared_trigger_frequency[pair] / occurrences

        position_a = vector_positions[frame_a]
        position_b = vector_positions[frame_b]
        definition_similarity = float(
            semantic_vectors[position_a].multiply(semantic_vectors[position_b]).sum()
        )
        lemmas_a = metadata[frame_a]["lemmas"]
        lemmas_b = metadata[frame_b]["lemmas"]
        lu_union = lemmas_a | lemmas_b
        lu_jaccard = len(lemmas_a & lemmas_b) / len(lu_union) if lu_union else 0.0
        semantic_similarity = 0.7 * definition_similarity + 0.3 * lu_jaccard
        relations = direct_relations(frame_a, frame_b, metadata)
        support_strength = min(1.0, math.log1p(occurrences) / math.log1p(100))
        score = (
            0.25 * overlap
            + 0.20 * jaccard
            + 0.25 * same_trigger_rate
            + 0.25 * semantic_similarity
            + 0.05 * support_strength
        )
        recommendation, rationale = classify_pair(
            score,
            occurrences,
            overlap,
            jaccard,
            same_trigger_rate,
            semantic_similarity,
            relations,
        )
        ranked_pairs.append(
            {
                "recommendation": recommendation,
                "score": round(score, 4),
                "frameA": frame_a,
                "frameB": frame_b,
                "frameAId": metadata[frame_a]["frameId"],
                "frameBId": metadata[frame_b]["frameId"],
                "cooccurrenceSentences": occurrences,
                "frameAFrequency": frequency_a,
                "frameBFrequency": frequency_b,
                "pBGivenA": round(conditional_b_given_a, 4),
                "pAGivenB": round(conditional_a_given_b, 4),
                "overlapCoefficient": round(overlap, 4),
                "jaccard": round(jaccard, 4),
                "sharedTriggerSentences": shared_trigger_frequency[pair],
                "sharedTriggerRate": round(same_trigger_rate, 4),
                "definitionSimilarity": round(definition_similarity, 4),
                "lexicalUnitJaccard": round(lu_jaccard, 4),
                "semanticSimilarity": round(semantic_similarity, 4),
                "directFrameNetRelations": "; ".join(relations),
                "domainFrameA": frame_a in domain_frames,
                "domainFrameB": frame_b in domain_frames,
                "rationale": rationale,
                "sharedForms": [],
                "examples": [],
            }
        )

    class_order = {
        "High-priority review": 0,
        "Secondary review": 1,
        "Related but distinct": 2,
        "Not exchangeable": 3,
    }
    ranked_pairs.sort(
        key=lambda row: (
            class_order[row["recommendation"]],
            -row["score"],
            -row["cooccurrenceSentences"],
            row["frameA"],
            row["frameB"],
        )
    )

    # Capture audit evidence only for the rows that will be surfaced in the
    # workbook.  This avoids retaining examples for millions of incidental
    # pairs while still making every recommendation easy to inspect.
    surfaced_candidates = [
        row
        for row in ranked_pairs
        if row["recommendation"] != "Not exchangeable"
    ][:500]
    domain_candidates = sorted(
        (
            row
            for row in ranked_pairs
            if row["domainFrameA"] or row["domainFrameB"]
        ),
        key=lambda row: (-row["score"], -row["cooccurrenceSentences"]),
    )[:100]
    surfaced = list(surfaced_candidates)
    surfaced_keys = {(row["frameA"], row["frameB"]) for row in surfaced}
    surfaced.extend(
        row
        for row in domain_candidates
        if (row["frameA"], row["frameB"]) not in surfaced_keys
    )
    surfaced_by_pair = {
        (row["frameA"], row["frameB"]): row
        for row in surfaced
    }
    shared_forms: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for sentence_record in sentences:
        present_surfaced_pairs = {
            pair
            for pair in combinations(sentence_record["frames"], 2)
            if pair in surfaced_by_pair
        }
        for pair in present_surfaced_pairs:
            row = surfaced_by_pair[pair]
            common_forms = (
                sentence_record["formsByFrame"].get(pair[0], set())
                & sentence_record["formsByFrame"].get(pair[1], set())
            )
            shared_forms[pair].update(common_forms)
            if len(row["examples"]) < 3 and common_forms:
                row["examples"].append(
                    {
                        "sentence": sentence_record["sentence"],
                        "sharedForms": sorted(common_forms),
                        "occurrenceCount": sentence_record["occurrenceCount"],
                        "sourceDocuments": sentence_record["sourceDocuments"],
                    }
                )
    for pair, row in surfaced_by_pair.items():
        row["sharedForms"] = [
            form for form, _count in shared_forms[pair].most_common(10)
        ]

    recommendation_counts = Counter(row["recommendation"] for row in ranked_pairs)
    frame_rows = [
        {
            "frame": name,
            "frameId": metadata[name]["frameId"],
            "sentenceFrequency": frequency,
            "sentenceShare": round(frequency / len(sentences), 4),
            "domainFrame": name in domain_frames,
            "definition": metadata[name]["definition"],
        }
        for name, frequency in frame_frequency.most_common()
    ]
    payload = {
        "summary": {
            "input": str(input_path),
            "analyzedSentences": len(sentences),
            "distinctFrames": len(frame_frequency),
            "pairsWithAtLeast10Cooccurrences": len(ranked_pairs),
            "highPriorityReviewPairs": recommendation_counts["High-priority review"],
            "secondaryReviewPairs": recommendation_counts["Secondary review"],
            "relatedButDistinctPairs": recommendation_counts["Related but distinct"],
            "frameSetMismatchRows": frame_mismatch_count,
            "methodNote": (
                "Candidate ranking combines overlap coefficient (25%), Jaccard (20%), "
                "same-trigger rate (25%), FrameNet semantic similarity (25%), and "
                "sample-strength (5%). Recommendations are lexical-corpus evidence, "
                "not automatic permission to merge FrameNet frames."
            ),
        },
        "candidatePairs": surfaced_candidates,
        "domainCandidatePairs": domain_candidates,
        "frameFrequency": frame_rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload["summary"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(analyze(args.input, args.output), indent=2))


if __name__ == "__main__":
    main()
