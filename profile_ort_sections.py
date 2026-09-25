"""Offline audit of existing ORT section units and task/activity provenance.

No re-chunking, model inference, or production-output changes. Business document
type comes from the source path; XML topic type is audited as a separate field.
"""
from __future__ import annotations

import csv
import json
import posixpath
import statistics
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path('unzipped/ort_new_dita/dita')
OUT = Path('outputs/ort_section_strategy')
csv.field_size_limit(10_000_000)


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


def write_csv(name, rows):
    if not rows:
        return
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def business_type(path):
    parts = path.split('/')
    return parts[1] if len(parts) > 1 else ''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    nodes = list(read_csv('outputs/ort_new_dita_kg_pipeline/en/kg_nodes.csv'))
    by_path = {r['article_path']: r for r in nodes}
    by_id = {'ORT:' + r['node_id']: r for r in nodes}
    maps, sections, membership = [], [], defaultdict(list)
    headings = Counter()
    title_cache = {}
    title_root_type = Counter()
    category_maps = Counter()
    for path in sorted((ROOT / 'en_EN').rglob('*.ditamap')):
        relative = path.relative_to(ROOT).as_posix()
        category = business_type(relative)
        category_maps[category] += 1
        if category not in ('task', 'activity'):
            continue
        root = ET.parse(path).getroot()
        title = ' '.join(root.findtext('title', '').split())
        top_heads = []
        count = 0
        missing = 0
        def visit(parent, ancestors):
            nonlocal count, missing
            for ref in parent:
                if ref.tag != 'topicref':
                    continue
                href = ref.get('href', '')
                if not href or urlsplit(href).scheme:
                    continue
                target = posixpath.normpath(posixpath.join(posixpath.dirname(relative), unquote(href.split('#')[0])))
                if target not in title_cache:
                    if (ROOT / target).is_file():
                        topic = ET.parse(ROOT / target).getroot()
                        title_cache[target] = (' '.join(topic.findtext('title', '').split()), topic.tag)
                    else:
                        title_cache[target] = ('[missing target]', '')
                section_title, topic_type = title_cache[target]
                if not ancestors:
                    top_heads.append(section_title)
                    headings[(category, section_title)] += 1
                count += 1
                body = by_path.get(target)
                if not topic_type:
                    missing += 1
                row = {'document_map': relative, 'document_title': title, 'business_document_type': category, 'section_path': target, 'section_title': section_title, 'ancestor_headings': ' > '.join(ancestors), 'xml_topic_type': topic_type, 'body_in_pipeline': body is not None, 'body_words': body['word_count'] if body else '', 'external_to_document_directory': posixpath.dirname(target) != posixpath.dirname(relative)}
                sections.append(row)
                membership[target].append(row)
                visit(ref, ancestors + [section_title])
        visit(root, [])
        maps.append({'map_path': relative, 'business_document_type': category, 'title': title, 'topic_occurrences': count, 'missing_targets': missing, 'top_level_headings': ' | '.join(top_heads), 'has_map_othermeta': any(e.tag == 'othermeta' for e in root.iter())})

    for n in nodes:
        title_root_type[(business_type(n['article_path']), n['document_type'])] += 1
    write_csv('publication_inventory.csv', maps)
    write_csv('section_context_inventory.csv', sections)
    write_csv('top_level_headings.csv', [{'business_document_type': k[0], 'heading': k[1], 'map_occurrences': v} for k, v in headings.most_common()])
    write_csv('business_vs_xml_type.csv', [{'business_document_type': k[0], 'xml_type_in_document_type_column': k[1], 'body_nodes': v} for k, v in sorted(title_root_type.items())])
    additional = {
        'sections_over_1200_body_characters': dict(Counter(business_type(n['article_path']) for n in nodes if business_type(n['article_path']) in ('activity', 'task') and len(n['text']) > 1200)),
        'task_maps_without_step_by_step': [m['map_path'] for m in maps if m['business_document_type'] == 'task' and 'Step by step' not in m['top_level_headings']],
        'common_note_occurrences': sum('/common_notes/' in s['section_path'] for s in sections),
        'distinct_common_note_targets': len({s['section_path'] for s in sections if '/common_notes/' in s['section_path']}),
    }
    (OUT / 'additional_observations.json').write_text(json.dumps(additional, indent=2), encoding='utf-8')

    pairs = Counter()
    example_candidates = []
    same_document = 0
    for r in read_csv('outputs/ort_internal_deduplication/en/pair_classifications.csv'):
        if r['final_relationship_type'] != 'duplicate/semantic duplicate':
            continue
        a, b = by_id[r['item1_node_id']], by_id[r['item2_node_id']]
        ta, tb = business_type(a['article_path']), business_type(b['article_path'])
        if ta not in ('task', 'activity') or tb not in ('task', 'activity'):
            continue
        pair_type = ' - '.join(sorted((ta, tb)))
        parent_a = {x['document_map'] for x in membership[a['article_path']]}
        parent_b = {x['document_map'] for x in membership[b['article_path']]}
        if parent_a & parent_b:
            same_document += 1
            continue
        pairs[pair_type] += 1
        if ta != tb and a['text'] == b['text'] and int(a['word_count']) >= 35 and a['article_title'].lower() not in ('summary', 'policy reference'):
            example_candidates.append({'section1': a['article_path'], 'section2': b['article_path'], 'title1': a['article_title'], 'title2': b['article_title'], 'words': a['word_count'], 'identical_raw_text': True, 'conrefs1': a['conref_targets'], 'conrefs2': b['conref_targets'], 'text': a['text']})
    write_csv('activity_task_identical_examples.csv', example_candidates)
    summary = {'scope': 'English en_EN; saved ORT internal classifications; document types derived from path', 'all_map_categories': dict(category_maps), 'all_body_node_categories': dict(Counter(business_type(n['article_path']) for n in nodes)), 'task_activity_maps': dict(Counter(m['business_document_type'] for m in maps)), 'task_activity_body_nodes': dict(Counter(business_type(n['article_path']) for n in nodes if business_type(n['article_path']) in ('task','activity'))), 'topic_occurrences_in_task_activity_maps': len(sections), 'task_activity_map_othermeta_count': sum(m['has_map_othermeta'] for m in maps), 'top_level_headings_by_type': {t: [{'heading': k[1], 'maps': v} for k,v in headings.most_common() if k[0] == t][:9] for t in ('activity','task')}, 'cross_document_duplicate_edges_by_type': dict(pairs), 'same_document_duplicate_edges_excluded': same_document, 'activity_task_identical_nontrivial_examples': len(example_candidates), 'section_body_word_statistics': {t: {'median': statistics.median([int(n['word_count']) for n in nodes if business_type(n['article_path'])==t]), 'max': max(int(n['word_count']) for n in nodes if business_type(n['article_path'])==t)} for t in ('activity','task')}, 'body_nodes_with_no_map_membership': sum(not membership[n['article_path']] for n in nodes if business_type(n['article_path']) in ('task','activity'))}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(example_candidates[:5], indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
