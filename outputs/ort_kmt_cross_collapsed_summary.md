# ORT ↔ KMT Cross-Source Collapsed Duplicate Metrics

Only cross-source comparisons are included: KMT English ↔ ORT English and KMT French ↔ ORT French. Same-source pairs are excluded. Duplicate clusters use confirmed `duplicate/semantic duplicate` relationships after LLM review; inclusion and conflicting-information relationships are not counted as duplicate clusters.

| Language | Total nodes | Confirmed duplicate pairs | Nodes in duplicate clusters | Duplicate clusters | Standalone unique nodes | Collapsed total | Collapsed duplicate portion |
|---|---:|---:|---:|---:|---:|---:|---:|
| English | 28,632 | 26 | 45 | 19 | 28,587 | 28,606 | 0.07% |
| French | 29,386 | 36 | 51 | 16 | 29,335 | 29,351 | 0.05% |

## Calculation

`Standalone unique nodes = total nodes − nodes in duplicate clusters`.

`Collapsed total = standalone unique nodes + duplicate clusters`.

`Collapsed duplicate portion = 1 − (standalone unique nodes / collapsed total)`.

This is a cluster-collapsed rate: each duplicate cluster is counted once as one reusable node. It is not the raw percentage of nodes participating in duplicate pairs.
