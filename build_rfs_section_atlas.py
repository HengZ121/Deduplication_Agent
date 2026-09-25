"""Build a source-traceable comparison of the eight English RFS task maps.

Existing DITA boundaries are preserved. Grouping is exact resolved structure;
nonexact relationships remain pairwise evidence, never transitive clusters.
"""
from pathlib import Path
from collections import defaultdict, Counter
from itertools import combinations
import csv, json, html, difflib, shutil, zipfile
from audit_ort_knowledge_reuse import (ROOT, ReuseAudit, element_text, xml_local_name,
    digest, structure, norm, word_tokens, write_csv)

OUT = Path('outputs/rfs_section_atlas')
DOCS = dict(zip('CEGKMNFS', ['roe_rts','roe_quit','roe_retirement','roe_other',
    'roe_dismissal','roe_loa','completing_roe_fishing_roe','completing_roe_strike_lockout']))
H = lambda x: html.escape(str(x))
LABELS = {'exact_resolved_section':'Exact content', 'template_variant_candidate':'Variant candidate',
 'partial_overlap_observed':'Partial overlap', 'related_or_unresolved':'Related / unresolved',
 'unresolved_source':'Unresolved source', 'semantic_equivalence_candidate':'Unconfirmed similarity'}

def family(title, headings, path):
    # Shared notes are aligned by source identity, never by generic Note/Callout titles.
    if '/common_' in path:
        return ' / '.join(headings + [Path(path).stem])
    if title.startswith(('Linking the ROE', 'Creating a link between the ROE')):
        title = 'Linking the ROE and matching employment'
    return ' / '.join(headings + [title.rstrip(':')])

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
        narrative=[]
        if empty:
            narrative.append('These are empty structural headings in the export. Matching headings are not duplicated procedural content.')
        else:
            narrative.append(f"{len(items)} document occurrences form {len(groups)} exact-content group(s): {grouptext}. Exact means the expanded body, element order, attributes and link targets match after case/whitespace normalization; it does not establish equal applicability.")
            if shared_source: narrative.append('These documents already point to the same source file. Preserve that existing reuse; do not create another master copy.')
            if pairs:
                narrative.append('Pair evidence: '+', '.join(f'{LABELS.get(k,k)} {v}' for k,v in counts.items())+'. These labels are deterministic triage, not approved consolidation decisions.')
            hidden=[p['pair'] for p in pairs if p['raw_normalized_equal'] and not p['resolved_structure_equal']]
            if hidden: narrative.append('Raw-body normalization hides expanded content or link/structure differences for '+', '.join(hidden)+'. Inspect the expanded text and source XML below.')
        if missing: narrative.append('No corresponding node in '+', '.join(missing)+'. Absence means absent from these maps, not absence of the policy.')
        if key.endswith('In RCM'):
            narrative.append('C/E/G/M are structurally exact. N has the same checklist with a hyphen instead of an en dash in the Search / Correct screen name, so strict matching keeps it separate. K adds payroll-frequency, ownership, EI-request and service-provider categories. F asks about block 6B trip/purchase dates, block 11 RFS and block 12 comments; regular ROEs use blocks 11, 16 and 18. S contains only the first three questions. Reuse common questions individually while retaining these field and scope differences.')
        if key=='Summary': narrative.append('The common trigger is an ROE that cannot be linked or whose adjudication need cannot be determined. The RFS category and Fishing context change. Treat this as a template family with explicit subject values, not one unqualified summary.')
        if 'Selecting a special condition' in key: narrative.append('Fishing has no corresponding node in its map. The other procedures contain their own conditions and referenced decision content; verify those branches and local step targets before sharing an instruction.')
        if 'Linking the ROE' in key and 'Step by step' not in key: narrative.append('The repeated explanation includes sample ROE tables. In the Quit/Dismissal pair, the first row’s RFS value changes E to M after expansion. Shared prose and sample-table variants must be recorded separately.')
        if not empty:
            # Anchor each row's narrative in real source wording, including single-source notes.
            if len(groups)==1:
                narrative.append('Content example: “'+items[0]['resolved_text'][:400]+('…”' if len(items[0]['resolved_text'])>400 else '”'))
            else:
                best=max(pairs,key=lambda p:p['longest_shared_block_words'],default=None)
                if best and best['example_shared_block']:
                    narrative.append('Observed shared passage ('+best['pair']+'): “'+best['example_shared_block'][:300]+('…”' if len(best['example_shared_block'])>300 else '”'))
        if not empty and not shared_source: narrative.append('All eight publications are business-type task documents. Their RFS subject is inherited even when this section contains no category name. Exact text is a review opportunity, not permission to erase that scope.')

        grouphtml=''.join('<span class="group '+('empty' if empty else ('same' if len(v)>1 else 'single'))+'">'+''.join('<span class="node">'+c+'</span>' for c in v)+'</span>' for v in groups.values())
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
        page_rows.append('<tr><td><a href="#row'+str(i)+'">'+str(i)+'. '+H(key)+'</a></td><td>'+grouphtml+('<br>Absent: '+H(missing) if missing else '')+'</td><td>'+''.join('<p>'+H(n)+'</p>' for n in narrative)+'</td></tr><tr><td colspan="3"><details id="row'+str(i)+'"><summary>Inspect sources and all '+str(len(pairs))+' within-row pairs</summary>'+''.join(rawhtml)+''.join(evidencehtml)+'</details></td></tr>')
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
    body{font:16px/1.55 Arial,sans-serif;color:#193046;background:#f7f9fb;margin:28px auto;padding:0 24px;max-width:1500px}h1{font-size:30px}h2{margin-top:32px}table{border-collapse:collapse;width:100%;background:white;table-layout:fixed}th,td{text-align:left;vertical-align:top;padding:14px;border-bottom:1px solid #d5dfe5;overflow-wrap:anywhere}th{background:#17364c;color:white}th:nth-child(1){width:24%}th:nth-child(2){width:25%}p{margin:0 0 12px}a{color:#08619b}details{margin:8px 0;padding:8px;background:#edf2f6}summary{cursor:pointer;font-weight:bold}pre{white-space:pre-wrap;font-size:13px;overflow-wrap:anywhere}.source{white-space:pre-wrap}.group{display:inline-flex;gap:3px;padding:7px;margin:3px;border-radius:24px}.same{background:#d3eee6;border:2px solid #317d68}.single{border:1px dashed #879bab}.empty{background:#e7eaee}.node{display:inline-grid;place-items:center;border-radius:50%;background:white;color:#193046;width:26px;height:26px;font-weight:bold}blockquote{border-left:4px solid #317d68;padding-left:12px}small{font-size:14px}@media(max-width:700px){body{padding:0 8px;margin:12px}th,td{padding:7px}.node{width:22px;height:22px}.group{padding:3px}}@media print{body{max-width:none;font-size:11px}details{display:none}a{color:inherit}tr{break-inside:avoid}th{color:black;background:#eee}}</style></head><body>
    <h1>Eight RFS documents: what repeats, what changes</h1>
    <p>Each letter is one document’s existing DITA node in that row. Green enclosures group exact expanded content; dashed single nodes differ. Gray groups are empty headings. Grouping describes content, not authorization to use one instruction for every RFS subject.</p>
    <ul>'''+intro+'''</ul><p><b>F and S are display labels.</b> Their source titles both use B. Scope: eight English task maps from en_EN; this is not a task-versus-activity comparison.</p>
    <h2>How to read the evidence</h2><p>Rows align by heading path, with the two linking-title variants explicitly aligned. Shared notes align by source ID, not by generic “Note” titles or ordinal position. This avoids inventing correspondence between unrelated callouts; different note IDs appear on separate rows and may still repeat wording across rows.</p>
    <p>Exact groups require reference-expanded body structure and link targets to match. Nonexact pair labels reuse the earlier deterministic audit: high lexical overlap with changed fields/links is a variant candidate; an identical internal XML block of at least 12 tokens supports partial overlap; remaining pairs stay related/unresolved. No semantic equivalence is confirmed, no LLM/model inference is run, and similarity edges are never transitively merged. Pair labels apply only within aligned rows; cross-row note duplicates are listed in the companion narrative.</p>
    <p><a href="ANALYSIS.md">Narrative and cross-row note matches</a> · <a href="section_summary.csv">Row narratives</a> · <a href="node_inventory.csv">All nodes and full text</a> · <a href="pair_evidence.csv">All pair evidence</a> · <a href="validation.json">Count validation</a></p><p>'''+H(f"{len(documents)} documents · {len(occurrences)} node occurrences · {len(families)} comparison rows · {sum(n['empty'] for n in occurrences)} empty headings · {len(copied)} packaged raw files")+'''</p><table><thead><tr><th>Section / node</th><th>Exact-content grouping</th><th>Similarities, differences and reuse interpretation</th></tr></thead><tbody>'''+''.join(page_rows)+'''</tbody></table></body></html>'''
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
