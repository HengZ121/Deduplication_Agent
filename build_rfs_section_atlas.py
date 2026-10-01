"""Build a source-traceable comparison of the eight English RFS task maps.

Existing DITA boundaries are preserved. Grouping is exact resolved structure;
nonexact relationships remain pairwise evidence, never transitive clusters.
"""
from pathlib import Path
from collections import defaultdict, Counter
from itertools import combinations
import csv, json, html, difflib, shutil, zipfile, math
from audit_ort_knowledge_reuse import (ROOT, ReuseAudit, element_text, xml_local_name,
    digest, structure, norm, word_tokens, write_csv)

OUT = Path('outputs/rfs_section_atlas')
DOCS = dict(zip('CEGKMNFS', ['roe_rts','roe_quit','roe_retirement','roe_other',
    'roe_dismissal','roe_loa','completing_roe_fishing_roe','completing_roe_strike_lockout']))
H = lambda x: html.escape(str(x))
LABELS = {'exact_resolved_section':'Exact content', 'template_variant_candidate':'Variant candidate',
 'partial_overlap_observed':'Partial overlap', 'related_or_unresolved':'Related / unresolved',
 'unresolved_source':'Unresolved source', 'semantic_equivalence_candidate':'Unconfirmed similarity'}

def force_graph(items, empty):
    """Deterministic spring/charge layout, embedded as offline, printable SVG.

    Only exact resolved-body pairs get edges. Empty headings never create
    duplicate edges. Distances are layout outputs, not similarity scores.
    """
    count = len(items)
    width, height, radius = 280, 240, 17
    positions = [[width/2+75*math.cos(2*math.pi*i/count),
                  height/2+75*math.sin(2*math.pi*i/count)] for i in range(count)]
    velocities = [[0., 0.] for _ in items]
    edges = [(i,j) for i,j in combinations(range(count),2)
             if not empty and items[i]['signature']==items[j]['signature']]
    connected = {i for edge in edges for i in edge}
    # Repulsion separates nodes; springs draw proven exact matches together.
    # Weak centering and bounded coordinates keep every label inside the cell.
    for tick in range(700):
        forces = [[(width/2-x)*.012,(height/2-y)*.012] for x,y in positions]
        for i,j in combinations(range(count),2):
            dx,dy=positions[j][0]-positions[i][0],positions[j][1]-positions[i][1]
            distance=max(math.hypot(dx,dy),.01)
            magnitude=1100/(distance*distance)+max(0,43-distance)*.8
            fx,fy=dx/distance*magnitude,dy/distance*magnitude
            forces[i][0]-=fx; forces[i][1]-=fy
            forces[j][0]+=fx; forces[j][1]+=fy
        for i,j in edges:
            dx,dy=positions[j][0]-positions[i][0],positions[j][1]-positions[i][1]
            distance=max(math.hypot(dx,dy),.01)
            magnitude=(distance-66)*.028
            fx,fy=dx/distance*magnitude,dy/distance*magnitude
            forces[i][0]+=fx; forces[i][1]+=fy
            forces[j][0]-=fx; forces[j][1]-=fy
        for i in range(count):
            for axis,limit in ((0,width),(1,height)):
                velocities[i][axis]=(velocities[i][axis]+forces[i][axis])*.72
                positions[i][axis]=min(limit-radius-6,max(radius+6,positions[i][axis]+velocities[i][axis]))
    assert all(math.dist(positions[i],positions[j])>=2*radius+2 for i,j in combinations(range(count),2)), 'Overlapping graph nodes'
    description=('Empty heading nodes; no duplicate edges.' if empty else
                 'Lines connect exact expanded content. Unconnected nodes have no exact match in this row. Distance is not a similarity score.')
    svg=['<svg class="force-graph" viewBox="0 0 280 240" role="img" aria-label="'+H(description)+'"><title>'+H(description)+'</title>']
    for i,j in edges:
        x1,y1=positions[i]; x2,y2=positions[j]
        svg.append(f'<line class="exact-edge" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>')
    for i,item in enumerate(items):
        x,y=positions[i]; state='heading-node' if empty else ('matched-node' if i in connected else 'unmatched-node')
        svg.append(f'<g class="{state}"><title>'+H(item['letter']+' — '+item['path'])+f'</title><circle cx="{x:.2f}" cy="{y:.2f}" r="{radius}"/><text x="{x:.2f}" y="{y:.2f}" dy=".35em" text-anchor="middle">'+item['letter']+'</text></g>')
    svg.append('</svg><small>'+('Empty headings · no content edges' if empty else f'{len(edges)} exact-content '+('edge' if len(edges)==1 else 'edges'))+'</small>')
    return ''.join(svg)

def family(title, headings, path):
    # Shared notes are aligned by source identity, never by generic Note/Callout titles.
    if '/common_' in path:
        return ' / '.join(headings + [Path(path).stem])
    if title.startswith(('Linking the ROE', 'Creating a link between the ROE')):
        title = 'Linking the ROE and matching employment'
    return ' / '.join(headings + [title.rstrip(':')])

def explain_row(key, items, groups, pairs, occurrences):
    """Describe duplication evidence only, separating copied files from shared references."""
    if all(n['empty'] for n in items):
        return [('Duplication','No duplicated body content — these nodes are empty headings.')], None
    exact=[' / '.join(v) for v in groups.values() if len(v)>1]
    one_source=len({n['path'] for n in items})==1
    sample=next((n for n in items if n['letter']=='E'),items[0])
    parts=[]
    if len(items)==1:
        parts.append(('Exact matches','No other document references this node in this aligned row.'))
    elif one_source:
        parts.append(('Exact matches',', '.join(n['letter'] for n in items)+' reference the same DITA file. The repeated content comes from an existing shared source, not separate file copies.'))
    elif len(groups)==1:
        parts.append(('Exact matches',' / '.join(n['letter'] for n in items)+' have identical expanded bodies and reference targets in separate files.'))
    else:
        parts.append(('Exact matches',('; '.join(exact)+'. Other full sections differ.') if exact else 'No full-section exact matches in this row.'))
    nonexact=[p for p in pairs if not p['resolved_structure_equal']]
    best=max(nonexact,key=lambda p:p['longest_shared_block_words'],default=None)
    quote=None
    if best and best['example_shared_block']:
        parts.append(('Partial duplication',best['pair']+' share '+str(best['shared_exact_blocks'])+' exact internal block(s) of at least 12 tokens. The excerpt below is one observed match.'))
        quote=best['example_shared_block']
        sample=next(n for n in items if n['letter']==best['pair'][0])
    elif len(items)>1 and len(groups)==1:
        quote=sample['resolved_text']
    differences={
        'Summary':'The summary wording follows the same pattern, but the RFS category and Fishing qualifier differ. These are similar summaries, not exact full-section duplicates.',
        'In RCM':'C / E / G / M match exactly. N differs by a hyphen versus an en dash. K adds four Other categories; F uses different ROE field numbers; S contains only the first three questions.',
        'Completing the Resolve Issue section':'Only G / N are exact full-section matches. The other sections differ in expanded wording or reference structure.',
        'Ensuring the reason for separation (RFS) details are correct':'All eight full sections differ. Their shared instructions surround different RFS condition-to-outcome tables.',
        'Selecting a special condition for the decision on file':'None of the seven sections match in full. Shared passages occur within differing decision branches and local step references.'}
    leaf=key.split(' / ')[-1]
    if leaf in differences: parts.append(('Differences within the duplicated wording',differences[leaf]))
    elif 'Linking the ROE' in key:
        parts.append(('Differences within the duplicated wording',
            'C / N match exactly. Other sections share passages but differ in wording or local step destinations.' if key.startswith('Step by step') else
            'The explanation contains shared passages, but expanded example tables differ. For example, Quit and Dismissal show E versus M in the first sample ROE row.'))
    elif nonexact:
        parts.append(('Differences within the duplicated wording','The full sections differ in text, structure or reference targets; expand the pair evidence below for the individual changes.'))
    if '/common_notes/' in sample['path']:
        twins=[n for n in occurrences if n['signature']==sample['signature'] and n['path']!=sample['path'] and '/common_notes/' in n['path']]
        if twins:
            parts.append(('Exact duplicate in another row','The same expanded body also appears in '+', '.join(sorted({Path(n['path']).name for n in twins}))+'. These are separate source files.'))
            quote=sample['resolved_text']
    if quote:
        excerpt=quote if len(quote)<=320 else quote[:320].rsplit(' ',1)[0]+'…'
        parts.append(('Duplicated text · '+sample['letter'],excerpt))
    return parts, sample if quote else None

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    audit = ReuseAudit()
    families, documents, occurrences, sections = {}, [], [], {}
    copied = set()
    def copy_source(path):
        path = path.resolve()
        if path in copied: return
        copied.add(path)
        rel = path.relative_to(ROOT)
        dest = OUT/'raw'/rel
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,dest)
        tree = audit.resolver.parse_xml(path)
        for node in tree.iter():
            if node.get('conref'):
                target, _ = audit.resolver.resolve_local_reference(path,node.get('conref'))
                copy_source(target)

    for letter, folder in DOCS.items():
        mp = ROOT/'en_EN/task'/folder/(folder+'.ditamap')
        tree = audit.resolver.parse_xml(mp)
        title = element_text(tree.find('title'))
        documents.append(dict(letter=letter,title=title,map=mp.relative_to(ROOT).as_posix(),business_type='task'))
        copy_source(mp)
        order = [0]
        def visit(parent, headings):
            for ref in parent:
                if xml_local_name(ref.tag) != 'topicref': continue
                path,_ = audit.resolver.resolve_local_reference(mp,ref.get('href'))
                path=path.resolve(); rel=path.relative_to(ROOT).as_posix()
                topic=audit.resolver.parse_xml(path); t=element_text(topic.find('title'))
                body=next(n for n in topic if xml_local_name(n.tag).endswith('body'))
                key=family(t,headings,rel)
                audit.index.parents[rel]=[dict(title=title,heading_path=' > '.join(headings),map_path=mp.relative_to(ROOT).as_posix())]
                s=audit.make_section(dict(article_path=rel,article_title=t,text=element_text(body),node_id=digest(rel)), 'en')
                order[0]+=1
                rec=dict(letter=letter,map_order=order[0],family=key,title=t,path=rel,
                         heading_path=' > '.join(headings),empty=not s.resolved.strip(),signature=s.signature,
                         words=len(word_tokens(s.resolved)),resolved_text=s.resolved)
                families.setdefault(key,[]).append(rec); occurrences.append(rec); sections[(letter,rel)]=s
                copy_source(path)
                visit(ref,headings+[t.rstrip(':')])
        visit(tree,[])

    # Keep shared notes next to their parent section rather than appending late discoveries.
    top_order = {k:i for i,k in enumerate(['Summary','What you need to know','Regional considerations','What you need to look for','Step by step','Policy reference'])}
    families = dict(sorted(families.items(), key=lambda kv: (top_order[kv[0].split(' / ')[0]], min(n['map_order'] for n in kv[1]), kv[0])))
    pair_rows=[]; page_rows=[]; summary_rows=[]
    for i,(key,items) in enumerate(families.items(),1):
        groups=defaultdict(list)
        for n in items: groups[n['signature']].append(n['letter'])
        empty=all(n['empty'] for n in items)
        pairs=[]
        for a,b in combinations(items,2):
            sa,sb=sections[(a['letter'],a['path'])],sections[(b['letter'],b['path'])]
            kind,evidence=audit.assess_pair(sa,sb)
            if empty: kind='heading_only'
            # No new semantic inference: this report has no model gate or human equivalence labels.
            if kind=='semantic_equivalence_candidate': kind='related_or_unresolved'
            row=dict(family=key,pair=a['letter']+'–'+b['letter'],classification=kind,
                     source_a=a['path'],source_b=b['path'],**evidence)
            pairs.append(row); pair_rows.append(row)
        missing=''.join(c for c in DOCS if not any(n['letter']==c for n in items))
        shared_source=len({n['path'] for n in items})==1 and len(items)>1
        grouptext=' | '.join(''.join(v) for v in groups.values())
        counts=Counter(p['classification'] for p in pairs)
        explanation, sample = explain_row(key, items, groups, pairs, occurrences)
        narrative=[label+': '+value for label,value in explanation]
        explanation_html='<div class="row-explanation">'+''.join(
            '<div class="explanation-part"><strong>'+H(label)+'</strong><p>'+H(value)+'</p></div>'
            for label,value in explanation)+'</div>'
        if sample:
            explanation_html+='<a class="source-link" href="raw/'+H(sample['path'])+'">Open quoted DITA source ('+H(sample['letter'])+')</a>'

        grouphtml=force_graph(items, empty)
        evidencehtml=[]
        for p in pairs:
            a=next(n for n in items if n['letter']==p['pair'][0]); b=next(n for n in items if n['letter']==p['pair'][-1])
            # Every nonexact pair has a complete word-level edit list, not a cropped model input.
            wa=a['resolved_text'].split(); wb=b['resolved_text'].split(); edits=[]
            for op,ia,ja,ib,jb in difflib.SequenceMatcher(None,wa,wb,autojunk=False).get_opcodes():
                if op!='equal': edits.append('<tr><td>'+H(' '.join(wa[ia:ja]) or '∅')+'</td><td>'+H(' '.join(wb[ib:jb]) or '∅')+'</td></tr>')
            diff='<table><tr><th>'+p['pair'][0]+'</th><th>'+p['pair'][-1]+'</th></tr>'+''.join(edits)+'</table>' if edits else '<p>No word changes. If groups differ, inspect XML structure and link targets.</p>'
            evidencehtml.append('<details><summary>'+H(p['pair']+' · '+LABELS.get(p['classification'],p['classification']))+'</summary><p>Token Jaccard '+str(p['lexical_jaccard_resolved'])+'; exact internal blocks ≥12 tokens: '+str(p['shared_exact_blocks'])+'. Signals: '+H(p['review_signals'] or 'none detected')+'</p>'+('<blockquote>'+H(p['example_shared_block'])+'</blockquote>' if p['example_shared_block'] else '')+diff+'</details>')
        rawhtml=[]
        for n in items:
            s=sections[(n['letter'],n['path'])]
            rawhtml.append('<details><summary>'+H(n['letter']+' · '+n['title']+' · '+str(n['words'])+' tokens')+'</summary><p><a href="raw/'+H(n['path'])+'">'+H(n['path'])+'</a></p><h4>Full expanded section</h4><p class="source">'+H(n['resolved_text'] or '[Empty heading body]')+'</p><h4>Original XML</h4><pre>'+H((ROOT/n['path']).read_text(encoding='utf-8'))+'</pre></details>')
        page_rows.append('<tr><td><a href="#row'+str(i)+'">'+str(i)+'. '+H(key)+'</a></td><td>'+grouphtml+('<br>Absent: '+H(missing) if missing else '')+'</td><td>'+explanation_html+'</td></tr><tr><td colspan="3"><details id="row'+str(i)+'"><summary>Inspect sources and all '+str(len(pairs))+' within-row pairs</summary>'+''.join(rawhtml)+''.join(evidencehtml)+'</details></td></tr>')
        summary_rows.append(dict(row=i,family=key,occurrences=len(items),empty=empty,exact_groups=grouptext,absent=missing,narrative=' '.join(narrative)))

    assert len(occurrences)==sum(len(v) for v in families.values())
    assert all(len({n['letter'] for n in v})==len(v) for v in families.values()), 'Ambiguous alignment'
    errors=[e for s in sections.values() for e in s.errors]
    assert not errors,errors
    write_csv(OUT/'node_inventory.csv',occurrences)
    write_csv(OUT/'pair_evidence.csv',pair_rows)
    write_csv(OUT/'section_summary.csv',summary_rows)
    write_csv(OUT/'documents.csv',documents)
    write_csv(OUT/'reference_repairs.csv',audit.resolver.repairs)
    metrics=dict(documents=len(documents),node_occurrences=len(occurrences),unique_source_topics=len({n['path'] for n in occurrences}),aligned_rows=len(families),empty_heading_occurrences=sum(n['empty'] for n in occurrences),pair_classifications=dict(Counter(p['classification'] for p in pair_rows)),unresolved_sources=errors,raw_files=len(copied))
    (OUT/'validation.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    intro=''.join('<li><b>'+d['letter']+'</b> — '+H(d['title'])+' <a href="raw/'+d['map']+'">map</a></li>' for d in documents)
    content='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Eight RFS documents — section atlas</title><style>
    body{font:16px/1.55 Arial,sans-serif;color:#193046;background:#f7f9fb;margin:28px auto;padding:0 24px;max-width:1500px}h1{font-size:30px}h2{margin-top:32px}table{border-collapse:collapse;width:100%;background:white;table-layout:fixed}th,td{text-align:left;vertical-align:top;padding:14px;border-bottom:1px solid #d5dfe5;overflow-wrap:anywhere}th{background:#17364c;color:white}th:nth-child(1){width:24%}th:nth-child(2){width:25%}p{margin:0 0 12px}a{color:#08619b}details{margin:8px 0;padding:8px;background:#edf2f6}summary{cursor:pointer;font-weight:bold}pre{white-space:pre-wrap;font-size:13px;overflow-wrap:anywhere}.source{white-space:pre-wrap}.group{display:inline-flex;gap:3px;padding:7px;margin:3px;border-radius:24px}.same{background:#d3eee6;border:2px solid #317d68}.single{border:1px dashed #879bab}.empty{background:#e7eaee}.node{display:inline-grid;place-items:center;border-radius:50%;background:white;color:#193046;width:26px;height:26px;font-weight:bold}blockquote{border-left:4px solid #317d68;padding-left:12px}small{font-size:14px}@media(max-width:700px){body{padding:0 8px;margin:12px}th,td{padding:7px}.node{width:22px;height:22px}.group{padding:3px}}@media print{body{max-width:none;font-size:11px}details{display:none}a{color:inherit}tr{break-inside:avoid}th{color:black;background:#eee}}.force-graph{display:block;width:100%;min-width:210px;max-width:340px;height:auto;margin:auto}.exact-edge{stroke:#317d68;stroke-width:1.5;opacity:.45}.force-graph circle{stroke:#708494;stroke-width:1.5;fill:white}.force-graph .matched-node circle{fill:#d3eee6;stroke:#317d68}.force-graph .heading-node circle{fill:#e7eaee;stroke:#879bab}.force-graph text{fill:#193046;font:bold 17px Arial,sans-serif}@media(max-width:850px){body>table>thead{display:none}body>table>tbody>tr,body>table>tbody>tr>td{display:block;width:auto}body>table>tbody>tr>td:nth-child(2){max-width:340px}.force-graph{min-width:0}}@media print{.force-graph{min-width:0}}
.row-explanation{display:grid;gap:12px}.explanation-part strong{display:block;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#51687b;margin-bottom:3px}.explanation-part:first-child p{font-weight:bold;font-size:18px;color:#17364c}.explanation-part p{margin:0}.explanation-part:last-child p{font-size:14px}.source-link{display:inline-block;margin-top:12px;font-size:14px}
</style></head><body>
    <h1>Eight RFS documents: what repeats, what changes</h1>
    <p>Each letter is one document’s existing DITA node in that row. Force-directed graphs use springs between exact-content matches and repulsion between nodes. Green lines connect exact expanded content; green nodes have an exact match, and outlined nodes do not. Gray nodes are empty headings and have no content edges. Distance is a layout choice, not a similarity score. Matches describe content, not authorization to use one instruction for every RFS subject.</p>
    <ul>'''+intro+'''</ul><p><b>F and S are display labels.</b> Their source titles both use B. Scope: eight English task maps from en_EN; this is not a task-versus-activity comparison.</p>
    <h2>How to read the evidence</h2><p>Rows align by heading path, with the two linking-title variants explicitly aligned. Shared notes align by source ID, not by generic “Note” titles or ordinal position. This avoids inventing correspondence between unrelated callouts; different note IDs appear on separate rows and may still repeat wording across rows.</p>
    <p>Exact groups require reference-expanded body structure and link targets to match. Nonexact pair labels reuse the earlier deterministic audit: high lexical overlap with changed fields/links is a variant candidate; an identical internal XML block of at least 12 tokens supports partial overlap; remaining pairs stay related/unresolved. No semantic equivalence is confirmed, no LLM/model inference is run, and similarity edges are never transitively merged. Pair labels apply only within aligned rows; cross-row note duplicates are listed in the companion narrative.</p>
    <p><a href="ANALYSIS.md">Narrative and cross-row note matches</a> · <a href="section_summary.csv">Row narratives</a> · <a href="node_inventory.csv">All nodes and full text</a> · <a href="pair_evidence.csv">All pair evidence</a> · <a href="validation.json">Count validation</a></p><p>'''+H(f"{len(documents)} documents · {len(occurrences)} node occurrences · {len(families)} comparison rows · {sum(n['empty'] for n in occurrences)} empty headings · {len(copied)} packaged raw files")+'''</p><table><thead><tr><th>Section / node</th><th>Force-directed exact-content graph</th><th>Duplication findings</th></tr></thead><tbody>'''+''.join(page_rows)+'''</tbody></table></body></html>'''
    (OUT/'index.html').write_text(content,encoding='utf-8')
    # Cross-row exact notes are explicitly reported instead of hiding them behind alignment.
    note_groups=defaultdict(list)
    for n in occurrences:
        if '/common_' in n['path']: note_groups[n['signature']].append(n)
    cross=[]
    for group in note_groups.values():
        if len({n['path'] for n in group})>1:
            cross.append(dict(sources=sorted({n['path'] for n in group}),occurrences=[n['letter']+':'+Path(n['path']).stem for n in group],text=group[0]['resolved_text']))
    (OUT/'cross_row_note_matches.json').write_text(json.dumps(cross,indent=2,ensure_ascii=False),encoding='utf-8')
    md=['# RFS section atlas', '', 'Open index.html for the visual comparison, full sources and pair differences.', '', '## Cross-row exact note matches', 'Different note IDs are not aligned merely because their titles match. The following resolved bodies nevertheless match exactly:']
    for g in cross: md+=['', '- '+', '.join(g['occurrences']), '  '+g['text']]
    md+=['','## Row-by-row analysis']
    for r in summary_rows: md+=['',f"### {r['row']}. {r['family']}",r['narrative']]
    (OUT/'ANALYSIS.md').write_text('\n'.join(md),encoding='utf-8')
    with zipfile.ZipFile(OUT.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        for p in OUT.rglob('*'):
            if p.is_file(): z.write(p,p.relative_to(OUT.parent))
    print(json.dumps(metrics,indent=2))

if __name__=='__main__': main()
