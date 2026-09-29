"""Check that collapsed length measurements count groups, not repeated members."""
import unittest
import pandas as pd
from analyze_cluster_word_counts import collapse, compare, GROUPS


class ClusterWordCountTests(unittest.TestCase):
    def setUp(self):
        self.nodes=pd.DataFrame([
            dict(dataset='ORT',subset='en',item_id='cluster:a',cluster_id='a',node_id='1',clustered=True,word_count=10,eligible=True,source_type='task'),
            dict(dataset='ORT',subset='en',item_id='cluster:a',cluster_id='a',node_id='2',clustered=True,word_count=30,eligible=False,source_type='activity'),
            dict(dataset='ORT',subset='en',item_id='single:3',cluster_id='',node_id='3',clustered=False,word_count=40,eligible=True,source_type='task')])

    def test_one_median_per_cluster_and_singleton(self):
        d=collapse(self.nodes)
        self.assertEqual(len(d),2)
        r=d[d.group.eq(GROUPS[0])].iloc[0]
        self.assertEqual(r.word_count,20)
        self.assertEqual(r.member_count,2)
        self.assertFalse(r.eligible)
        self.assertEqual(r.source_type,'activity|task')

    def test_within_type_preserves_members(self):
        d=collapse(self.nodes,within_type=True)
        self.assertEqual(len(d),3)
        self.assertEqual(d.member_count.sum(),3)

    def test_descriptive_probability_and_ratio(self):
        r=compare(collapse(self.nodes),'test','test')
        self.assertEqual(r['probability_cluster_shorter'],1)
        self.assertEqual(r['median_ratio'],.5)


if __name__=='__main__':unittest.main()
