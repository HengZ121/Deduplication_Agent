# KMT word counts of collapsed duplicate clusters

KMT: cluster median 55 words vs 37 standalone (1.49×; cluster-shorter probability 39.8%). Saved borderline LLM reviews: 98,242 completed; 0 pending or failed. These are descriptive statistics, not an independent validation of semantic equivalence.

## Method and limitations

This report covers KMT English and French only. Each duplicate cluster contributes one observation: the median saved word_count of its member topics. Each standalone node contributes its own count. Clusters are formed separately by language from saved “duplicate/semantic duplicate” edges as connected components. Partial-inclusion pairs are not merged. A connected component does not establish that every pair of its members is semantically equivalent.

Source topics containing a keyref attribute have been excluded, together with their associated pairs. Word counts cover text physically present in the DITA body, including note topics. They do not expand conref references or measure complete published documents.

The charts compare median cluster member length with standalone-node length. The probability column is P(cluster length < standalone length) + 0.5 × P(tie), a descriptive statistic. Eligibility views use the saved comparability flag and retain a cluster only when all its members are eligible. Unclustered means not assigned to a detected cluster, not proven unique. Sensitivity rows compare minimum, median, mean, and maximum member lengths.

| View | Dataset | Clusters | Standalone | Cluster median | Standalone median | Median ratio | Probability shorter |
|---|---|---:|---:|---:|---:|---:|---:|
| pooled | KMT | 4,942 | 11,511 | 55 | 37 | 1.49 | 39.8% |
| by_subset | KMT · EN | 2,466 | 5,764 | 55 | 37 | 1.49 | 39.9% |
| by_subset | KMT · FR | 2,476 | 5,747 | 55 | 37 | 1.49 | 39.7% |
| eligible_only | KMT · EN | 2,466 | 5,641 | 55 | 37 | 1.49 | 40.7% |
| eligible_only | KMT · FR | 2,476 | 5,624 | 55 | 37 | 1.49 | 40.6% |

## Correction applied (2026-10-13)

The EN run originally also loaded `fr/KA-*_EN/` topics, which are byte-identical copies of the English files, so many EN "clusters" were an English topic paired with its own copy. Those nodes and their pairs are removed here and EN clusters are re-formed from the saved decisions. FR rows are unchanged, but the KMT `fr` DITA export itself contains English text, so FR results do not describe French content until the export is regenerated.
