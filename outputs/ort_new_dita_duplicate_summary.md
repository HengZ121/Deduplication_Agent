# ORT New DITA — Collapsed Duplicate Summary

The new ORT DITA body pipeline produced the following confirmed duplicate metrics. Duplicate clusters are connected components formed from confirmed duplicate/semantic-duplicate relationships after CrossEncoder and LLM review; inclusion relationships are excluded.

| Dataset | Total nodes | Confirmed duplicate pairs | Nodes in duplicate clusters | Duplicate clusters | Standalone unique nodes | Collapsed total | Collapsed duplicate portion |
|---|---:|---:|---:|---:|---:|---:|---:|
| English | 20,238 | 33,418 | 11,860 | 2,243 | 8,378 | 10,621 | 21.12% |
| French | 20,983 | 35,735 | 12,514 | 2,107 | 8,469 | 10,576 | 19.92% |

## Calculation

`Standalone unique nodes = total nodes − nodes in duplicate clusters`.

`Collapsed total = standalone unique nodes + duplicate clusters`.

`Collapsed duplicate portion = 1 − (standalone unique nodes / collapsed total)`.

This is a cluster-collapsed rate: each duplicate cluster is counted once as one reusable node. It is different from the raw percentage of nodes that participate in duplicate clusters.

Results were generated from the English and French runs in `outputs/ort_new_dita_kg_pipeline/en` and `outputs/ort_new_dita_kg_pipeline/fr`.
