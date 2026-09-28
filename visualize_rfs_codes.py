"""Adapt audited RFS sections to the existing chord renderer, without model calls.

Every edge contributes one aligned, nonempty section pair. Already-shared source
files are separated from copied exact content; neither implies safe applicability.
"""
from pathlib import Path
import json
import pandas as pd
import visualize_duplicate_chords as chord

SOURCE = Path('outputs/rfs_section_atlas')
OUT = Path('outputs/visualizations/rfs_codes_chord.html')
LABELS = {
    'exact_resolved_section': 'Exact content in separate files',
    'template_variant_candidate': 'Variant candidate',
    'partial_overlap_observed': 'Partial overlap',
    'related_or_unresolved': 'Related / unresolved',
}


def prepare_pairs():
    inventory = pd.read_csv(SOURCE/'node_inventory.csv', keep_default_na=False)
    nodes = {(r.letter, r.path): r for r in inventory.itertuples()}
    rows = []
    for p in pd.read_csv(SOURCE/'pair_evidence.csv', keep_default_na=False).to_dict('records'):
        if p['classification'] == 'heading_only':
            continue
        letters = p['pair'].split('–')
        label = LABELS[p['classification']]
        if p['source_a'] == p['source_b']:
            label = 'Already shared source'
        row = dict(llm_relationship_type=label, section_count=1,
                   llm_analysis=f"Section: {p['family']}. {p['review_signals'] or 'No automated risk signal detected'}. "
                   'Content evidence only; applicability is not approved.', family=p['family'])
        for side, (letter, path) in enumerate(zip(letters, [p['source_a'], p['source_b']]), 1):
            n = nodes[letter, path]
            row.update({f'item{side}_title': letter, f'item{side}_path': path,
                        f'item{side}_id': f'{letter}:{path}', f'item{side}_type': 'task',
                        f'item{side}_summary': p['family'], f'item{side}_text': n.resolved_text})
        rows.append(row)
    return pd.DataFrame(rows)


def count_wording(value):
    """Relabel the reused renderer so count weights never masquerade as scores."""
    if isinstance(value, dict): return {k: count_wording(v) for k,v in value.items()}
    if isinstance(value, list): return [count_wording(v) for v in value]
    if isinstance(value, tuple): return tuple(count_wording(v) for v in value)
    if not isinstance(value, str): return value
    return (value.replace('Total similarity:', 'Section-pair incidences:')
            .replace('Sum similarity:', 'Section pairs:')
            .replace('Avg similarity: 1.000<br>', '')
            .replace('Best example:', 'Representative section:'))


def main():
    df = prepare_pairs()
    chord.RELATIONSHIP_COLORS.update(dict(zip(
        ['Exact content in separate files','Already shared source','Variant candidate','Partial overlap','Related / unresolved'],
        ['#197e67','#577c96','#c38b21','#8366ad','#929ba5'])))
    links, totals = chord.build_aggregates(df, 'title', 'section_count', True)
    links = links.sort_values(['weight','avg_weight'], ascending=False).reset_index(drop=True)
    links['diff_id'] = [f'pair-{i+1}' for i in range(len(links))]
    fig = chord.build_figure(links, totals, 'RFS codes: section relationships', 'title',
                             SOURCE/'pair_evidence.csv', len(totals), len(links))
    fig.update_layout(title_text=f'RFS codes: section relationships<br><sup>8 documents · {len(df)} aligned, nonempty section pairs · counts, not similarity scores</sup>')
    fig.layout.annotations[-1].text = 'Line width increases with section-pair count. Select a relationship filter; click a connection for an example.'
    fig = chord.go.Figure(count_wording(fig.to_plotly_json()))
    records = chord.build_pairwise_diff_records(links)
    for record in records:
        record['label'] += ' · ' + record['relationship'] + ' · representative example'
        record['analysis'] = 'This connection aggregates multiple section pairs; the text below is one representative. Use the individual section entries for every pair. ' + record['analysis']
    # Keep every underlying pair selectable, not only the representative retained
    # by the existing aggregation function. Click IDs still select link examples.
    for i,row in enumerate(df.to_dict('records')):
        individual, _ = chord.build_aggregates(pd.DataFrame([row]), 'title', 'section_count', True)
        individual['diff_id'] = f'section-{i+1}'
        record = chord.build_pairwise_diff_records(individual)[0]
        record['label'] += ' · ' + row['family'] + ' · ' + row['llm_relationship_type']
        records.append(record)
    page = chord.build_standalone_html(fig, records, True, 'RFS codes: section relationships')
    page = page.replace('<div class="metric">avg similarity ${formatScore(record.avgWeight)}</div>', '')
    page = page.replace('sum similarity ${formatScore(record.weight)}', 'section-pair count ${Number(record.weight)}')
    page = page.replace('<strong>LLM analysis:</strong>', '<strong>Audit evidence:</strong>')
    note = '''<section style="padding:20px 32px;background:#fff;color:#172033;line-height:1.6">
    <h2>Compare the eight RFS documents</h2>
    <p>C = Return to school; E = Quit; G = Mandatory retirement; K = Other; M = Dismissal;
    N = Leave of absence; F = Fishing; S = Strike or lockout. F and S are display labels;
    both source titles use B.</p>
    <p>Each counted pair compares nodes in the same aligned section row. The 168 empty-heading pairs
    are excluded. Already-shared source files are shown separately from exact content in separate files.
    Counts are neither duplicated-word percentages nor evidence that two whole documents can be merged.
    Variant and partial-overlap connections are review candidates. Related/unresolved is not a duplicate finding.</p>
    <p>The chart initially shows all relationship types. Filters hide connections; arc sizes retain the all-category totals.
    Clicking a connection shows one representative section; the difference-viewer list also contains every individual pair.
    These are deterministic audit labels, despite the legacy input column named llm_relationship_type; no LLM was called.</p>
    <p><a href="../rfs_section_atlas/index.html">Section-by-section atlas and raw files</a> ·
    <a href="rfs_codes_pairs.csv">All plotted pairs</a> · <a href="rfs_codes_counts.csv">Counts by code pair and category</a></p>
    </section>'''
    page = page.replace('<body>', '<body>'+note, 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding='utf-8')
    df.to_csv(OUT.with_name('rfs_codes_pairs.csv'), index=False)
    links[['source_node','target_node','relationship','pair_count']].to_csv(OUT.with_name('rfs_codes_counts.csv'),index=False)
    assert len(totals) == 8 and int(links.pair_count.sum()) == len(df) == 370
    assert len(records) == len(links) + len(df)
    assert 'avg similarity ${' not in page and 'sum similarity ${' not in page
    assert len({r['id'] for r in records}) == len(records)
    print(json.dumps({'output':str(OUT),'section_pairs':len(df),'connections':len(links),
                      'categories':df.llm_relationship_type.value_counts().to_dict()},indent=2))


if __name__ == '__main__':
    main()
