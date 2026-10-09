"""Supplement the reproducible ORT audit with dependency and FrameNet evidence.

All analysis stays local. FrameNet checks use the existing English rule mapper,
explicitly disabling BERT. Coverage is not annotation accuracy or pair precision.
"""
import csv
import hashlib
import json
import itertools
import re
from collections import Counter, defaultdict
from pathlib import Path

from audit_ort_knowledge_reuse import (OUT, ROOT, AuditResolver, RiskScanner,
    digest, element_text, structure, write_csv, xml_local_name)
from hybrid_frame_mapper import hybrid_frame_mapping


def read(name):
    with (OUT / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def frame_row(text, path, label):
    result = hybrid_frame_mapping(text, 0, use_bert=False)
    elements = result['frameElements'] if result else {}
    filled = {k:v['text'] for k,v in elements.items() if v.get('text')}
    return {'case':label, 'source_path':path, 'sentence':text,
            'frame':result['frame'] if result else '',
            'trigger':result['trigger'] if result else '',
            'filled_roles':json.dumps(filled,ensure_ascii=False),
            'missing_configured_roles':'|'.join(k for k,v in elements.items() if not v.get('text')),
            'configured_roles':len(elements), 'filled_role_count':len(filled),
            'domain_slots':json.dumps(RiskScanner.slots(text),ensure_ascii=False),
            'official_lexical_unit_found':bool(result and result['frameNet']['target']),
            'execution':'existing English rules; BERT disabled; no LLM',
            'interpretation':'coverage only; role names validated against FrameNet, extracted arguments not validated'}


def main():
    sections = read('section_inventory.csv')
    by_path = {s['path']:s for s in sections}
    # Hash-selected distinct first sentences: reproducible coverage probe, not a
    # random accuracy evaluation or balanced sample of all sentence positions.
    pool = {}
    for s in sections:
        if s['language'] != 'en':
            continue
        sentence = re.split(r'(?<=[.!?])\s+', s['resolved_text'])[0]
        if len(sentence.split()) >= 8:
            pool.setdefault(sentence,s['path'])
    sample = sorted(pool,key=lambda t:hashlib.sha256(t.encode()).hexdigest())[:240]
    frames = [frame_row(t,pool[t],'hash_selected_first_sentence') for t in sample]
    write_csv(OUT/'framenet_coverage_probe.csv',frames)
    examples = []
    wanted = [
        ('en_EN/activity/access_code/detailed_security_check.dita','Representatives are identified'),
        ('en_EN/task/envoyer-code-acces-issue-access-code-curam/detailed_security_check.dita','Representatives are identified'),
        ('en_EN/task/replacing_ac/detailed_security_check.dita','Representatives are identified'),
    ]
    for path,phrase in wanted:
        for sentence in re.split(r'(?<=[.!?])\s+',by_path[path]['resolved_text']):
            if phrase in sentence:
                examples.append(frame_row(sentence,path,'access_code_system_difference'))
    for s in sections:
        if s['language']=='en' and ('/roe_rfs/' in s['path'] or '/roe_quit/' in s['path']) and 'linking' in s['path']:
            for sentence in re.split(r'(?<=[.!?])\s+',s['resolved_text']):
                if 'The system verifies whether' in sentence or 'Non-complex agent must review' in sentence:
                    examples.append(frame_row(sentence,s['path'],'automatic_vs_manual_matching'))
    write_csv(OUT/'framenet_document_examples.csv',examples)
    mapped=[r for r in frames if r['frame']]
    frame_summary={'sample_size':len(frames),'eligible_unique_first_sentences':len(pool),
                   'mapped_sentences':len(mapped),'unmapped_sentences':len(frames)-len(mapped),
                   'mapped_with_no_extracted_roles':sum(r['filled_role_count']==0 for r in mapped),
                   'mapped_missing_at_least_one_configured_role':sum(r['filled_role_count']<r['configured_roles'] for r in mapped),
                   'mapped_without_official_lexical_unit':sum(not r['official_lexical_unit_found'] for r in mapped),
                   'frame_counts':dict(Counter(r['frame'] for r in mapped)),
                   'scope':'English only, 240 SHA256-selected distinct first sentences >=8 whitespace words; coverage, NOT accuracy; BERT disabled'}

    # Existing common references may themselves be duplicate physical files.
    resolver=AuditResolver(ROOT)
    shared=read('already_shared_reference_sources.csv')
    source_groups=defaultdict(list)
    source_errors=[]
    for row in shared:
        path=ROOT/row['source_path']
        tree=resolver.parse_xml(path)
        body=next((x for x in tree if xml_local_name(x.tag).endswith('body')),None)
        if body is None:
            continue
        errors=[]
        expanded=resolver.expand(body,path,errors)
        if errors:
            source_errors.append({'path':row['source_path'],'errors':'|'.join(errors)})
            continue
        key=(row['source_path'].split('/')[0],digest(structure(expanded)))
        source_groups[key].append({**row,'text':element_text(expanded)})
    repeated=[]
    for (lang,key),rows in source_groups.items():
        if len(rows)>1:
            repeated.append({'language':lang,'group_id':key,'physical_sources':len(rows),
                             'reference_occurrences':sum(int(r['map_occurrences']) for r in rows),
                             'words':len(rows[0]['text'].split()),
                             'source_paths':'|'.join(r['source_path'] for r in rows),'text':rows[0]['text']})
    repeated.sort(key=lambda r:-r['reference_occurrences'])
    write_csv(OUT/'duplicate_common_source_files.csv',repeated)
    write_csv(OUT/'common_source_issues.csv',source_errors)

    summaries={}
    queues=[]
    for lang in ('en','fr'):
        pairs=read(lang+'/pair_audit.csv')
        selected=[s for s in sections if s['language']==lang]
        exact=read('exact_section_opportunities.csv')
        exact=[r for r in exact if r['language']==lang]
        # Component closure is NOT assumed to be pairwise equivalence. Report
        # implied but unevaluated links explicitly to expose chaining risk.
        parent={}
        def find(x):
            parent.setdefault(x,x)
            while parent[x]!=x:
                parent[x]=parent[parent[x]]
                x=parent[x]
            return x
        for r in pairs:
            a,b=find(r['path1']),find(r['path2'])
            parent[a]=b
        components=defaultdict(set)
        edges=Counter()
        for x in parent:
            components[find(x)].add(x)
        for r in pairs:
            edges[find(r['path1'])]+=1
        graph=[]
        for key,nodes in components.items():
            possible=len(nodes)*(len(nodes)-1)//2
            graph.append({'language':lang,'sections':len(nodes),'observed_positive_edges':edges[key],
                          'all_pairs_in_component':possible,'pairs_without_audited_positive_edge':possible-edges[key],
                          'source_paths':'|'.join(sorted(nodes))})
        graph.sort(key=lambda r:-r['sections'])
        write_csv(OUT/lang/'positive_graph_components.csv',graph)
        summaries[lang]={
            'sections':len(selected),'publications':len({p for s in selected for p in s['parent_maps'].split('|') if p}),
            'section_types':dict(Counter(s['business_type'] for s in selected)),
            'exact_groups':len(exact),'exact_group_sections':sum(int(r['physical_section_copies']) for r in exact),
            'exact_groups_min40words':sum(int(r['words_per_copy'])>=40 for r in exact),
            'review_tier_groups':sum(r['review_tier']=='substantive_exact_content_review' for r in exact),
            'sections_in_saved_positive_pairs':len({r[k] for r in pairs for k in ('path1','path2')}),
            'exact_surface_nonexact_structure_pairs':sum(r['resolved_surface_equal']=='True' and r['resolved_structure_equal']=='False' for r in pairs),
            'nonexact_pairs_with_any_shared_block':sum(int(r['shared_exact_blocks'])>0 and r['audit_bucket']!='exact_resolved_section' for r in pairs),
            'positive_components':len(graph),'largest_positive_component':{k:v for k,v in graph[0].items() if k!='source_paths'},
            'component_pairs_without_positive_edge':sum(r['pairs_without_audited_positive_edge'] for r in graph),
        }
        memberships=defaultdict(list)
        for row in read('exact_section_group_members.csv'):
            if row['group_id'].startswith(lang+'_'):
                memberships[row['group_id']].append(row)
        expected=set()
        for items in memberships.values():
            for a,b in itertools.combinations(items,2):
                if not (set(a['parent_maps'].split('|')) & set(b['parent_maps'].split('|'))):
                    expected.add(tuple(sorted((a['source_path'],b['source_path']))))
        positives={tuple(sorted((r['path1'],r['path2']))) for r in pairs}
        ids={r['node_id']:r['path'] for r in selected}
        candidates=set()
        input_path=Path('outputs/ort_internal_deduplication')/lang/'pair_classifications.csv'
        with input_path.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                a,b=ids.get(row['item1_node_id']),ids.get(row['item2_node_id'])
                if a and b:
                    candidates.add(tuple(sorted((a,b))))
        summaries[lang]['global_exact_pair_coverage']={
            'eligible_global_exact_pairs':len(expected),
            'in_saved_candidates':len(expected & candidates),
            'in_saved_positive_pairs':len(expected & positives),
            'absent_saved_candidates':len(expected-candidates),
            'candidate_but_not_positive':len((expected&candidates)-positives)}
        write_csv(OUT/lang/'exact_pairs_absent_saved_candidates.csv',[
            {'path1':a,'path2':b,'title1':by_path[a]['title'],'title2':by_path[b]['title'],
             'resolved_words':by_path[a]['resolved_words'],
             'resolved_signature':by_path[a]['resolved_signature']}
            for a,b in sorted(expected-candidates)])
        # Review queue: two examples per bucket and signal, plus the original
        # access-code and RFS examples. This is triage, not a random precision set.
        included=set()
        criteria=[('bucket:'+b,lambda r,b=b:r['audit_bucket']==b) for b in sorted({r['audit_bucket'] for r in pairs})]
        criteria += [('signal:'+f,lambda r,f=f:f in r['review_signals'].split('|')) for f in ('systems','rfs_categories','levels','numbers','negation','inherited_context_difference','document_local_step_reference')]
        for label,predicate in criteria:
            candidates=sorted((r for r in pairs if predicate(r)),key=lambda r:hashlib.sha256((r['path1']+r['path2']).encode()).hexdigest())[:2]
            for r in candidates:
                key=(r['path1'],r['path2'])
                if key not in included:
                    queues.append({**r,'selection_reason':label,'human_content_label':'','human_applicability_decision':'','reviewer_notes':''})
                    included.add(key)
    write_csv(OUT/'review_queue.csv',queues)
    # Give reviewers actual source text alongside the compact statistical brief.
    # Text below is explicitly an expanded-text view; DITA links retain the
    # authoritative table/list structure for inspection.
    cases=[
        ('Access code: FTS versus Cúram',
         'Shared security wording does not erase the system and indicator differences. Review the common statements separately from the system-specific sentence.',[
          'en_EN/activity/access_code/detailed_security_check.dita',
          'en_EN/task/envoyer-code-acces-issue-access-code-curam/detailed_security_check.dita',
          'en_EN/task/replacing_ac/detailed_security_check.dita']),
        ('RFS summary: Quit versus Dismissal',
         'Preserve E–Quit and M–Dismissal as applicability conditions. These are variants, not interchangeable instructions.',[
          'en_EN/task/roe_quit/summary.dita','en_EN/task/roe_dismissal/summary.dita']),
        ('RFS linking: hidden table differences',
         'Raw normalized bodies matched, but expanding conrefs reveals different E/M table values. Six existing internal elements match exactly. A table example difference alone does not prove contradictory policy.',[
          'en_EN/task/roe_quit/linking_the_roe_and_the_matching_period_f71580ff.dita',
          'en_EN/task/roe_dismissal/linking_the_roe_and_the_matching_period_e21c3afb.dita']),
        ('Genuine exact content across activity and task',
         'Both expanded bodies are identical. Task/activity is context, not a reason to forbid comparison. Confirm applicability before proposing shared maintenance.',[
          'en_EN/activity/adj_rfs_review/conditions_for_creating_the_wi.dita',
          'en_EN/task/adj_rfs_review_man_ret/conditions_for_creating_the_wi.dita'])]
    case_text=['# ORT source examples\n\nActual expanded section text from the audited files. This text view flattens lists and tables; use the linked DITA source to inspect their structure. These examples illustrate the method; they are not an unbiased precision sample.\n']
    for title,interpretation,paths in cases:
        case_text.extend(['## '+title,interpretation])
        for path in paths:
            s=by_path[path]
            case_text.extend(['### '+s['title'],
                             f"[Open original DITA source]({(ROOT/path).as_posix()})",f'`{path}`',
                             '**Expanded body:**\n\n'+s['resolved_text']])
    (OUT/'CASE_STUDIES.md').write_text('\n\n'.join(case_text)+'\n',encoding='utf-8')
    result={'languages':summaries,'framenet':frame_summary,
            'duplicate_common_source_groups':len(repeated),
            'physical_common_sources_in_duplicate_groups':sum(r['physical_sources'] for r in repeated),
            'common_source_errors':len(source_errors),'review_queue_pairs':len(queues),
            'external_api_calls':0}
    (OUT/'pattern_summary.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    manifest=[]
    for path in [Path(__file__),Path('audit_ort_knowledge_reuse.py'),
                 Path('hybrid_frame_mapper.py'),Path('framenet_registry.py')]+[
                 Path(f'outputs/ort_internal_deduplication/{lang}/pair_classifications.csv') for lang in ('en','fr')]+[
                 Path(f'outputs/ort_new_dita_kg_pipeline/{lang}/kg_nodes.csv') for lang in ('en','fr')]+[OUT/'section_inventory.csv']:
        with path.open('rb') as stream:
            checksum=hashlib.file_digest(stream,'sha256').hexdigest()
        manifest.append({'path':path.as_posix(),'bytes':path.stat().st_size,'sha256':checksum})
    write_csv(OUT/'input_and_code_manifest.csv',manifest)
    print(json.dumps(result,indent=2,ensure_ascii=True))


if __name__=='__main__':
    main()
