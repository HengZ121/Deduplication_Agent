"""Offline, reference-aware measurement of ORT section reuse opportunities.

This is an audit, not a replacement for production decisions. It reuses saved
retrieval/model scores and the existing DITA resolver. Exact observations,
heuristic triage, and unresolved semantic judgments have separate fields.
No model/API calls occur here. English and French never form cross-language pairs.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import posixpath
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

from profile_ort_sections import business_type, read_csv
from run_procedure_pipeline import DitaTopicResolver, element_text, xml_local_name
from run_passage_pipeline import normalized_passage, word_tokens

csv.field_size_limit(10_000_000)
ROOT = Path('unzipped/ort_new_dita/dita').resolve()
OUT = Path('outputs/ort_knowledge_reuse_audit')
RULE_VERSION = 'ort-reuse-audit-v1'
BUCKETS = ('exact_resolved_section', 'template_variant_candidate', 'partial_overlap_observed',
           'semantic_equivalence_candidate', 'related_or_unresolved', 'unresolved_source')


def norm(text: str) -> str:
    """Whitespace/case normalization preserves slashes, numbers and punctuation."""
    return ' '.join(unicodedata.normalize('NFC', text).split()).casefold()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def write_csv(path: Path, rows: list[dict], columns=None):
    """Write even empty evidence tables so a rerun cannot leave stale evidence."""
    columns = columns or (list(rows[0]) if rows else ['no_records'])
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


class AuditResolver(DitaTopicResolver):
    """Reuse fragment semantics, with cached lexical paths and explicit failures.

    Expanding cloned XML preserves row/step ordering and reference attributes,
    unlike flattening only the text. Cache original XML without modifying it.
    """
    def __init__(self, root):
        super().__init__(root)
        self.repairs = []

    def parse_xml(self, path):
        path = Path(path)
        if path not in self._xml_cache:
            self._xml_cache[path] = ET.parse(path).getroot()
        return self._xml_cache[path]

    def resolve_local_reference(self, current_path, reference):
        raw, _, fragment = reference.partition('#')
        rel = Path(current_path).relative_to(self.dita_root).as_posix()
        target_rel = posixpath.normpath(posixpath.join(posixpath.dirname(rel), unquote(raw))) if raw else rel
        if target_rel.startswith('../') or target_rel.startswith('/'):
            raise ValueError('Reference escapes DITA root: ' + reference)
        target = self.dita_root / target_rel
        if not target.is_file():
            for folder in ('common_notes', 'common_tables'):
                if folder in target.parts:
                    alternative = self.dita_root / rel.split('/')[0] / folder / target.name
                    if alternative.is_file():
                        self.repairs.append({'source': rel, 'reference': reference, 'resolved': alternative.relative_to(self.dita_root).as_posix()})
                        target = alternative
        return target, unquote(fragment)

    def expand(self, node, current_path, errors, active=frozenset()):
        """Return an expanded clone; unresolved/unsupported content is never exact."""
        if node.get('conref'):
            try:
                target, fragment = self.resolve_local_reference(current_path, node.get('conref'))
                key = (str(target), fragment)
                if key in active:
                    raise ValueError('Circular conref')
                source = self.find_fragment(self.parse_xml(target), fragment)
                clone = self.expand(source, target, errors, active | {key})
                clone.tail = node.tail
                return clone
            except (OSError, ValueError, ET.ParseError) as exc:
                errors.append(str(exc))
        clone = ET.Element(xml_local_name(node.tag), dict(node.attrib))
        clone.text, clone.tail = node.text, node.tail
        for attr in ('conkeyref', 'keyref', 'conrefend', 'conaction'):
            if node.get(attr):
                errors.append('Unsupported ' + attr + ': ' + node.get(attr))
        href = node.get('href')
        if href and not urlsplit(href).scheme and not href.startswith('/'):
            try:
                target, frag = self.resolve_local_reference(current_path, href)
                clone.set('href', target.relative_to(self.dita_root).as_posix() + ('#' + frag if frag else ''))
                if target.suffix == '.dita' and not target.is_file():
                    errors.append('Missing linked topic: ' + str(target))
            except ValueError as exc:
                errors.append(str(exc))
        for child in node:
            clone.append(self.expand(child, current_path, errors, active))
        return clone


def structure(node):
    """Ignore local IDs and styling; retain order, cell spans, applicability, links."""
    attrs = {k: v for k, v in node.attrib.items() if k not in ('id', 'class', 'outputclass', 'conref')}
    return [xml_local_name(node.tag), norm(node.text or ''), attrs,
            [[structure(c), norm(c.tail or '')] for c in node]]


class RiskScanner:
    """Conservative review signals, not automatic contradiction judgments."""
    systems = re.compile(r'\b(?:FTS|ETI|NWS|SNT|RCM|SRE|IPOC|COPA|WECS|SIEW|C[uú]ram)\b', re.I)
    codes = re.compile(r'\b([A-Z])\s*[-–—]\s*(Quit|Dismissal|Leave of absence|Other|Mandatory retirement|Return to school|Strike or lockout|Départ volontaire|Congédiement|Autre|Congé|Retraite obligatoire|Retour aux études|Grève ou lock-out)\b', re.I)
    levels = re.compile(r'\b(?:level|niveau)\s*([12])\b', re.I)
    jumps = re.compile(r'\b(?:go\s+(?:to\s+)?step|(?:aller|allez|passez)\s+à\s+l[’\']étape)\s*\d+', re.I)
    negations = re.compile(r'\b(?:not|never|no|pas|jamais|aucun|aucune)\b', re.I)
    numbers = re.compile(r'(?<!\w)\d+(?:[.,/]\d+)*%?\b')

    @classmethod
    def slots(cls, text):
        return {
            'systems': tuple(sorted({norm(m.group()).replace('ú', 'u') for m in cls.systems.finditer(text)})),
            'rfs_categories': tuple(sorted({norm(m.group()) for m in cls.codes.finditer(text)})),
            'levels': tuple(sorted({m.group(1) for m in cls.levels.finditer(text)})),
            'numbers': tuple(sorted(set(cls.numbers.findall(text)))),
            'negation': bool(cls.negations.search(text)),
        }

    @classmethod
    def changed(cls, a, b):
        left, right = cls.slots(a), cls.slots(b)
        return [key for key in left if left[key] != right[key]]


@dataclass
class Section:
    node_id: str
    path: str
    title: str
    language: str
    raw: str
    resolved: str
    signature: str
    tokens: frozenset
    blocks: dict
    parents: list
    errors: list = field(default_factory=list)
    has_jumps: bool = False
    has_conref: bool = False
    link_targets: tuple = ()
    context: tuple = ()
    raw_equal_key: str = ''


class MapIndex:
    def __init__(self, resolver):
        self.resolver = resolver
        self.parents = defaultdict(list)
        self.documents = []
        self.shared_occurrences = []
        self.issues = []

    def load(self, branch):
        for kind in ('task', 'activity'):
            for path in sorted((self.resolver.dita_root / branch / kind).rglob('*.ditamap')):
                rel = path.relative_to(self.resolver.dita_root).as_posix()
                tree = self.resolver.parse_xml(path)
                title = element_text(tree.find('title'))
                doc = {'map_path': rel, 'title': title, 'business_type': kind}
                self.documents.append(doc)

                def visit(parent, headings):
                    for ref in parent:
                        if xml_local_name(ref.tag) != 'topicref':
                            continue
                        href = ref.get('href', '')
                        if not href or urlsplit(href).scheme:
                            continue
                        try:
                            target, _ = self.resolver.resolve_local_reference(path, href)
                            topic = self.resolver.parse_xml(target)
                        except (OSError, ValueError, ET.ParseError) as exc:
                            self.issues.append({'map': rel, 'reference': href, 'error': str(exc)})
                            continue
                        target_rel = target.relative_to(self.resolver.dita_root).as_posix()
                        topic_title = element_text(topic.find('title'))
                        occurrence = {**doc, 'heading_path': ' > '.join(headings), 'section_path': target_rel}
                        self.parents[target_rel].append(occurrence)
                        if '/common_notes/' in target_rel or '/common_tables/' in target_rel:
                            self.shared_occurrences.append(occurrence)
                        visit(ref, headings + [topic_title])
                visit(tree, [])


class ReuseAudit:
    def __init__(self, root=ROOT, output=OUT, minimum_block_words=12):
        self.root, self.output = Path(root), Path(output)
        self.minimum_block_words = minimum_block_words
        self.resolver = AuditResolver(self.root)
        self.index = MapIndex(self.resolver)
        self.sections = {}
        self.blocks = {}

    def make_section(self, row, language):
        relative = row['article_path']
        path = self.root / relative
        tree = self.resolver.parse_xml(path)
        body = next(c for c in tree if xml_local_name(c.tag).endswith('body'))
        errors = []
        expanded = self.resolver.expand(body, path, errors)
        resolved = element_text(expanded)
        blocks = {}
        # These are evidence spans inside existing sections, not new dataset chunks.
        def collect(node, xpath):
            tag = xml_local_name(node.tag)
            candidate = tag in ('p', 'cmd', 'shortdesc', 'table', 'simpletable') or (tag == 'li' and not any(xml_local_name(c.tag) in ('p','li','ul','ol') for c in node.iter() if c is not node))
            if candidate:
                value = element_text(node)
                words = len(word_tokens(value))
                if words >= self.minimum_block_words:
                    key = digest([language, structure(node)])
                    blocks[key] = {'text': value, 'words': words, 'element': xpath, 'tag': tag}
                    self.blocks.setdefault(key, {'text': value, 'words': words, 'tag': tag, 'sections': set()})['sections'].add(relative)
                return  # Avoid counting nested overlapping subspans twice.
            for i, child in enumerate(node):
                collect(child, xpath + '/' + xml_local_name(child.tag) + f'[{i+1}]')
        collect(expanded, '/' + xml_local_name(body.tag))
        parents = self.index.parents[relative]
        context = []
        for parent in parents:
            slots = RiskScanner.slots(parent['title'] + ' ' + parent['heading_path'])
            context.append((slots['systems'], slots['rfs_categories'], slots['levels']))
        return Section('ORT:' + row['node_id'], relative, row['article_title'], language,
                       row['text'], resolved, digest(structure(expanded)), frozenset(word_tokens(resolved)), blocks, parents,
                       errors, bool(RiskScanner.jumps.search(resolved)), any(x.get('conref') for x in body.iter()),
                       tuple(sorted(x.get('href') for x in expanded.iter() if x.get('href'))),
                       tuple(sorted(set(context))), normalized_passage(row['text']))

    @staticmethod
    def assess_pair(a, b):
        """Mutually exclusive audit buckets; evidence flags may overlap.

        The precedence is source completeness, exact, high-overlap changed
        slots/references, exact internal overlap, model-suggested equivalence,
        unresolved. None of the candidate buckets assert semantic truth.
        """
        union = a.tokens | b.tokens
        overlap = len(a.tokens & b.tokens) / len(union) if union else 0.0
        changes = RiskScanner.changed(a.resolved, b.resolved)
        if a.link_targets != b.link_targets:
            changes.append('reference_targets')
        if norm(a.resolved) == norm(b.resolved) and a.signature != b.signature:
            changes.append('structure_or_reference')
        shared = set(a.blocks) & set(b.blocks)
        context_difference = a.context != b.context
        flags = changes + (['inherited_context_difference'] if context_difference else [])
        if a.has_jumps or b.has_jumps:
            flags.append('document_local_step_reference')
        common = sorted(shared, key=lambda k: (-a.blocks[k]['words'], k))
        base = {'lexical_jaccard_resolved': round(overlap, 6), 'review_signals': '|'.join(flags),
                'shared_exact_blocks': len(shared), 'longest_shared_block_words': a.blocks[common[0]]['words'] if common else 0,
                'example_shared_block': a.blocks[common[0]]['text'] if common else '',
                'example_element1': a.blocks[common[0]]['element'] if common else '',
                'example_element2': b.blocks[common[0]]['element'] if common else '',
                'raw_normalized_equal': a.raw_equal_key == b.raw_equal_key,
                'resolved_legacy_normalized_equal': normalized_passage(a.resolved) == normalized_passage(b.resolved),
                'either_has_conref': a.has_conref or b.has_conref,
                'resolved_surface_equal': norm(a.resolved) == norm(b.resolved),
                'resolved_structure_equal': a.signature == b.signature,
                'inherited_context_difference': context_difference}
        if a.errors or b.errors:
            return 'unresolved_source', base
        if a.signature == b.signature:
            return 'exact_resolved_section', base
        if overlap >= 0.80 and changes:
            return 'template_variant_candidate', base
        if shared:
            return 'partial_overlap_observed', base
        # Semantic equivalence is never established by this deterministic audit.
        if overlap >= 0.72 and not changes and not context_difference:
            return 'semantic_equivalence_candidate', base
        return 'related_or_unresolved', base

    def run_language(self, lang):
        started = time.monotonic()
        self.index.load('en_EN' if lang == 'en' else 'fr_FR')
        raw_nodes = read_csv(f'outputs/ort_new_dita_kg_pipeline/{lang}/kg_nodes.csv')
        selected = [r for r in raw_nodes if business_type(r['article_path']) in ('task','activity')]
        print(f'{lang}: expanding {len(selected)} existing section bodies', flush=True)
        for row in selected:
            section = self.make_section(row, lang)
            self.sections[section.node_id] = section
        results, counts, flags, strata = [], Counter(), Counter(), Counter()
        saved = Counter()
        omitted = Counter()
        seen = set()
        for row in read_csv(f'outputs/ort_internal_deduplication/{lang}/pair_classifications.csv'):
            a, b = self.sections.get(row['item1_node_id']), self.sections.get(row['item2_node_id'])
            if not a or not b:
                omitted['outside_task_activity'] += 1
                continue
            amap = {p['map_path'] for p in a.parents}
            bmap = {p['map_path'] for p in b.parents}
            if not amap or not bmap:
                omitted['missing_parent'] += 1
                continue
            if amap & bmap:
                omitted['shared_parent_document'] += 1
                continue
            key = tuple(sorted((a.node_id, b.node_id)))
            if key in seen:
                omitted['repeated_pair'] += 1
                continue
            seen.add(key)
            saved[row['final_relationship_type']] += 1
            if row['final_relationship_type'] != 'duplicate/semantic duplicate':
                continue
            bucket, evidence = self.assess_pair(a,b)
            # This bucket also requires the saved high model score. Do not imply
            # lexical overlap alone is sufficient, even for a candidate label.
            if bucket == 'semantic_equivalence_candidate' and (float(row['cross_encoder_score']) < .995 or float(row['embedding_similarity']) < .90):
                bucket = 'related_or_unresolved'
            counts[bucket] += 1
            pair_type = ' / '.join(sorted((business_type(a.path), business_type(b.path))))
            strata[(pair_type,bucket)] += 1
            flags.update(evidence['review_signals'].split('|') if evidence['review_signals'] else [])
            results.append({'language':lang,'node1':a.node_id,'node2':b.node_id,'path1':a.path,'path2':b.path,
                            'title1':a.title,'title2':b.title,'document1':a.parents[0]['title'],'document2':b.parents[0]['title'],
                            'parent_maps1':'|'.join(sorted(amap)),'parent_maps2':'|'.join(sorted(bmap)),
                            'pair_type':pair_type,'audit_bucket':bucket,'saved_relationship':row['final_relationship_type'],
                            'saved_cross_score':row['cross_encoder_score'],'saved_embedding':row['embedding_similarity'],
                            **evidence,'source_issues1':'|'.join(a.errors),'source_issues2':'|'.join(b.errors)})
        folder = self.output / lang
        folder.mkdir(parents=True, exist_ok=True)
        write_csv(folder/'pair_audit.csv',results)
        denominator = sum(counts.values())
        distribution = [{'language':lang,'bucket':b,'pair_count':counts[b],'denominator':denominator,'percent':round(100*counts[b]/denominator,3)} for b in BUCKETS]
        write_csv(folder/'type_distribution.csv',distribution)
        write_csv(folder/'type_by_document_pair.csv',[{'pair_type':k[0],'bucket':k[1],'count':v} for k,v in sorted(strata.items())])
        write_csv(folder/'review_signal_counts.csv',[{'signal':k,'pair_count':v,'denominator':denominator,'percent':round(v*100/denominator,3)} for k,v in flags.most_common()])
        summary = {'language':lang,'section_bodies':len(selected),'saved_cross_document_candidates':sum(saved.values()),
                   'saved_candidate_relationships':dict(saved),'audited_duplicate_pairs':denominator,'buckets':dict(counts),
                   'excluded_saved_pairs':dict(omitted),'signals_nonexclusive':dict(flags),
                   'shared_exact_block_in_nonexact_pairs':sum(r['shared_exact_blocks']>0 and r['audit_bucket']!='exact_resolved_section' for r in results),
                   'raw_equal_but_expanded_surface_different':sum(r['raw_normalized_equal'] and not r['resolved_surface_equal'] for r in results),
                   'raw_equal_but_expanded_legacy_normalized_different':sum(r['raw_normalized_equal'] and not r['resolved_legacy_normalized_equal'] for r in results),
                   'raw_equal_conref_present_expanded_legacy_different':sum(r['raw_normalized_equal'] and r['either_has_conref'] and not r['resolved_legacy_normalized_equal'] for r in results),
                   'raw_equal_but_structure_or_refs_different':sum(r['raw_normalized_equal'] and not r['resolved_structure_equal'] for r in results),
                   'seconds':round(time.monotonic()-started,2)}
        (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        print(json.dumps(summary),flush=True)
        return summary

    def opportunities(self):
        """Global exact groups do not depend on nearest-neighbor pair sampling."""
        groups = defaultdict(list)
        by_path = {s.path:s for s in self.sections.values()}
        inventory = []
        for s in self.sections.values():
            groups[(s.language,s.signature)].append(s)
            inventory.append({'node_id':s.node_id,'path':s.path,'language':s.language,'business_type':business_type(s.path),
                              'title':s.title,'parent_maps':'|'.join(p['map_path'] for p in s.parents),'resolved_words':len(word_tokens(s.resolved)),
                              'raw_characters':len(s.raw),'resolved_signature':s.signature,'context':json.dumps(s.context,ensure_ascii=False),
                              'has_conref':s.has_conref,'has_step_jump':s.has_jumps,'source_issues':'|'.join(s.errors),
                              'resolved_text':s.resolved})
        write_csv(self.output/'section_inventory.csv',inventory)
        exact, members = [], []
        for (lang,key), items in groups.items():
            docs = {p['map_path'] for s in items for p in s.parents}
            if len(items)<2 or len(docs)<2:
                continue
            if any(s.errors for s in items):
                continue
            words = len(word_tokens(items[0].resolved))
            contexts = {s.context for s in items}
            jumps = any(s.has_jumps for s in items)
            priority = words * (len(items)-1)
            tier = 'substantive_exact_content_review' if words>=40 and not jumps and len(contexts)==1 else 'scope_dependency_or_short_text_review'
            exact.append({'group_id':lang+'_'+key,'language':lang,'physical_section_copies':len(items),'parent_documents':len(docs),
                          'words_per_copy':words,'repeated_word_instances':priority,'different_context_signatures':len(contexts),
                          'has_step_jump':jumps,'review_tier':tier,'representative_title':items[0].title,'representative_path':items[0].path,
                          'text':items[0].resolved})
            for s in items:
                members.append({'group_id':lang+'_'+key,'source_path':s.path,'document_titles':'|'.join(p['title'] for p in s.parents),'parent_maps':'|'.join(p['map_path'] for p in s.parents),'context':json.dumps(s.context,ensure_ascii=False)})
        exact.sort(key=lambda r:(r['review_tier']!='substantive_exact_content_review',-r['repeated_word_instances']))
        write_csv(self.output/'exact_section_opportunities.csv',exact)
        write_csv(self.output/'exact_section_group_members.csv',members)
        blocks = []
        for key, block in self.blocks.items():
            paths = block['sections']
            docs = {p['map_path'] for path in paths for p in by_path[path].parents}
            if len(paths)<2 or len(docs)<2:
                continue
            language = by_path[next(iter(paths))].language
            blocks.append({'block_id':key,'language':language,'element_kind':block['tag'],'words':block['words'],
                           'physical_sections':len(paths),'parent_documents':len(docs),'repeated_word_instances':block['words']*(len(paths)-1),
                           'source_paths':'|'.join(sorted(paths)),'text':block['text']})
        blocks.sort(key=lambda r:-r['repeated_word_instances'])
        write_csv(self.output/'repeated_internal_spans.csv',blocks)
        shared = defaultdict(list)
        for occurrence in self.index.shared_occurrences:
            shared[occurrence['section_path']].append(occurrence)
        shared_rows = [{'source_path':p,'map_occurrences':len(o),'distinct_parent_documents':len({x['map_path'] for x in o})} for p,o in shared.items()]
        shared_rows.sort(key=lambda r:-r['distinct_parent_documents'])
        write_csv(self.output/'already_shared_reference_sources.csv',shared_rows)
        write_csv(self.output/'reference_repairs.csv',self.resolver.repairs)
        write_csv(self.output/'map_issues.csv',self.index.issues)
        summary = {'exact_section_groups':len(exact),'physical_sections_in_exact_groups':sum(r['physical_section_copies'] for r in exact),
                   'redundant_physical_copies_upper_bound':sum(r['physical_section_copies']-1 for r in exact),
                   'substantive_review_groups':sum(r['review_tier']=='substantive_exact_content_review' for r in exact),
                   'internal_exact_span_groups':len(blocks),'already_shared_sources':len(shared_rows),
                   'already_shared_sources_in_multiple_documents':sum(r['distinct_parent_documents']>1 for r in shared_rows),
                   'shared_reference_occurrences':len(self.index.shared_occurrences),'map_issues':len(self.index.issues),
                   'sections_with_unresolved_source':sum(bool(s.errors) for s in self.sections.values()),
                   'note':'Exact groups and internal span groups overlap. Do not add their repeated-word counts. Exact content does not certify universal applicability.'}
        (self.output/'opportunity_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--languages',nargs='+',default=['en','fr'],choices=['en','fr'])
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    audit=ReuseAudit()
    summaries=[audit.run_language(lang) for lang in args.languages]
    opportunities=audit.opportunities()
    metadata={'rule_version':RULE_VERSION,'languages':summaries,'opportunities':opportunities,
              'scope':'ORT task/activity English en_EN and/or French fr_FR. Same-language, distinct-parent saved positive pairs.',
              'minimum_exact_internal_span_words':audit.minimum_block_words,
              'pair_denominator':'Saved unique cross-document duplicate/semantic-duplicate pairs, not every possible pair.',
              'semantic_equivalence_status':'Candidates only. No confirmed paraphrase count is inferred.',
              'external_llm_calls':0,'new_embedding_or_cross_encoder_inference':False}
    (OUT/'run_summary.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps(opportunities,indent=2),flush=True)


if __name__=='__main__':
    main()
