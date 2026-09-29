# Word counts of collapsed duplicate clusters

ORT clusters are shorter at the median: 81.5 words versus 98 for standalone nodes (16.8% lower), with the same direction in English and French. KMT is only slightly shorter when pooled: 50 versus 54 words (7.4% lower). That pooled KMT result hides opposite patterns: body clusters are longer (English 94 versus 81; French 122.25 versus 93), while note clusters are shorter (English 28 versus 32; French 33 versus 37). These directions persist in the matching-eligible sensitivity view. Therefore “clustered nodes have fewer words” is supported descriptively for ORT and KMT notes, but not for KMT bodies.

The distributions overlap substantially: a randomly selected collapsed cluster is shorter than a standalone node, with ties half-counted, in 54.8% of ORT and 51.3% of pooled KMT comparisons. Word count alone is consequently a weak separator. ORT source-type results vary, and the policy panel has only one cluster: do not generalize its median. A higher prevalence of short repetitive notes can explain an overall pattern without a universal short-text bias.

The collapsing rule matters most for KMT: using each cluster's longest member instead of its median reverses the pooled comparison (59 versus 54 words). ORT remains shorter under minimum, median, mean and maximum member-length choices. These are sensitivity checks, not recommendations to select the shortest or longest member as the master copy.

## Method and limitations

Each existing duplicate cluster contributes one observation: the median stored word_count of its members. Each standalone node contributes its own count. We do not sum member lengths, count a cluster once per member, or choose a final master copy. A fractional value can arise from an even-sized cluster.

Membership comes from outputs/kmt_all_duplicate_cluster_files.csv and outputs/ort_all_duplicate_cluster_files.csv. These are separate within-source cluster inventories, not ORT–KMT cross-source clusters. ORT uses the internal-run membership (3,753 clusters), not the older reviewed-run summary (4,350 clusters). All members were matched by node ID to their originating inventories. KMT uses the four cleaned kmt_dita_1 body/all_notes inventories; ORT uses the ORT rows of cross_nodes.csv, the universe used by its internal clustering script. Data-quality check: 2,902 KMT English note rows have aggregate file_content that differs from inventory text (the inspected example contains French text). We use inventory word_count, not aggregate file_content. Mismatch IDs are listed in aggregate_text_mismatches.csv; other subsets have no text mismatches.

Lengths are the saved pipeline word_count values of extracted node text, using the pipeline word-token definition rather than character count. They measure what was available to that run. They do not restore omitted conref tables/notes or measure the complete original publication. Existing cluster labels are pipeline decisions, not validated safe-reuse groups; KMT and ORT membership was produced by different runs/review policies.

Boxes span the 25th–75th percentiles; the line is the median; whiskers reach the furthest observation within 1.5 IQR; points beyond them are retained as outliers. Quartiles and fences are computed on original word counts; the default log axis only changes display. Linear scale is available. All positive-length items are included initially. The eligibility sensitivity view uses saved is_comparable and retains a cluster only if all members are eligible. Eligibility does not prove a node was compared against every possible partner. Unclustered means not assigned to an existing cluster, not proven unique.

Language and KMT body/note panels prevent a pooled result from hiding different populations. ORT source-type panels collapse a cluster separately within each type it contains; a mixed-type cluster can appear in several panels, so those panels must not be summed. English/French are pooled in those source-type panels only.

The probability column is P(cluster length < standalone length) + 0.5 × P(tie), computed over all cross-group comparisons. It is descriptive, not a causal effect or a significance test. A median ratio below 1 indicates shorter typical collapsed-cluster length. This does not establish that the classifier prefers short text: retrieval thresholds, content type, template structure, and review policy also affect cluster membership. Collapse sensitivity reports minimum, median, mean and maximum member length, with equal cluster weighting throughout.

| View | Dataset | Clusters | Standalone | Cluster median | Standalone median | Median ratio | Probability shorter |
|---|---|---:|---:|---:|---:|---:|---:|
| pooled | KMT | 3,360 | 15,689 | 50 | 54 | 0.93 | 51.3% |
| pooled | ORT | 3,753 | 25,752 | 81.5 | 98 | 0.83 | 54.8% |
| by_subset | KMT bodies · English | 904 | 5,086 | 94 | 81 | 1.16 | 46.2% |
| by_subset | KMT bodies · French | 908 | 4,944 | 122.25 | 93 | 1.31 | 44.2% |
| by_subset | KMT notes · English | 773 | 2,851 | 28 | 32 | 0.88 | 54.8% |
| by_subset | KMT notes · French | 775 | 2,808 | 33 | 37 | 0.89 | 54.5% |
| by_subset | ORT · English | 1,880 | 12,458 | 74 | 89 | 0.83 | 54.3% |
| by_subset | ORT · French | 1,873 | 13,294 | 91 | 108.5 | 0.84 | 55.3% |
| eligible_only | KMT bodies · English | 904 | 4,956 | 94 | 84 | 1.12 | 47.4% |
| eligible_only | KMT bodies · French | 908 | 4,844 | 122.25 | 97 | 1.26 | 45.1% |
| eligible_only | KMT notes · English | 773 | 2,851 | 28 | 32 | 0.88 | 54.8% |
| eligible_only | KMT notes · French | 775 | 2,808 | 33 | 37 | 0.89 | 54.5% |
| eligible_only | ORT · English | 1,865 | 12,425 | 75 | 89 | 0.84 | 54.1% |
| eligible_only | ORT · French | 1,857 | 13,265 | 93 | 109 | 0.85 | 55.0% |