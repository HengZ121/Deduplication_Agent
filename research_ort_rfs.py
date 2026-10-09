"""Reproducible, offline ORT research; does not alter production classifications.

Reuse the repository's DITA resolver and comparison functions. Preserve map
hierarchy, topic provenance, tables, and conref content in reviewable Markdown.
The output is source reconstruction, not a DITA publishing-engine rendering.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from urllib.parse import urlparse

from run_procedure_pipeline import DitaTopicResolver, direct_child, element_text, xml_local_name
from run_passage_pipeline import has_conflict_signal, normalized_passage, token_jaccard

ROOT = Path('unzipped/ort_new_dita/dita').resolve()
OUT = Path('outputs/ort_rfs_research')
RFS = re.compile(r'\bRFS\b|reason for separation', re.I)
csv.field_size_limit(10_000_000)


def write_csv(path, rows):
    if rows:
        with path.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


class SourceReconstructor:
    """Render local source with explicit provenance and fail-visible references."""

    def __init__(self):
        self.resolver = DitaTopicResolver(ROOT)
        self.issues = []
        self.features = Counter()
        self.parents = defaultdict(list)
        self.repairs = []

    def resolve(self, current, reference):
        """Repair only the observed misplaced common-note/table directory.

        Retain language and exact filename, and log every repair. This is an
        explicit export-path repair, not a guess based on similar content.
        """
        target, fragment = self.resolver.resolve_local_reference(current, reference)
        if not target.exists():
            language = current.relative_to(ROOT).parts[0]
            for collection in ('common_notes', 'common_tables'):
                if collection in target.parts:
                    canonical = ROOT / language / collection / target.name
                    if canonical.is_file():
                        self.repairs.append({'source': current.relative_to(ROOT).as_posix(), 'original_reference': reference, 'resolved_target': canonical.relative_to(ROOT).as_posix()})
                        return canonical, fragment
        return target, fragment

    def render(self, element, path, active=frozenset()):
        tag = xml_local_name(element.tag)
        if element.get('conref'):
            reference = element.get('conref')
            target, fragment = self.resolve(path, reference)
            key = (target, fragment)
            if key in active:
                raise ValueError(f'Circular conref: {reference}')
            self.features['expanded_conrefs'] += 1
            try:
                node = self.resolver.find_fragment(self.resolver.parse_xml(target), fragment)
                return self.render(node, target, active | {key})
            except (OSError, ValueError) as exc:
                self.issues.append({'path': str(path.relative_to(ROOT)), 'reference': reference, 'error': str(exc)})
                return f' [UNRESOLVED: {reference}] '
        # Key-based references require publication key scopes; do not guess.
        for attr in ('keyref', 'conkeyref', 'conrefend', 'conaction'):
            if element.get(attr):
                self.issues.append({'path': str(path.relative_to(ROOT)), 'reference': element.get(attr), 'error': f'Unsupported {attr}'})
        if tag in ('prolog', 'related-links'):
            return ''
        content = (element.text or '')
        for child in element:
            content += self.render(child, path, active) + (child.tail or '')
        content = content.strip()
        if tag in ('table', 'simpletable'):
            return '\n\n```text\n' + content + '\n```\n\n'
        if tag in ('row', 'strow', 'sthead'):
            return '\n| ' + re.sub(r'\s+', ' ', content) + '\n'
        if tag in ('entry', 'stentry'):
            return re.sub(r'\s+', ' ', content) + ' | '
        if tag == 'xref':
            href = element.get('href', '')
            if href and not urlparse(href).scheme and not href.startswith('/'):
                href = str((path.parent / href.split('#')[0]).resolve()).replace('\\', '/') + ('#' + href.split('#', 1)[1] if '#' in href else '')
            return f' [{content or "Reference"}]({href}) '
        if tag in ('li', 'step', 'substep'):
            return '\n- ' + content + '\n'
        if tag == 'title':
            return '\n\n**' + content + '**\n\n'
        if tag in ('p', 'cmd', 'info', 'note', 'section', 'ul', 'ol', 'steps', 'shortdesc'):
            return '\n\n' + content + '\n\n'
        return content + ' '

    def document(self, map_path):
        root = self.resolver.parse_xml(map_path)
        title = element_text(direct_child(root, 'title')) or map_path.stem
        topics, parts = [], [f'# {title}', f'Source map: `{map_path.relative_to(ROOT).as_posix()}`']

        def visit(container, current_map, depth, active):
            for ref in container:
                tag = xml_local_name(ref.tag)
                if tag not in ('topicref', 'mapref', 'topichead', 'topicgroup'):
                    continue
                href = ref.get('href', '')
                if href and not urlparse(href).scheme:
                    path, fragment = self.resolve(current_map, href)
                    if path in active:
                        raise ValueError(f'Circular map: {path}')
                    if path.suffix == '.ditamap':
                        visit(self.resolver.parse_xml(path), path, depth, active | {path})
                    else:
                        try:
                            topic = self.resolver.parse_xml(path)
                            if fragment:
                                topic = self.resolver.find_fragment(topic, fragment)
                            rel = path.relative_to(ROOT).as_posix()
                            topics.append(rel)
                            self.parents[rel].append(map_path.relative_to(ROOT).as_posix())
                            heading = element_text(direct_child(topic, 'title')) or path.stem
                            parts.extend(['#' * min(depth + 2, 6) + ' ' + heading, f'Source topic: `{rel}`'])
                            for child in topic:
                                if xml_local_name(child.tag) not in ('title', 'prolog'):
                                    parts.append(self.render(child, path))
                        except (OSError, ValueError) as exc:
                            self.issues.append({'path': str(current_map.relative_to(ROOT)), 'reference': href, 'error': str(exc)})
                            parts.append(f'UNRESOLVED TOPIC: {href}')
                visit(ref, current_map, depth + 1, active)

        visit(root, map_path, 0, frozenset({map_path}))
        return title, topics, re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', '\n\n'.join(parts))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with Path('outputs/ort_all_duplicate_cluster_files.csv').open(encoding='utf-8-sig') as f:
        first = [row for _, row in zip(range(3), csv.DictReader(f))]
    focus_paths = {r['file_path'] for r in first}
    recon = SourceReconstructor()
    documents, inventory = {}, []
    # Use the exact English branch underlying the saved pipeline, not the
    # parallel en/ tree or older ort_dita_extracted export.
    resume = '--resume-reconstruction' in sys.argv
    if resume:
        with (OUT / 'document_inventory.csv').open(encoding='utf-8-sig') as f:
            inventory = list(csv.DictReader(f))
        for row in inventory:
            text = Path(row['restored_file']).read_text(encoding='utf-8')
            topics = re.findall(r'Source topic: `([^`]+)`', text)
            documents[row['map_path']] = {'title': row['title'], 'topics': topics, 'text': text}
            row['rfs_related'] = row['rfs_related'] == 'True'
            for topic in topics:
                recon.parents[topic].append(row['map_path'])
        if (OUT / 'reconstruction_issues.csv').exists():
            with (OUT / 'reconstruction_issues.csv').open(encoding='utf-8-sig') as f:
                recon.issues = list(csv.DictReader(f))
    for map_path in ([] if resume else sorted((ROOT / 'en_EN').rglob('*.ditamap'))):
        title, topics, text = recon.document(map_path)
        if not RFS.search(text) and not focus_paths.intersection(topics):
            continue
        rel = map_path.relative_to(ROOT).as_posix()
        output = OUT / 'documents' / Path(rel).with_suffix('.md')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + '\n', encoding='utf-8')
        documents[rel] = {'title': title, 'topics': topics, 'text': text}
        inventory.append({'map_path': rel, 'title': title, 'rfs_related': bool(RFS.search(text)), 'topic_count': len(topics), 'words_in_reconstruction': len(text.split()), 'restored_file': output.as_posix()})
    write_csv(OUT / 'document_inventory.csv', inventory)
    write_csv(OUT / 'reconstruction_issues.csv', recon.issues)

    with Path('outputs/ort_kmt_cross_deduplication/en/cross_nodes.csv').open(encoding='utf-8-sig') as f:
        nodes = {r['node_id']: r for r in csv.DictReader(f) if r['node_id'].startswith('ORT:')}
    first_ids = {r['node_id'] for r in first}
    rfs_nodes = {k for k, v in nodes.items() if RFS.search(v['text'] + ' ' + v['article_title'])}
    selected, rfs_pairs, stats = [], [], Counter()
    for row in first:
        row['parent_maps'] = ' | '.join(recon.parents[row['file_path']])
    write_csv(OUT / 'first_three_rows.csv', first)
    with Path('outputs/ort_internal_deduplication/en/pair_classifications.csv').open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            a, b = row['item1_node_id'], row['item2_node_id']
            is_focus = a in first_ids and b in first_ids
            is_rfs = a in rfs_nodes and b in rfs_nodes
            if not (is_focus or is_rfs):
                continue
            left, right = nodes[a], nodes[b]
            row.update({'item1_path': left['article_path'], 'item2_path': right['article_path'], 'lexical_jaccard': token_jaccard(left['text'], right['text']), 'conflict_signal': has_conflict_signal(left['text'], right['text']), 'normalized_equal': normalized_passage(left['text']) == normalized_passage(right['text']), 'item1_text': left['text'], 'item2_text': right['text']})
            if is_focus:
                selected.append(row.copy())
            if is_rfs:
                rfs_pairs.append(row)
                stats[row['final_relationship_type']] += 1
    write_csv(OUT / 'first_three_pair_evidence.csv', selected)
    write_csv(OUT / 'rfs_pair_evidence.csv', rfs_pairs)

    # Quantify omitted referenced material for every topic in reconstructed
    # RFS maps, using the same resolver as the existing document reader.
    expansion = []
    all_topics = sorted({p for d in documents.values() for p in d['topics']})
    for rel in all_topics:
        path = ROOT / rel
        root = recon.resolver.parse_xml(path)
        body = next((c for c in root if xml_local_name(c.tag).endswith('body')), None)
        if body is None:
            continue
        refs = [e.get('conref') for e in body.iter() if e.get('conref')]
        if not refs:
            continue
        try:
            raw = element_text(body)
            expanded = recon.resolver.expanded_element_text(body, path)
            expansion.append({'topic_path': rel, 'raw_words': len(raw.split()), 'expanded_words': len(expanded.split()), 'added_words': len(expanded.split()) - len(raw.split()), 'conrefs': ' | '.join(refs), 'expanded_text': expanded})
        except (OSError, ValueError):
            pass  # Already recorded by the source reconstruction above.
    write_csv(OUT / 'conref_expansion_evidence.csv', expansion)

    # Small interpretable full-document comparison: RFS action variants.
    family = {k: v for k, v in documents.items() if k.split('/')[-2] in {'roe_quit', 'roe_dismissal', 'roe_loa', 'roe_other', 'roe_retirement', 'roe_rts', 'adj_rfs_review_b_other', 'adj_rfs_review_k_other', 'adj_rfs_review_man_ret'}}
    comparisons = []
    for (a, da), (b, db) in combinations(family.items(), 2):
        ta = [recon.resolver.read_topic(ROOT / p)[1] for p in da['topics']]
        tb = [recon.resolver.read_topic(ROOT / p)[1] for p in db['topics']]
        na, nb = set(map(normalized_passage, ta)), set(map(normalized_passage, tb))
        shared = na & nb
        comparisons.append({'map1': a, 'map2': b, 'title1': da['title'], 'title2': db['title'], 'expanded_document_token_jaccard': token_jaccard(' '.join(ta), ' '.join(tb)), 'unique_sections1': len(na), 'unique_sections2': len(nb), 'exact_shared_sections': len(shared), 'exact_section_coverage1': len(shared) / len(na), 'exact_section_coverage2': len(shared) / len(nb), 'full_normalized_equal': normalized_passage(' '.join(ta)) == normalized_passage(' '.join(tb))})
    write_csv(OUT / 'rfs_document_comparison.csv', comparisons)
    summary = {'english_maps_scanned': len(list((ROOT / 'en_EN').rglob('*.ditamap'))), 'restored_documents': len(inventory), 'rfs_documents': sum(r['rfs_related'] for r in inventory), 'rfs_body_nodes': len(rfs_nodes), 'saved_rfs_pair_classifications': dict(stats), 'first_three_direct_pair_count': len(selected), 'referenced_topics_with_conrefs': len(expansion), 'added_conref_words': sum(r['added_words'] for r in expansion), 'reconstruction_issues_entire_english_scan': len(recon.issues), 'features_entire_english_scan': None if resume else dict(recon.features)}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    print(json.dumps([{k: r[k] for k in ('item1_path', 'item2_path', 'embedding_similarity', 'cross_encoder_score', 'lexical_jaccard', 'conflict_signal', 'final_relationship_type')} for r in selected], indent=2))


if __name__ == '__main__':
    main()
