"""Inspect saved RFS decisions against expanded source and document context."""
import csv
import json
from pathlib import Path

from research_ort_rfs import OUT, ROOT, SourceReconstructor, write_csv
from run_passage_pipeline import normalized_passage


def main():
    recon = SourceReconstructor()
    audit = []
    with (OUT / 'rfs_pair_evidence.csv').open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if row['final_relationship_type'] != 'duplicate/semantic duplicate':
                continue
            a, b = ROOT / row['item1_path'], ROOT / row['item2_path']
            def body_text(path):
                root = recon.resolver.parse_xml(path)
                body = next(c for c in root if c.tag.endswith('body'))
                return recon.resolver.expanded_element_text(body, path)
            left, right = body_text(a), body_text(b)
            if row['normalized_equal'] == 'True' and normalized_passage(left) != normalized_passage(right):
                audit.append({'item1_path': row['item1_path'], 'item2_path': row['item2_path'], 'raw_identical': True, 'expanded_identical': False, 'expanded_text1': left, 'expanded_text2': right})
    write_csv(OUT / 'identical_body_different_expansion.csv', audit)

    # Restore corresponding French publications without treating translated
    # subject abbreviations as English RFS search hits.
    french, refreshed_english = [], []
    with (OUT / 'document_inventory.csv').open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            # Refresh English artifacts with audited export-link repairs and
            # readable source-order table rows before generating counterparts.
            title_en, topics_en, text_en = recon.document(ROOT / row['map_path'])
            Path(row['restored_file']).write_text(text_en + '\n', encoding='utf-8')
            row['topic_count'] = len(topics_en)
            row['words_in_reconstruction'] = len(text_en.split())
            refreshed_english.append(row)
            rel = row['map_path'].replace('en_EN/', 'fr_FR/', 1)
            path = ROOT / rel
            if not path.is_file():
                continue
            title, topics, text = recon.document(path)
            output = OUT / 'documents' / Path(rel).with_suffix('.md')
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text + '\n', encoding='utf-8')
            french.append({'map_path': rel, 'title': title, 'english_map': row['map_path'], 'topic_count': len(topics), 'restored_file': output.as_posix()})
    write_csv(OUT / 'french_counterpart_inventory.csv', french)
    write_csv(OUT / 'document_inventory.csv', refreshed_english)
    write_csv(OUT / 'selected_reconstruction_issues.csv', recon.issues)
    write_csv(OUT / 'reference_path_repairs.csv', recon.repairs)
    summary = {'identical_raw_rfs_duplicate_pairs_with_different_expansion': len(audit), 'french_counterpart_documents': len(french), 'selected_english_and_french_reconstruction_issues': len(recon.issues), 'audited_reference_path_repairs': len(recon.repairs)}
    (OUT / 'supplement_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
