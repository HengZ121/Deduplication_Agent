"""Rebuild the KMT cluster word-count report without the EN run's ``fr/`` copies.

The 2026-10-07 EN body run selected topics by any ``*_EN`` folder, so it also
loaded ``fr/KA-*_EN/`` article topics (byte-identical copies of the English
files). This drops those nodes and every pair touching them, re-forms EN
clusters as connected components of the saved cluster-forming pairs, and reruns the existing report. No model inference is performed; FR rows
are unchanged.

Limitation: candidate retrieval kept 20 neighbours per node, so a removed copy
may have displaced one English candidate pair that a fresh run would score.
"""
from pathlib import Path
import argparse
import sys
import zipfile

import numpy as np
import pandas as pd

import analyze_cluster_word_counts as report
from run_passage_pipeline import is_cluster_relationship

ROOT = Path('outputs')
PUBLISHED = ROOT / 'cluster_word_counts_2026-10-07' / 'node_membership_word_counts.csv'
EN_RESULTS = ROOT / 'kmt_2026-10-07_body_en_kg_pipeline' / 'kmt_english_llm_results.zip'


def components(node_ids, edges):
    parent = {node: node for node in node_ids}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for a, b in edges:
        if a in parent and b in parent:
            parent[find(a)] = find(b)
    groups = {}
    for node in node_ids:
        groups.setdefault(find(node), []).append(node)
    return [sorted(group) for group in groups.values() if len(group) > 1]


def en_clusters(node_ids):
    with zipfile.ZipFile(EN_RESULTS) as archive, archive.open('kg_pair_classifications.csv') as stream:
        pairs = pd.read_csv(stream, encoding='utf-8-sig',
                            usecols=['item1_node_id', 'item2_node_id', 'final_relationship_type'])
    duplicates = pairs[pairs.final_relationship_type.map(is_cluster_relationship)]
    return components(node_ids, zip(duplicates.item1_node_id, duplicates.item2_node_id))


def read_nodes():
    nodes = pd.read_csv(PUBLISHED, keep_default_na=False, encoding='utf-8-sig')
    nodes['clustered'] = nodes.clustered.astype(str).str.lower().eq('true')
    nodes['eligible'] = nodes.eligible.astype(str).str.lower().eq('true')
    en = nodes.subset.eq('en')

    # Guard: the published EN clusters must be reproducible from the saved pairs.
    published = set(nodes[en & nodes.clustered].groupby('cluster_id').node_id.apply(frozenset))
    assert set(map(frozenset, en_clusters(list(nodes.loc[en, 'node_id'])))) == published

    copies = en & nodes.article_path.str.replace('\\', '/', regex=False).str.startswith('fr/')
    nodes = nodes[~copies].copy()
    en = nodes.subset.eq('en')
    cluster_of = {node: f'KMT_en_cluster_{members[0]}'
                  for members in en_clusters(list(nodes.loc[en, 'node_id'])) for node in members}
    nodes.loc[en, 'cluster_id'] = nodes.loc[en, 'node_id'].map(cluster_of).fillna('')
    nodes.loc[en, 'clustered'] = nodes.loc[en, 'cluster_id'].ne('')
    nodes['item_id'] = np.where(nodes.clustered, 'cluster:' + nodes.cluster_id, 'singleton:' + nodes.node_id)
    nodes['aggregate_text_mismatch'] = False
    print(f'Removed {int(copies.sum()):,} EN-run nodes loaded from fr/ copies.')
    return nodes.reset_index(drop=True), [PUBLISHED, EN_RESULTS]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'cluster_word_counts_2026-10-13_en_without_fr_copies')
    output_dir = parser.parse_args().output_dir
    report.read_nodes = read_nodes
    sys.argv = [sys.argv[0], '--output-dir', str(output_dir)]
    report.main()
    note = ('\n\n## Correction applied (2026-10-13)\n\n'
            'The EN run originally also loaded `fr/KA-*_EN/` topics, which are byte-identical copies of the '
            'English files, so many EN "clusters" were an English topic paired with its own copy. Those nodes '
            'and their pairs are removed here and EN clusters are re-formed from the saved decisions. FR rows are '
            'unchanged, but the KMT `fr` DITA export itself contains English text, so FR results do not '
            'describe French content until the export is regenerated.\n')
    with (output_dir / 'REPORT.md').open('a', encoding='utf-8') as stream:
        stream.write(note)


if __name__ == '__main__':
    main()
