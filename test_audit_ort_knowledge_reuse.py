"""Regression checks for observed ORT failure modes and counting semantics."""
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from audit_ort_knowledge_reuse import AuditResolver, ReuseAudit, RiskScanner, Section, digest, norm, structure
from run_passage_pipeline import normalized_passage, word_tokens


def section(text, *, signature=None, context=(), errors=None, blocks=None, links=()):
    return Section('id','en_EN/task/sample/a.dita','Title','en',text,text,
                   signature or digest(text),frozenset(word_tokens(text)),blocks or {},[],
                   errors or [],False,False,links,context,normalized_passage(text))


class ReuseAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_root=(Path(__file__).parent/'test_fixtures'/'ort_reuse_audit').resolve()
    def test_system_change_cannot_be_exact_or_semantic_equivalence(self):
        prefix='A detailed security check must be conducted with the client before providing information or issuing an access code. '
        a=section(prefix+'Representatives are identified in FTS with the indicator REP.')
        b=section(prefix+'Representatives are identified in Cúram with the indicator REP.')
        bucket,e=ReuseAudit.assess_pair(a,b)
        self.assertEqual(bucket,'template_variant_candidate')
        self.assertIn('systems',e['review_signals'])

    def test_exact_content_survives_parent_context_difference(self):
        text='When a work item is received, the agent reviews the information on file.'
        a=section(text,context=(((),(),('1',)),))
        b=section(text,context=(((),(),('2',)),))
        bucket,e=ReuseAudit.assess_pair(a,b)
        self.assertEqual(bucket,'exact_resolved_section')
        self.assertTrue(e['inherited_context_difference'])

    def test_missing_source_blocks_exact_acceptance(self):
        a=section('Identical body with missing table',errors=['Missing table'])
        b=section('Identical body with missing table')
        self.assertEqual(ReuseAudit.assess_pair(a,b)[0],'unresolved_source')

    def test_meaningful_indicator_punctuation_survives_normalization(self):
        self.assertNotEqual(norm('FTS /REP/'),norm('FTS REP'))

    def test_different_link_targets_are_a_review_signal(self):
        text='The officer must read the instructions in the following Note before continuing.'
        a=section(text,signature='a',links=('common_notes/a.dita',))
        b=section(text,signature='b',links=('common_notes/b.dita',))
        bucket,e=ReuseAudit.assess_pair(a,b)
        self.assertEqual(bucket,'template_variant_candidate')
        self.assertIn('reference_targets',e['review_signals'])

    def test_exact_internal_evidence_can_support_partial_overlap(self):
        block={'same':{'text':'A shared instruction','words':12,'element':'/conbody/p[1]'}}
        a=section('Shared instruction. First document continues with completely different additional guidance.',blocks=block)
        b=section('Shared instruction. Additional advice about another process appears in this document.',blocks=block)
        self.assertEqual(ReuseAudit.assess_pair(a,b)[0],'partial_overlap_observed')

    def test_french_system_and_level_signals(self):
        a='Dans Cúram, niveau 1, vérifier les informations.'
        b='Dans ETI, niveau 2, vérifier les informations.'
        self.assertEqual(set(RiskScanner.changed(a,b)),{'systems','levels','numbers'})

    def test_conref_tables_change_expanded_signature(self):
        root=self.test_root
        resolver=AuditResolver(root)
        errors=[]
        a=resolver.expand(ET.fromstring('<conbody><p>Same prose</p><table conref="E.dita#r/t"/></conbody>'),root/'a.dita',errors)
        b=resolver.expand(ET.fromstring('<conbody><p>Same prose</p><table conref="M.dita#r/t"/></conbody>'),root/'b.dita',errors)
        self.assertNotEqual(digest(structure(a)),digest(structure(b)))
        self.assertEqual(errors,[])

    def test_conref_cycle_is_recorded(self):
        root=self.test_root
        resolver=AuditResolver(root)
        errors=[]
        resolver.expand(resolver.parse_xml(root/'cycle.dita'),root/'cycle.dita',errors)
        self.assertTrue(any('Circular' in e for e in errors))


if __name__=='__main__':
    unittest.main()
