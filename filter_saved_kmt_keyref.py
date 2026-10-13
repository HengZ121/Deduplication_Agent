"""Remove keyref-bearing source topics from completed KMT results, without inference.

Back up every changed artifact first. Identify keyref attributes in the original
XML, because extracted plain text does not retain the attributes. Reindex saved
pair references after filtering so the remaining CSVs stay mutually consistent.
"""
from pathlib import Path
import collections
import csv
import datetime
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'unzipped/KMT_2026-10-07/output/dita'
BACKUP = ROOT / '.build' / ('before_keyref_row_filter_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
csv.field_size_limit(100_000_000)


def read_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def backup(path):
    target = BACKUP / path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def filter_run(language):
    directory = ROOT / f'outputs/kmt_2026-10-07_body_{language}_kg_pipeline'
    nodes = read_rows(directory / 'kg_nodes.csv')
    removed = set()
    removed_rows = []
    # Fail before modifying any result if a source file cannot be resolved/parsed.
    for node in nodes:
        source = SOURCE / node['topic_path']
        tree = ET.parse(source)
        if any(any(k.rsplit('}', 1)[-1] == 'keyref' for k in element.attrib) for element in tree.iter()):
            removed.add(node['node_id'])
            removed_rows.append({'node_id': node['node_id'], 'source_path': node['topic_path']})
    kept = [node for node in nodes if node['node_id'] not in removed]
    comparable = [node for node in kept if node['is_comparable'].lower() == 'true']
    indices = {node['node_id']: index for index, node in enumerate(comparable)}
    counts = {}
    classifications = collections.Counter()
    statuses = collections.Counter()
    borderline = 0
    pair_row_map = {}
    pair_fields = ('item1_node_id', 'item2_node_id')
    for path in sorted(directory.glob('*.csv')):
        backup(path)
        temporary = path.with_suffix('.csv.filtering')
        before = after = 0
        with path.open(encoding='utf-8-sig', newline='') as src, temporary.open('w', encoding='utf-8-sig', newline='') as dst:
            reader = csv.DictReader(src)
            writer = csv.DictWriter(dst, fieldnames=reader.fieldnames)
            writer.writeheader()
            identity_fields = [k for k in ('node_id', 'instance_id', *pair_fields, 'source_node_id', 'target_node_id') if k in reader.fieldnames]
            for old_index, row in enumerate(reader):
                before += 1
                if any(row[k] in removed for k in identity_fields):
                    continue
                for side in ('item1', 'item2'):
                    if side + '_index' in row and side + '_node_id' in row:
                        row[side + '_index'] = indices[row[side + '_node_id']]
                if path.name == 'kg_pair_classifications.csv':
                    pair_row_map[old_index] = after
                    classifications[row['final_relationship_type']] += 1
                    statuses[row['llm_review_status']] += 1
                    borderline += row['is_borderline'].lower() == 'true'
                writer.writerow(row)
                after += 1
        temporary.replace(path)
        counts[path.name] = {'before': before, 'after': after, 'removed': before - after}
    path = directory / 'kg_llm_reviews.jsonl'
    backup(path)
    temporary = path.with_suffix('.jsonl.filtering')
    with path.open(encoding='utf-8') as src, temporary.open('w', encoding='utf-8') as dst:
        for line in src:
            row = json.loads(line)
            if any(row[k] in removed for k in pair_fields):
                continue
            row['pair_row_index'] = pair_row_map[row['pair_row_index']]
            dst.write(json.dumps(row, ensure_ascii=False) + '\n')
    temporary.replace(path)
    # Binary scoring checkpoints describe the old candidate order. Keep only in backup.
    for path in directory.glob('kg_cross_encoder_scores.checkpoint*'):
        backup(path)
        path.unlink()
    summary_path = directory / 'run_summary.json'
    backup(summary_path)
    summary = json.loads(summary_path.read_text(encoding='utf-8-sig'))
    summary.update(node_count=len(kept), comparable_content_node_count=len(comparable),
                   structural_node_count=sum(n['is_structural'].lower() == 'true' for n in kept),
                   candidate_pair_count=counts['kg_candidate_pairs.csv']['after'],
                   edge_count=counts['kg_edges.csv']['after'], borderline_pair_count=borderline,
                   llm_reviewed_pair_count=statuses['reviewed'], llm_api_error_pair_count=statuses['api_error'],
                   llm_not_reviewed_pair_count=statuses['not_reviewed'], relationship_counts=dict(classifications),
                   keyref_filter='Entire source topic excluded when its XML contains a keyref attribute; retained scores and LLM decisions reused.')
    summary_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    review_summary = directory / 'llm_review_summary.json'
    if review_summary.exists():
        backup(review_summary)
        review_data = json.loads(review_summary.read_text(encoding='utf-8-sig'))
        review_data.update(pair_count=counts['kg_pair_classifications.csv']['after'],
                           borderline_pair_count=borderline,
                           llm_review_status_counts=dict(statuses),
                           final_relationship_counts=dict(classifications))
        review_summary.write_text(json.dumps(review_data, indent=2), encoding='utf-8')
    with (directory / 'keyref_removed_nodes.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['node_id', 'source_path'])
        writer.writeheader()
        writer.writerows(removed_rows)
    for path in directory.glob('*.zip'):
        backup(path)
        with zipfile.ZipFile(path) as old:
            names = old.namelist()
        temporary = path.with_suffix('.zip.filtering')
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                local = directory / Path(name).name
                if local.is_file() and local != path:
                    archive.write(local, name)
        temporary.replace(path)
    report = {'language': language, 'removed_nodes': len(removed), 'remaining_nodes': len(kept), 'files': counts, 'backup': str(BACKUP)}
    (directory / 'keyref_filter_summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    for language in ('en', 'fr'):
        filter_run(language)
