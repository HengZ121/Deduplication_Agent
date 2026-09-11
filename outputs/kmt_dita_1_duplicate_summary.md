# KMT DITA 1 Bodies and All Notes Deduplication Summary

This report records duplicate counts and percentages for the new `kmt_dita 1.zip` dataset, with English and French processed separately.

It covers:

- KMT body-level content outside notes
- KMT `all_notes` content

## Counting method

- Unit of comparison: text-node pairs.
- Bodies: text extracted from DITA body tags such as `conbody`, `refbody`, and `taskbody`.
- Notes: files under `all_notes`, processed with no chunking; each DITA note file/article is one node. All notes in this dataset are `concept/conbody`.
- Candidate generation: top 20 semantic neighbors per comparable node, then filtered by embedding threshold.
- Cross-encoder thresholds:
  - Duplicate: score >= 0.995
  - Borderline for LLM review: 0.95 <= score < 0.995
- Body results are final LLM-reviewed results.
- Notes results are final LLM-reviewed results.
- Pair-based percentages are calculated over all candidate pairs in `kg_pair_classifications.csv`, including pairs later classified as `independent`.
- `kg_deduplication_matches.csv` contains only non-independent result rows: `duplicate/semantic duplicate`, `one passage included in another`, and `conflicting information`. It excludes `independent` rows, so its row count is smaller than the full candidate-pair count.
- File/node-based percentages are calculated over unique files/nodes in `kg_nodes.csv`, not over candidate pairs.
- Duplicate percentage is calculated as:

```text
duplicate / candidate pairs
```

- Duplicate + included percentage is calculated as:

```text
(duplicate + one passage included in another) / candidate pairs
```

## Overall results

| Dataset | Nodes | Comparable nodes | Candidate pairs | Duplicate / semantic duplicate pairs | Duplicate % of candidates | One passage included in another | Duplicate + included pairs | Duplicate + included % | Borderline pairs | LLM-reviewed pairs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| KMT bodies EN | 9,935 | 9,805 | 74,609 | 21,270 | 28.51% | 2,176 | 23,446 | 31.43% | 28,492 | 28,492 |
| KMT bodies FR | 9,941 | 9,841 | 126,813 | 22,043 | 17.38% | 2,472 | 24,515 | 19.33% | 33,332 | 33,332 |
| KMT bodies EN + FR | 19,876 | 19,646 | 201,422 | 43,313 | 21.50% | 4,648 | 47,961 | 23.81% | 61,824 | 61,824 |
| KMT all_notes EN | 5,787 | 5,787 | 20,022 | 9,996 | 49.93% | 234 | 10,230 | 51.09% | 9,739 | 9,739 |
| KMT all_notes FR | 5,808 | 5,808 | 33,680 | 9,743 | 28.93% | 328 | 10,071 | 29.90% | 18,343 | 18,343 |
| KMT all_notes EN + FR | 11,595 | 11,595 | 53,702 | 19,739 | 36.76% | 562 | 20,301 | 37.80% | 28,082 | 28,082 |
| KMT bodies + all_notes total | 31,471 | 31,241 | 255,124 | 63,052 | 24.71% | 5,210 | 68,262 | 26.76% | 89,906 | 89,906 |

## File/node-based duplicate results

This section counts unique files/nodes that participate in at least one duplicate pair. This is different from the pair-based tables above: a single duplicated file/node can appear in many candidate pairs but is counted once here.

These numbers are based on the latest `kmt_dita_1` output folders. They are not old data. The apparent difference comes from using a different denominator:

- Pair-based tables: duplicate pairs / all candidate pairs.
- File/node-based tables: unique files or nodes that appear in at least one duplicate pair / all files or nodes.

For body-level processing, each row is one extracted body node from a source DITA file. For `all_notes`, each row is one note DITA file/article.

| Dataset | Total files/nodes | Files/nodes in duplicate pairs | Duplicate file/node % | Files/nodes in duplicate + included pairs | Duplicate + included file/node % |
|---|---:|---:|---:|---:|---:|
| KMT bodies EN | 9,935 | 4,616 | 46.46% | 5,529 | 55.65% |
| KMT bodies FR | 9,941 | 4,781 | 48.09% | 5,800 | 58.34% |
| KMT bodies EN + FR | 19,876 | 9,397 | 47.28% | 11,329 | 56.99% |
| KMT all_notes EN | 5,787 | 2,932 | 50.67% | 3,027 | 52.31% |
| KMT all_notes FR | 5,808 | 2,997 | 51.60% | 3,104 | 53.44% |
| KMT all_notes EN + FR | 11,595 | 5,929 | 51.13% | 6,131 | 52.88% |
| KMT bodies + all_notes total | 31,471 | 15,326 | 48.70% | 17,460 | 55.48% |

### File/node-based results by body type

| Dataset | Body type | Total files/nodes | Files/nodes in duplicate pairs | Duplicate file/node % | Files/nodes in duplicate + included pairs | Duplicate + included file/node % |
|---|---|---:|---:|---:|---:|---:|
| KMT bodies EN | conbody | 6,972 | 2,877 | 41.27% | 3,587 | 51.45% |
| KMT bodies EN | refbody | 1,371 | 909 | 66.30% | 1,002 | 73.09% |
| KMT bodies EN | taskbody | 1,592 | 830 | 52.14% | 940 | 59.05% |
| KMT bodies FR | conbody | 7,630 | 3,338 | 43.75% | 4,197 | 55.01% |
| KMT bodies FR | refbody | 1,375 | 893 | 64.95% | 1,013 | 73.67% |
| KMT bodies FR | taskbody | 936 | 550 | 58.76% | 590 | 63.03% |
| KMT bodies EN + FR | conbody | 14,602 | 6,215 | 42.56% | 7,784 | 53.31% |
| KMT bodies EN + FR | refbody | 2,746 | 1,802 | 65.62% | 2,015 | 73.38% |
| KMT bodies EN + FR | taskbody | 2,528 | 1,380 | 54.59% | 1,530 | 60.52% |
| KMT all_notes EN | conbody | 5,787 | 2,932 | 50.67% | 3,027 | 52.31% |
| KMT all_notes FR | conbody | 5,808 | 2,997 | 51.60% | 3,104 | 53.44% |
| KMT all_notes EN + FR | conbody | 11,595 | 5,929 | 51.13% | 6,131 | 52.88% |

## Results by body type

Mixed body-type rows such as `conbody + refbody` mean the candidate pair spans two different body tags.

### KMT bodies EN

| Body type pairing | Candidate pairs | Duplicate pairs | Duplicate % | Included pairs | Duplicate + included pairs | Duplicate + included % |
|---|---:|---:|---:|---:|---:|---:|
| conbody | 35,982 | 11,646 | 32.37% | 1,248 | 12,894 | 35.83% |
| conbody + refbody | 2,542 | 75 | 2.95% | 122 | 197 | 7.75% |
| conbody + taskbody | 7,445 | 721 | 9.68% | 241 | 962 | 12.92% |
| refbody | 15,126 | 7,569 | 50.04% | 425 | 7,994 | 52.85% |
| refbody + taskbody | 126 | 6 | 4.76% | 5 | 11 | 8.73% |
| taskbody | 13,388 | 1,253 | 9.36% | 135 | 1,388 | 10.37% |

### KMT bodies FR

| Body type pairing | Candidate pairs | Duplicate pairs | Duplicate % | Included pairs | Duplicate + included pairs | Duplicate + included % |
|---|---:|---:|---:|---:|---:|---:|
| conbody | 89,389 | 12,972 | 14.51% | 1,773 | 14,745 | 16.50% |
| conbody + refbody | 4,424 | 93 | 2.10% | 150 | 243 | 5.49% |
| conbody + taskbody | 7,119 | 285 | 4.00% | 95 | 380 | 5.34% |
| refbody | 15,685 | 8,034 | 51.22% | 407 | 8,441 | 53.82% |
| refbody + taskbody | 139 | 2 | 1.44% | 2 | 4 | 2.88% |
| taskbody | 10,057 | 657 | 6.53% | 45 | 702 | 6.98% |

### KMT all_notes

| Dataset | Body type pairing | Candidate pairs | Duplicate pairs | Duplicate % | Included pairs | Duplicate + included pairs | Duplicate + included % |
|---|---|---:|---:|---:|---:|---:|---:|
| EN all_notes | conbody | 20,022 | 9,996 | 49.93% | 234 | 10,230 | 51.09% |
| FR all_notes | conbody | 33,680 | 9,743 | 28.93% | 328 | 10,071 | 29.90% |
| EN + FR all_notes | conbody | 53,702 | 19,739 | 36.76% | 562 | 20,301 | 37.80% |

## Other relationship counts

| Dataset | Independent | Conflicting information | LLM-reviewed borderline pairs | LLM not reviewed borderline pairs | LLM API errors |
|---|---:|---:|---:|---:|---:|
| KMT bodies EN | 50,094 | 1,069 | 28,492 | 0 | 0 |
| KMT bodies FR | 101,071 | 1,227 | 33,332 | 0 | 0 |
| KMT all_notes EN | 7,277 | 2,515 | 9,739 | 0 | 0 |
| KMT all_notes FR | 20,396 | 3,213 | 18,343 | 0 | 0 |

## Source files

- KMT bodies EN summary: `outputs/kmt_dita_1_body_en_kg_pipeline/run_summary.json`
- KMT bodies FR summary: `outputs/kmt_dita_1_body_fr_kg_pipeline/run_summary.json`
- KMT bodies EN full classification CSV: `outputs/kmt_dita_1_body_en_kg_pipeline/kg_pair_classifications.csv`
- KMT bodies FR full classification CSV: `outputs/kmt_dita_1_body_fr_kg_pipeline/kg_pair_classifications.csv`
- KMT bodies EN non-independent matches CSV: `outputs/kmt_dita_1_body_en_kg_pipeline/kg_deduplication_matches.csv`
- KMT bodies FR non-independent matches CSV: `outputs/kmt_dita_1_body_fr_kg_pipeline/kg_deduplication_matches.csv`
- KMT all_notes EN summary: `outputs/kmt_dita_1_all_notes_en_kg_pipeline/run_summary.json`
- KMT all_notes FR summary: `outputs/kmt_dita_1_all_notes_fr_kg_pipeline/run_summary.json`
- KMT all_notes EN full classification CSV: `outputs/kmt_dita_1_all_notes_en_kg_pipeline/kg_pair_classifications.csv`
- KMT all_notes FR full classification CSV: `outputs/kmt_dita_1_all_notes_fr_kg_pipeline/kg_pair_classifications.csv`
- KMT all_notes EN non-independent matches CSV: `outputs/kmt_dita_1_all_notes_en_kg_pipeline/kg_deduplication_matches.csv`
- KMT all_notes FR non-independent matches CSV: `outputs/kmt_dita_1_all_notes_fr_kg_pipeline/kg_deduplication_matches.csv`
