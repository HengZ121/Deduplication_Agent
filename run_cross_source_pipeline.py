import argparse
from pathlib import Path
import pandas as pd
from run_passage_pipeline import encode_passages
from run_kg_pipeline import compact_candidate_pairs, score_candidate_pairs, classify_compact_pairs, detailed_matches

BASE = Path('outputs')
OUT = BASE / 'ort_kmt_cross_deduplication'

def run(lang, kmt_dir, ort_dir, output_dir):
    out = output_dir / lang; out.mkdir(parents=True, exist_ok=True)
    # main() resolves each input to its language-specific directory.
    k = pd.read_csv(kmt_dir / 'kg_nodes.csv', encoding='utf-8-sig')
    o = pd.read_csv(ort_dir / 'kg_nodes.csv', encoding='utf-8-sig')
    k['dataset_source'] = 'KMT'; o['dataset_source'] = 'ORT'
    k['node_id'] = 'KMT:' + k['node_id'].astype(str); o['node_id'] = 'ORT:' + o['node_id'].astype(str)
    nodes = pd.concat([k, o], ignore_index=True)
    nodes['node_index'] = range(len(nodes))
    comparable = nodes[nodes['is_comparable'].astype(bool)].reset_index(drop=True)
    comparable['node_index'] = range(len(comparable))
    emb = encode_passages(comparable, 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', 256)
    c = compact_candidate_pairs(comparable, emb, 0.68, 20, 512, 0)
    src = comparable['dataset_source'].tolist()
    c = c[[src[int(a)] != src[int(b)] for a,b in zip(c.item1_index,c.item2_index)]].reset_index(drop=True)
    scored = score_candidate_pairs(c, comparable, 'cross-encoder/ms-marco-MiniLM-L-6-v2', 256, 1200, output_dir/lang/'scores.dat')
    res = classify_compact_pairs(scored, comparable, 0.995, 0.95)
    nodes.to_csv(out/'cross_nodes.csv', index=False, encoding='utf-8-sig')
    c.to_csv(out/'cross_candidate_pairs.csv', index=False, encoding='utf-8-sig')
    res.to_csv(out/'cross_pair_classifications.csv', index=False, encoding='utf-8-sig')
    detailed_matches(res, comparable).to_csv(out/'cross_deduplication_matches.csv', index=False, encoding='utf-8-sig')
    print(lang, len(nodes), len(c), int(res.is_borderline.sum()))

def main():
    parser = argparse.ArgumentParser(description='Find cross-source KMT–ORT duplicate candidates.')
    parser.add_argument('--kmt-dir', type=Path, default=BASE / 'kmt_dita_1_body_{lang}_kg_pipeline',
                        help='Directory template; use {lang} for the per-language folder.')
    parser.add_argument('--ort-dir', type=Path, default=BASE / 'ort_new_dita_kg_pipeline',
                        help='Directory containing en/ and fr/ node tables, or template with {lang}.')
    parser.add_argument('--output-dir', type=Path, default=OUT)
    args = parser.parse_args()
    # The historical KMT default has language in the directory name; new runs
    # may instead use a parent directory with separate en/ and fr/ children.
    for language in ('en', 'fr'):
        kmt_dir = Path(str(args.kmt_dir).format(lang=language))
        if not (kmt_dir / 'kg_nodes.csv').is_file():
            kmt_dir = args.kmt_dir / language
        ort_dir = args.ort_dir / language
        if not (ort_dir / 'kg_nodes.csv').is_file():
            ort_dir = Path(str(args.ort_dir).format(lang=language))
        run(language, kmt_dir, ort_dir, args.output_dir)


if __name__ == '__main__':
    main()
