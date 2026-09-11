# KMT DITA 1 Bodies and All Notes Deduplication Summary

This report records duplicate counts and percentages for the new `kmt_dita 1.zip` dataset, with English and French processed separately.

Rows whose node text contains the word `snippet` or the French equivalent `extrait/extraits` have been removed from the cleaned CSV outputs because these hidden web-page snippets are not intended dataset content.

## Counting method

- Unit of comparison: text-node pairs.
- Pair-based percentages are calculated over all cleaned candidate pairs in `kg_pair_classifications.csv`, including pairs later classified as `independent`.
- File/node-based percentages are calculated over unique files/nodes in cleaned `kg_nodes.csv`, not over candidate pairs.
- Duplicate clusters are built from confirmed `duplicate/semantic duplicate` pairs. If node A duplicates node B, and node B duplicates node C, then A/B/C share one `cluster_id`.

## Overall pair-based results

| Dataset | Nodes | Comparable nodes | Candidate pairs | Duplicate / semantic duplicate pairs | Duplicate % of candidates | One passage included in another | Duplicate + included pairs | Duplicate + included % | Borderline pairs | LLM-reviewed pairs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| KMT bodies EN | 8,394 | 8,264 | 47,682 | 7,034 | 14.75% | 1,477 | 8,511 | 17.85% | 21,744 | 21,744 |
| KMT bodies FR | 8,403 | 8,303 | 94,338 | 7,038 | 7.46% | 1,662 | 8,700 | 9.22% | 25,738 | 25,738 |
| KMT bodies EN + FR | 16,797 | 16,567 | 142,020 | 14,072 | 9.91% | 3,139 | 17,211 | 12.12% | 47,482 | 47,482 |
| KMT all_notes EN | 5,771 | 5,771 | 19,957 | 9,980 | 50.01% | 234 | 10,214 | 51.18% | 9,692 | 9,692 |
| KMT all_notes FR | 5,787 | 5,787 | 33,432 | 9,721 | 29.08% | 328 | 10,049 | 30.06% | 18,240 | 18,240 |
| KMT all_notes EN + FR | 11,558 | 11,558 | 53,389 | 19,701 | 36.90% | 562 | 20,263 | 37.95% | 27,932 | 27,932 |
| KMT bodies + all_notes total | 28,355 | 28,125 | 195,409 | 33,773 | 17.28% | 3,701 | 37,474 | 19.18% | 75,414 | 75,414 |

## Duplicate cluster / note-level results

This is the client-facing node-level view. It answers:

```text
# nodes in duplicate clusters / # total nodes
```

| Dataset | Total nodes | Nodes in duplicate clusters | Duplicate-cluster node % | Duplicate clusters | Largest cluster size | Confirmed duplicate pairs |
|---|---:|---:|---:|---:|---:|---:|
| KMT bodies EN | 8,394 | 3,308 | 39.41% | 904 | 82 | 7,034 |
| KMT bodies FR | 8,403 | 3,459 | 41.16% | 908 | 76 | 7,038 |
| KMT bodies EN + FR | 16,797 | 6,767 | 40.29% | 1,812 | 82 | 14,072 |
| KMT all_notes EN | 5,771 | 2,920 | 50.60% | 773 | 64 | 9,980 |
| KMT all_notes FR | 5,787 | 2,979 | 51.48% | 775 | 80 | 9,721 |
| KMT all_notes EN + FR | 11,558 | 5,899 | 51.04% | 1,548 | 80 | 19,701 |
| KMT bodies + all_notes total | 28,355 | 12,666 | 44.67% | 3,360 | 82 | 33,773 |

### Duplicate cluster results by body type

| Dataset | Body type | Total nodes | Nodes in duplicate clusters | Duplicate-cluster node % |
|---|---|---:|---:|---:|
| KMT bodies EN | conbody | 6,461 | 2,413 | 37.35% |
| KMT bodies EN | refbody | 613 | 221 | 36.05% |
| KMT bodies EN | taskbody | 1,320 | 674 | 51.06% |
| KMT bodies FR | conbody | 6,937 | 2,752 | 39.67% |
| KMT bodies FR | refbody | 617 | 208 | 33.71% |
| KMT bodies FR | taskbody | 849 | 499 | 58.78% |
| KMT all_notes EN | conbody | 5,771 | 2,920 | 50.60% |
| KMT all_notes FR | conbody | 5,787 | 2,979 | 51.48% |

## Results by body type

Mixed body-type rows such as `conbody + refbody` mean the candidate pair spans two different body tags.

### KMT bodies EN

| Body type pairing | Candidate pairs | Duplicate pairs | Duplicate % | Included pairs | Duplicate + included pairs | Duplicate + included % |
|---|---:|---:|---:|---:|---:|---:|
| conbody | 28,674 | 5,489 | 19.14% | 1,067 | 6,556 | 22.86% |
| conbody + refbody | 1,527 | 61 | 3.99% | 59 | 120 | 7.86% |
| conbody + taskbody | 4,398 | 154 | 3.50% | 145 | 299 | 6.80% |
| refbody | 2,797 | 523 | 18.70% | 119 | 642 | 22.95% |
| refbody + taskbody | 55 | 6 | 10.91% | 2 | 8 | 14.55% |
| taskbody | 10,231 | 801 | 7.83% | 85 | 886 | 8.66% |

### KMT bodies FR

| Body type pairing | Candidate pairs | Duplicate pairs | Duplicate % | Included pairs | Duplicate + included pairs | Duplicate + included % |
|---|---:|---:|---:|---:|---:|---:|
| conbody | 75,011 | 5,901 | 7.87% | 1,361 | 7,262 | 9.68% |
| conbody + refbody | 2,469 | 81 | 3.28% | 90 | 171 | 6.93% |
| conbody + taskbody | 4,491 | 67 | 1.49% | 58 | 125 | 2.78% |
| refbody | 3,066 | 391 | 12.75% | 110 | 501 | 16.34% |
| refbody + taskbody | 35 | 2 | 5.71% | 2 | 4 | 11.43% |
| taskbody | 9,266 | 596 | 6.43% | 41 | 637 | 6.87% |

### KMT all_notes EN

| Body type pairing | Candidate pairs | Duplicate pairs | Duplicate % | Included pairs | Duplicate + included pairs | Duplicate + included % |
|---|---:|---:|---:|---:|---:|---:|
| conbody | 19,957 | 9,980 | 50.01% | 234 | 10,214 | 51.18% |

### KMT all_notes FR

| Body type pairing | Candidate pairs | Duplicate pairs | Duplicate % | Included pairs | Duplicate + included pairs | Duplicate + included % |
|---|---:|---:|---:|---:|---:|---:|
| conbody | 33,432 | 9,721 | 29.08% | 328 | 10,049 | 30.06% |

## Other relationship counts

| Dataset | Independent | Conflicting information | LLM-reviewed borderline pairs | LLM not reviewed borderline pairs | LLM API errors |
|---|---:|---:|---:|---:|---:|
| KMT bodies EN | 38,174 | 997 | 21,744 | 0 | 0 |
| KMT bodies FR | 84,492 | 1,146 | 25,738 | 0 | 0 |
| KMT all_notes EN | 7,239 | 2,504 | 9,692 | 0 | 0 |
| KMT all_notes FR | 20,178 | 3,205 | 18,240 | 0 | 0 |

## Source files

- KMT bodies EN full classification CSV: `outputs/kmt_dita_1_body_en_kg_pipeline/kg_pair_classifications.csv`
- KMT bodies EN full classification CSV with clusters: `outputs/kmt_dita_1_body_en_kg_pipeline/kg_pair_classifications_with_clusters.csv`
- KMT bodies EN non-independent matches CSV: `outputs/kmt_dita_1_body_en_kg_pipeline/kg_deduplication_matches.csv`
- KMT bodies EN non-independent matches CSV with clusters: `outputs/kmt_dita_1_body_en_kg_pipeline/kg_deduplication_matches_with_clusters.csv`
- KMT bodies EN node cluster CSV: `outputs/kmt_dita_1_body_en_kg_pipeline/kg_node_duplicate_clusters.csv`
- KMT bodies FR full classification CSV: `outputs/kmt_dita_1_body_fr_kg_pipeline/kg_pair_classifications.csv`
- KMT bodies FR full classification CSV with clusters: `outputs/kmt_dita_1_body_fr_kg_pipeline/kg_pair_classifications_with_clusters.csv`
- KMT bodies FR non-independent matches CSV: `outputs/kmt_dita_1_body_fr_kg_pipeline/kg_deduplication_matches.csv`
- KMT bodies FR non-independent matches CSV with clusters: `outputs/kmt_dita_1_body_fr_kg_pipeline/kg_deduplication_matches_with_clusters.csv`
- KMT bodies FR node cluster CSV: `outputs/kmt_dita_1_body_fr_kg_pipeline/kg_node_duplicate_clusters.csv`
- KMT all_notes EN full classification CSV: `outputs/kmt_dita_1_all_notes_en_kg_pipeline/kg_pair_classifications.csv`
- KMT all_notes EN full classification CSV with clusters: `outputs/kmt_dita_1_all_notes_en_kg_pipeline/kg_pair_classifications_with_clusters.csv`
- KMT all_notes EN non-independent matches CSV: `outputs/kmt_dita_1_all_notes_en_kg_pipeline/kg_deduplication_matches.csv`
- KMT all_notes EN non-independent matches CSV with clusters: `outputs/kmt_dita_1_all_notes_en_kg_pipeline/kg_deduplication_matches_with_clusters.csv`
- KMT all_notes EN node cluster CSV: `outputs/kmt_dita_1_all_notes_en_kg_pipeline/kg_node_duplicate_clusters.csv`
- KMT all_notes FR full classification CSV: `outputs/kmt_dita_1_all_notes_fr_kg_pipeline/kg_pair_classifications.csv`
- KMT all_notes FR full classification CSV with clusters: `outputs/kmt_dita_1_all_notes_fr_kg_pipeline/kg_pair_classifications_with_clusters.csv`
- KMT all_notes FR non-independent matches CSV: `outputs/kmt_dita_1_all_notes_fr_kg_pipeline/kg_deduplication_matches.csv`
- KMT all_notes FR non-independent matches CSV with clusters: `outputs/kmt_dita_1_all_notes_fr_kg_pipeline/kg_deduplication_matches_with_clusters.csv`
- KMT all_notes FR node cluster CSV: `outputs/kmt_dita_1_all_notes_fr_kg_pipeline/kg_node_duplicate_clusters.csv`
- Duplicate cluster summary CSV: `outputs/kmt_dita_1_duplicate_cluster_summary.csv`
- Snippet filter report CSV: `outputs/kmt_dita_1_snippet_filter_report.csv`
