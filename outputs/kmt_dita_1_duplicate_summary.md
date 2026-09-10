# KMT DITA 1 Body Deduplication Summary

This report records the final duplicate counts and percentages for the new `kmt_dita 1.zip` dataset, processed at body level with EN and FR separated.

## Counting method

- Unit of comparison: body-level text node pairs.
- Candidate generation: top 20 semantic neighbors per comparable node, then filtered by embedding threshold.
- Cross-encoder thresholds:
  - Duplicate: score >= 0.995
  - Borderline for LLM review: 0.95 <= score < 0.995
- All borderline pairs were sent to LLM review.
- Duplicate percentage is calculated as:

```text
duplicate / candidate pairs
```

## Final results

| Dataset | Body nodes | Comparable nodes | Candidate pairs | Duplicate / semantic duplicate pairs | Duplicate % of candidates | One passage included in another | Duplicate + included pairs | Duplicate + included % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| EN bodies | 9,935 | 9,805 | 74,609 | 21,270 | 28.51% | 2,176 | 23,446 | 31.43% |
| FR bodies | 9,941 | 9,841 | 126,813 | 22,043 | 17.38% | 2,472 | 24,515 | 19.33% |

## Other relationship counts

| Dataset | Independent | Conflicting information | LLM-reviewed borderline pairs | LLM API errors |
|---|---:|---:|---:|---:|
| EN bodies | 50,094 | 1,069 | 28,492 | 0 |
| FR bodies | 101,071 | 1,227 | 33,332 | 0 |

## Source files

- EN summary: `outputs/kmt_dita_1_body_en_kg_pipeline/run_summary.json`
- FR summary: `outputs/kmt_dita_1_body_fr_kg_pipeline/run_summary.json`
- EN final CSV: `outputs/kmt_dita_1_body_en_kg_pipeline/kg_deduplication_matches.csv`
- FR final CSV: `outputs/kmt_dita_1_body_fr_kg_pipeline/kg_deduplication_matches.csv`
