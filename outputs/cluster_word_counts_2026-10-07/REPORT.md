# KMT word counts of collapsed duplicate clusters

KMT: cluster median 58 words vs 32 standalone (1.81×; cluster-shorter probability 34.6%). Saved borderline LLM reviews: 98,242 completed; 0 pending or failed. These are descriptive statistics, not an independent validation of semantic equivalence.

## Method and limitations

This report covers KMT English and French only. Each duplicate cluster contributes one observation: the median saved word_count of its member topics. Each standalone node contributes its own count. Clusters are formed separately by language from saved “duplicate/semantic duplicate” edges as connected components. Partial-inclusion pairs are not merged. A connected component does not establish that every pair of its members is semantically equivalent.

Source topics containing a keyref attribute have been excluded, together with their associated pairs. Word counts cover text physically present in the DITA body, including note topics. They do not expand conref references or measure complete published documents.

The charts compare median cluster member length with standalone-node length. The probability column is P(cluster length < standalone length) + 0.5 × P(tie), a descriptive statistic. Eligibility views use the saved comparability flag and retain a cluster only when all its members are eligible. Unclustered means not assigned to a detected cluster, not proven unique. Sensitivity rows compare minimum, median, mean, and maximum member lengths.

| View | Dataset | Clusters | Standalone | Cluster median | Standalone median | Median ratio | Probability shorter |
|---|---|---:|---:|---:|---:|---:|---:|
| pooled | KMT | 7,889 | 8,488 | 58 | 32 | 1.81 | 34.6% |
| by_subset | KMT · EN | 5,413 | 2,741 | 60 | 25 | 2.40 | 24.8% |
| by_subset | KMT · FR | 2,476 | 5,747 | 55 | 37 | 1.49 | 39.7% |
| eligible_only | KMT · EN | 5,413 | 2,514 | 60 | 27 | 2.22 | 27.1% |
| eligible_only | KMT · FR | 2,476 | 5,624 | 55 | 37 | 1.49 | 40.6% |