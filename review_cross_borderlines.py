from pathlib import Path
import pandas as pd
from run_kg_pipeline import review_borderline_pairs, detailed_matches
from run_procedure_pipeline import resolve_api_key, DEFAULT_API_KEY_FILE, DEFAULT_MODEL, DEFAULT_LLM_WORKERS

base = Path('outputs/ort_kmt_cross_deduplication')
key, _ = resolve_api_key(DEFAULT_API_KEY_FILE)
for lang in ('en','fr'):
    d = base / lang
    nodes = pd.read_csv(d/'cross_nodes.csv', encoding='utf-8-sig')
    comparable = nodes[nodes['is_comparable'].astype(bool)].reset_index(drop=True)
    comparable['node_index'] = range(len(comparable))
    res = pd.read_csv(d/'cross_pair_classifications.csv', encoding='utf-8-sig')
    res = review_borderline_pairs(res, comparable, key, DEFAULT_MODEL, 2_000_000, DEFAULT_LLM_WORKERS, 60, d/'kg_llm_reviews.jsonl')
    res.to_csv(d/'cross_pair_classifications.csv', index=False, encoding='utf-8-sig')
    detailed_matches(res, comparable).to_csv(d/'cross_deduplication_matches.csv', index=False, encoding='utf-8-sig')
    print(lang, 'borderlines', int(res.is_borderline.sum()), 'final matches', len(detailed_matches(res, comparable)))
