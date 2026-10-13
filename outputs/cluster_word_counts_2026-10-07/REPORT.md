# Word counts of collapsed duplicate clusters

KMT: cluster median 58 words vs 32 standalone (1.81×; cluster-shorter probability 34.6%). ORT: cluster median 62.5 words vs 55 standalone (1.14×; cluster-shorter probability 45.5%). These are descriptive results from pair classifications with borderline cases not LLM reviewed.

## Method and limitations

Each duplicate cluster contributes one observation: the median saved word_count of its member topics. Each standalone node contributes its own count. These are separate within-dataset clusters by language; cross-source matches do not join clusters. Membership is formed from saved “duplicate/semantic duplicate” edges as connected components. Partial-inclusion pairs are not merged. Cluster labels are model outputs and are not human- or LLM-confirmed safe-reuse groups.

The refreshed deduplication runs used direct DITA topic-body text. Broken conref targets prevented full expansion, so word counts do not reconstruct the complete conref-expanded source. KMT note topics are included and separated from other KMT topics in source-type views. ORT source-type panels collapse a mixed-type cluster separately within each represented type, so these counts are not additive.

The charts compare median cluster member length with standalone-node length. The probability column is P(cluster length < standalone length) + 0.5 × P(tie), a descriptive statistic. Eligibility views use the saved comparability flag and retain a cluster only when all its members are eligible. Unclustered means not assigned to a detected cluster, not proven unique. Sensitivity rows compare minimum, median, mean, and maximum member lengths.

| View | Dataset | Clusters | Standalone | Cluster median | Standalone median | Median ratio | Probability shorter |
|---|---|---:|---:|---:|---:|---:|---:|
| pooled | KMT | 7,889 | 8,488 | 58 | 32 | 1.81 | 34.6% |
| pooled | ORT | 7,365 | 37,216 | 62.5 | 55 | 1.14 | 45.5% |
| by_subset | KMT · EN | 5,413 | 2,741 | 60 | 25 | 2.40 | 24.8% |
| by_subset | KMT · FR | 2,476 | 5,747 | 55 | 37 | 1.49 | 39.7% |
| by_subset | ORT · EN | 3,719 | 18,434 | 59 | 52 | 1.13 | 45.4% |
| by_subset | ORT · FR | 3,646 | 18,782 | 66 | 59 | 1.12 | 45.4% |
| eligible_only | KMT · EN | 5,413 | 2,514 | 60 | 27 | 2.22 | 27.1% |
| eligible_only | KMT · FR | 2,476 | 5,624 | 55 | 37 | 1.49 | 40.6% |
| eligible_only | ORT · EN | 3,719 | 15,169 | 59 | 72 | 0.82 | 55.2% |
| eligible_only | ORT · FR | 3,646 | 15,510 | 66 | 80 | 0.82 | 55.0% |