"""Build within-dataset duplicate clusters from saved pair classifications.

This reuses the KMT/ORT language-level KG results; it does not rerun embedding,
CrossEncoder scoring, or LLM review. Duplicate edges are grouped into connected
components, matching the historical ORT internal-cluster rule.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def cluster_dataset(dataset: str, language: str, run_dir: Path) -> pd.DataFrame:
    """Return cluster membership rows for one saved language run."""
    nodes = pd.read_csv(run_dir / "kg_nodes.csv", encoding="utf-8-sig", keep_default_na=False)
    pairs = pd.read_csv(run_dir / "kg_pair_classifications.csv", encoding="utf-8-sig", keep_default_na=False)

    # Initialize every source topic so that cluster membership is built only
    # from edges available to this run, while singleton nodes remain excluded.
    parent = {str(node_id): str(node_id) for node_id in nodes.node_id}

    def find(node_id: str) -> str:
        while parent[node_id] != node_id:
            parent[node_id] = parent[parent[node_id]]
            node_id = parent[node_id]
        return node_id

    # Partial inclusion is not a duplicate cluster: it can describe different
    # lengths or scope. Only pairs classified as semantic duplicates connect.
    duplicate_pairs = pairs.loc[
        pairs.final_relationship_type.eq("duplicate/semantic duplicate"),
        ["item1_node_id", "item2_node_id"],
    ]
    for left, right in duplicate_pairs.itertuples(index=False, name=None):
        left, right = str(left), str(right)
        if left not in parent or right not in parent:
            continue
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    groups: dict[str, list[str]] = {}
    for node_id in parent:
        groups.setdefault(find(node_id), []).append(node_id)

    nodes_by_id = nodes.set_index("node_id", drop=False)
    rows: list[dict[str, object]] = []
    for root, members in groups.items():
        if len(members) < 2:
            continue
        cluster_id = f"{dataset}_{language}_cluster_{root}"
        for node_id in members:
            node = nodes_by_id.loc[node_id]
            rows.append(
                {
                    "dataset": dataset,
                    "subset": language,
                    "cluster_id": cluster_id,
                    "cluster_size": len(members),
                    "node_id": node_id,
                    "file_path": node.get("article_path", ""),
                    "language": node.get("language", language),
                    "source_element_path": node.get("source_element_path", ""),
                    "file_content": node.get("text", ""),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kmt-dir",
        type=Path,
        default=Path("outputs/kmt_2026-10-07_body_{lang}_kg_pipeline"),
        help="KMT run directory template; {lang} is replaced with en or fr.",
    )
    parser.add_argument(
        "--ort-dir",
        type=Path,
        default=Path("outputs/ort_2026-10-07_body_{lang}_kg_pipeline"),
        help="ORT run directory template; {lang} is replaced with en or fr.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/internal_clusters_2026-10-07"),
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for dataset, template in (("KMT", args.kmt_dir), ("ORT", args.ort_dir)):
        language_memberships = []
        for language in ("en", "fr"):
            run_dir = Path(str(template).format(lang=language))
            membership = cluster_dataset(dataset, language, run_dir)
            language_memberships.append(membership)
            cluster_count = membership.cluster_id.nunique() if not membership.empty else 0
            print(
                f"{dataset} {language}: {len(membership):,} clustered nodes "
                f"in {cluster_count:,} clusters"
            )
        result = pd.concat(language_memberships, ignore_index=True)
        result.to_csv(
            args.output_dir / f"{dataset.lower()}_all_duplicate_cluster_files.csv",
            index=False,
            encoding="utf-8-sig",
        )


if __name__ == "__main__":
    main()
