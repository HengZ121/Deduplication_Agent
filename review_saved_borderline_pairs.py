"""LLM-review every saved borderline pair without rerunning retrieval/scoring.

Results are appended to per-run JSONL checkpoints as calls finish, so an
interrupted run can be resumed by invoking this script again.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from run_kg_pipeline import (
    LLM_REVIEW_CHECKPOINT_NAME,
    detailed_matches,
    review_borderline_pairs,
)
from run_procedure_pipeline import DEFAULT_API_KEY_FILE, DEFAULT_LLM_WORKERS, DEFAULT_MODEL, resolve_api_key


ROOT = Path("outputs")
WITHIN_RUNS = [
    ROOT / f"{dataset}_2026-10-07_body_{lang}_kg_pipeline"
    for dataset in ("kmt", "ort")
    for lang in ("en", "fr")
]
CROSS_RUNS = [ROOT / "ort_kmt_cross_2026-10-07_deduplication" / lang for lang in ("en", "fr")]


def read_comparable_nodes(nodes_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes = pd.read_csv(nodes_path, encoding="utf-8-sig", keep_default_na=False)
    comparable = nodes.loc[
        nodes["is_comparable"].astype(str).str.lower().eq("true")
    ].reset_index(drop=True)
    return nodes, comparable


def persist_review(run_dir: Path, *, cross_source: bool, api_key: str, model: str, workers: int, timeout: int) -> dict[str, object]:
    nodes_path = run_dir / ("cross_nodes.csv" if cross_source else "kg_nodes.csv")
    result_path = run_dir / ("cross_pair_classifications.csv" if cross_source else "kg_pair_classifications.csv")
    nodes, comparable = read_comparable_nodes(nodes_path)
    results = pd.read_csv(result_path, encoding="utf-8-sig", keep_default_na=False)
    borderline_count = int(results["is_borderline"].astype(str).str.lower().eq("true").sum())
    checkpoint = run_dir / ("cross_llm_reviews.jsonl" if cross_source else LLM_REVIEW_CHECKPOINT_NAME)
    print(f"{run_dir}: reviewing up to {borderline_count:,} borderline pairs with model {model}.", flush=True)
    reviewed = review_borderline_pairs(
        results,
        comparable,
        api_key,
        model,
        len(results),  # Maximum effective limit: every borderline row in this run.
        workers,
        timeout,
        checkpoint_path=checkpoint,
    )
    reviewed.to_csv(result_path, index=False, encoding="utf-8-sig")
    match_name = "cross_deduplication_matches.csv" if cross_source else "kg_deduplication_matches.csv"
    detailed_matches(reviewed, comparable).to_csv(
        run_dir / match_name, index=False, encoding="utf-8-sig"
    )
    counts = reviewed["llm_review_status"].value_counts().to_dict()
    relationships = reviewed["final_relationship_type"].value_counts().to_dict()
    summary: dict[str, object] = {
        "model": model,
        "pair_count": len(reviewed),
        "borderline_pair_count": borderline_count,
        "llm_review_status_counts": counts,
        "final_relationship_counts": relationships,
    }
    if not cross_source:
        old = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
        old["relationship_counts"] = relationships
        old["llm_reviewed_pair_count"] = int(counts.get("reviewed", 0))
        old["llm_api_error_pair_count"] = int(counts.get("api_error", 0))
        old["llm_not_reviewed_pair_count"] = int(counts.get("not_reviewed", 0))
        old["llm_model"] = model
        (run_dir / "run_summary.json").write_text(json.dumps(old, indent=2), encoding="utf-8")
    (run_dir / "llm_review_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"{run_dir}: {counts}; relationships={relationships}", flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_API_KEY_FILE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=DEFAULT_LLM_WORKERS)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--dataset", choices=("all", "kmt", "ort"), default="all")
    parser.add_argument("--skip-cross-source", action="store_true")
    args = parser.parse_args()
    api_key, source = resolve_api_key(args.api_key_file)
    if not api_key:
        raise SystemExit(f"No API key is configured (checked {args.api_key_file} and environment variables).")
    print(f"API key is configured via {source}; key value is not displayed.", flush=True)

    # Probe one pair first. If account access, quota, or model availability is
    # broken, stop before submitting hundreds of thousands of requests.
    first_dir = next((d for d in WITHIN_RUNS if (d / "kg_pair_classifications.csv").is_file()), None)
    if first_dir is None:
        raise SystemExit("No refreshed within-source classification output was found.")
    nodes, comparable = read_comparable_nodes(first_dir / "kg_nodes.csv")
    first_result_path = first_dir / "kg_pair_classifications.csv"
    first_results = pd.read_csv(first_result_path, encoding="utf-8-sig", keep_default_na=False)
    if first_results.llm_review_status.astype(str).eq("reviewed").any():
        print("LLM reviews already exist; resuming from checkpoints.", flush=True)
    else:
        probe = review_borderline_pairs(
            first_results, comparable, api_key, args.model, 1, 1, args.timeout,
            checkpoint_path=first_dir / LLM_REVIEW_CHECKPOINT_NAME,
        )
        if not probe.llm_review_status.astype(str).eq("reviewed").any():
            raise SystemExit("LLM preflight did not produce a successful review; no bulk requests were started.")
        probe.to_csv(first_result_path, index=False, encoding="utf-8-sig")

    runs = [
        run_dir
        for run_dir in WITHIN_RUNS
        if args.dataset == "all" or run_dir.name.startswith(f"{args.dataset}_")
    ]
    # Cross-source reviews require both KMT and ORT, so they are only included
    # when the user requests all datasets.
    if args.dataset == "all" and not args.skip_cross_source:
        runs += CROSS_RUNS
    for run_dir in runs:
        cross_source = run_dir in CROSS_RUNS
        persist_review(
            run_dir,
            cross_source=cross_source,
            api_key=api_key,
            model=args.model,
            workers=max(1, args.workers),
            timeout=args.timeout,
        )


if __name__ == "__main__":
    main()
