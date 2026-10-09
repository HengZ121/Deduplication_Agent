# ORT: identifying content that can be maintained together

23 September 2026 — local dataset audit; no client text sent to an external model.

## 1. Decision supported by this investigation

Build a **reuse evidence index**, with separate fields for the repeated content and its applicability. Keep the existing DITA section as the unit of discovery. Identify matching paragraphs, commands, and tables *inside* those sections as evidence; do not ask the conversion team to rechunk its output.

There is measurable potential: **1,398 exact-content groups containing 4,105 physical section files**, across English and French. There are also repeated passages in non-identical sections. These are discovery results, not authorization to replace every occurrence with one universally applicable source.

The practical pilot is policy paragraphs and well-defined instructions with explicit scope. System-specific procedures and RFS variants should retain their differences. The KMT team can later decide how to implement approved shared sources.

## 2. What was counted

| Scope | English | French |
|---|---:|---:|
| Existing nonempty task/activity section bodies | 14,499 | 15,228 |
| Activity section bodies | 910 | 907 |
| Task section bodies | 13,589 | 14,321 |
| Publication maps inspected | 881 | 881 |
| Maps represented by these nonempty task/activity bodies | 879 | 879 |
| Saved candidate pairs between distinct publications | 130,564 | 187,912 |
| Saved accepted duplicate pairs re-audited | **13,998** | **12,867** |

The source branches are `en_EN` and `fr_FR` under `unzipped/ort_new_dita/dita`. Parallel `en`/`fr` branches and older extractions were excluded. English and French are counted separately; no cross-language duplicate claim is made. Each language has 101 activity and 780 task maps. Task/activity comes from the publication path, not the XML root tag: a task publication can contain concept topics.

Pair denominator: unique saved `duplicate/semantic duplicate` pairs for which both endpoints are task/activity sections with distinct parent documents. Pairs sharing any parent map are excluded. This is a **reclassification of the pipeline's positive pool**, not the proportion of all possible document pairs, all documents, or all client content that is duplicated. The audit did not estimate the pipeline's overall precision or semantic recall.

### Mutually exclusive proportions

| Audit type | English pairs | English share | French pairs | French share |
|---|---:|---:|---:|---:|
| Exact expanded section content and structure | 3,920 | **28.00%** | 3,187 | **24.77%** |
| Template/value/reference variant candidate | 4,619 | **33.00%** | 4,490 | **34.90%** |
| Partial overlap observed | 2,774 | **19.82%** | 2,616 | **20.33%** |
| Semantic-equivalence candidate, unconfirmed | 2,259 | **16.14%** | 2,046 | **15.90%** |
| Related or unresolved | 426 | **3.04%** | 528 | **4.10%** |
| Unresolved source | 0 | 0.00% | 0 | 0.00% |
| Total | **13,998** | **100%** | **12,867** | **100%** |

The earlier proposed “equivalent” and “related” types cannot honestly be counted as confirmed semantic judgments without reference labels. Their audit categories therefore remain candidates/unresolved. No model score is interpreted as a probability of safe reuse.

The rules are applied in this order:

1. Unresolved/unsupported references prevent an exact finding.
2. Exact means equal normalized expanded body structure, including element order, table structure, applicable attributes, and normalized reference destinations. Local IDs and styling attributes are ignored. Case and whitespace are normalized; punctuation, numbers, and slashes are retained. The section title and publication context remain separate evidence.
3. Variant candidate means resolved token-set Jaccard similarity at least 0.80 plus a changed extracted value/system/level/negation signal, reference destination, or structure. It includes dependency variants; it does **not** mean every pair expresses conflicting policy or is a safely parameterizable template.
4. Partial overlap requires an identical existing XML paragraph, command, table, or eligible list item of at least 12 tokens. This also can occur in the variant category, which has higher precedence.
5. Semantic-equivalence candidate requires Jaccard at least 0.72, no detected slot/context changes, saved cross-encoder score at least 0.995, and embedding similarity at least 0.90. These are provisional triage thresholds, not validated operating thresholds.
6. Remaining positives are related or unresolved. They are not automatically classified as nonduplicates.

Independent of bucket precedence, **4,510 English and 4,224 French non-exact accepted pairs contain an exact internal passage**. These overlap the variant and partial categories; do not add them to the table.

Files: [English distribution](D:/Deduplication_Agent/outputs/ort_knowledge_reuse_audit/en/type_distribution.csv), [French distribution](D:/Deduplication_Agent/outputs/ort_knowledge_reuse_audit/fr/type_distribution.csv), [English pair evidence](D:/Deduplication_Agent/outputs/ort_knowledge_reuse_audit/en/pair_audit.csv), [French pair evidence](D:/Deduplication_Agent/outputs/ort_knowledge_reuse_audit/fr/pair_audit.csv).

## 3. Patterns that matter for knowledge management

### A. Repeated policy sections are a practical starting point

Whole-corpus exact grouping is independent of the saved nearest-neighbor candidate list.

| Opportunity measure | English | French |
|---|---:|---:|
| Exact section groups | 758 | 640 |
| Physical sections in those groups | 2,217 (15.29% of section bodies) | 1,888 (12.40%) |
| Groups with at least 40 tokens per section | 393 | 345 |
| First-review shortlist: at least 40 tokens, no detected local step jump, same extracted context signature | 312 | 317 |

The **629-group shortlist is a review priority, not a safe-to-merge list**. An empty context signature means unknown, not universal applicability. Version, owner, effective date, and policy scope were not reliably available for certification.

Concrete English opportunities:

| Repeated content | Identical physical copies | Parent documents | Tokens per copy | Proposed next action |
|---|---:|---:|---:|---|
| Information reported after claimant's reports have been processed — one officer-worded variant | 15 | 15 | 190 | Have the policy owner confirm common applicability and currency |
| Levels of decision — failure to respond / rescinding D15 | 19 | 19 | 92 | Check authority and time-window scope across all occurrences |
| Return to work (RTW) | 14 | 14 | 122 | Review renewal/conversion scope and linked dependencies |
| Fraud indicators — one exact variant | 5 | 5 | 217 | Verify applicable workflow before proposing shared maintenance |

The same “information reported” heading also has a **different 131-token agent-worded variant in nine documents**. Similar titles therefore identify a content family, not one identical component. Likewise, “Selecting the appropriate benefit type” has separate 113-token and 112-token exact groups. Preserve those families and show their differences.

At most 2,707 extra physical section copies could be removed if every exact group proved consolidatable. This is an upper bound on copies, **not a savings estimate**. It includes short content and ignores implementation/maintenance cost.

### B. Repeated passages inside different sections are a larger discovery surface

There are **6,489 English and 6,787 French distinct repeated internal element groups**. Of these, 417 English and 456 French contain at least 40 tokens and appear in at least three parent documents. These groups overlap full-section groups and each other across occurrences; their volumes must not be added as independent savings.

Examples from the actual English files:

| Identical passage | Physical section occurrences | Parent documents | Interpretation |
|---|---:|---:|---|
| 48-token voluntary-disclosure paragraph beginning “The voluntary disclosure policy may apply…” | 61 | 61 | Strong policy-paragraph review candidate |
| “In NWS, add details to the draft SROC created during fact-finding or create a new SROC as follows:” | 173 | 113 | Repeated command introduction; following fields may differ |
| “When the Operational Centre Memo (MM06) transaction opens, send the information to IPOC as follows:” | 277 | 128 | Workflow family; the introduction alone is incomplete |

This is why the output should include an exact source span and its surrounding instructions. A repeated “as follows” command is evidence of a common workflow, but is not a self-contained unit to centralize without its arguments and following list.

### C. The client already has some sharing—and some duplicated shared files

The inspected maps contain 10,911 references to 7,924 distinct common-note/table source files. **1,229 source files already serve more than one document**. Do not present those existing shared references as new deduplication savings.

Separately, **35 exact-content groups contain 72 distinct common source files**: 17 English groups and 18 French groups. For example, English `note_c_2721.dita` and `note_c_2751.dita` have identical expanded bodies, with 18 map-reference occurrences in total. They instruct reassignment of a contentious issue to Level 2 while keeping the CR Conversion WI separate. This is a small, concrete source-governance pilot, subject to scope/version checks.

Map-reference counts are not complete runtime use counts: references embedded inside bodies are resolved for section comparison, but are not included in these map-occurrence totals. Different fragments of a shared source can also require separate applicability review.

### D. Task and activity documents should be compared, but interpreted differently

Of the English accepted pairs, 11,048 are task–task, 2,592 activity–task, and 358 activity–activity. **328 activity–task pairs are exact expanded-content matches**. A hard rule forbidding cross-type comparison would lose genuine repeated material.

Use document type and heading role as contextual features and review strata. Activities often describe the process or automated behavior; tasks often prescribe an agent's actions. Identical titles or related operations do not establish equivalent instructions. The previously inspected activity RFS matching explanation and task ROE linking procedure illustrate this distinction.

## 4. Where current decisions need improvement

### System identity: the first three rows really were accepted together

The three detailed-security-check sections from **Access code**, **Issuing an access code — Cúram**, and **Issuing an access code** were accepted by the existing pipeline. Their pair scores were approximately 0.99937–0.99957, without LLM review. They share security wording but vary in FTS/Cúram, `/REP/` versus `REP`, and agent/officer wording.

The saved classifier's conflict checks focus on numbers and negation. They do not bind the instruction to a system. These examples fit inside the scoring limit, so truncation does not explain this specific failure. A very high relevance/similarity score is insufficient evidence that the same instruction applies in both systems.

**Treatment:** retain the genuinely repeated security statements as span evidence; label the system-specific lines as variants; preserve literal indicator punctuation. Do not infer that FTS and Cúram are aliases. Have the domain owner decide whether the common statements can be maintained together.

### RFS: small changes can determine applicability

The **Quit** and **Dismissal** summary sections differ in the RFS trigger, E–Quit versus M–Dismissal, despite a saved score around 0.99942. They belong to the same procedural family, but the trigger must remain attached to its instruction.

Their “Linking the ROE and the matching period” sections had identical normalized extracted bodies, but resolve different tables: `table_c_0617` and `table_c_0611`. The corresponding example contains E versus M in the RFS field. The new audit detects **six identical internal elements** while keeping the full sections separate as variants. An example-value difference is not, by itself, proof that the procedural instructions contradict each other.

Across the accepted pool, **nine English pairs and one French pair** had equal legacy-normalized raw text, contained a conref, and differed after expansion under that same normalization. A much larger strict surface-difference count also includes punctuation changes; it would be misleading to report all of those as hidden-table errors.

**Treatment:** expand dependencies before comparing; align table rows/cells and preserve column labels so a bare E/M can be interpreted as an RFS value. A regex over whole-section text cannot reliably do that binding.

### Context must remain separate from exactness

Even within the exact bucket, **453 English and 366 French accepted pairs** differ in the limited context signatures extracted from parent titles/headings. Exact body content therefore cannot serve as an automatic applicability certificate.

Nonexclusive review signals in the full positive pool include:

| Signal | English pairs | French pairs |
|---|---:|---:|
| Different inherited context signature | 1,653 | 1,542 |
| Different link targets | 4,666 | 4,717 |
| Different extracted system sets | 206 | 138 |
| Different RFS code-and-label sets | 30 | 29 |
| Different authority levels | 29 | 43 |
| Different numbers | 174 | 243 |
| Presence/absence of detected negation differs | 33 | 40 |
| A document-local step reference is detected | 1,279 | 7 |

These are review signals, not confirmed contradictions, and they overlap. The French step-reference count is a limitation of the narrow phrase recognizer; it is **not evidence that French documents have almost no local dependencies**. System/RFS vocabularies are also incomplete. The current rule scan is a baseline to improve, not a finished semantic guard.

### Exact lookup should bypass the nearest-neighbor cap

Global hashing found 5,210 eligible English and 4,413 French exact section pairs. The saved candidate lists contain 3,920 and 3,187 respectively: **1,290 English and 1,226 French exact pairs were absent**. All these missing pairs have bodies shorter than 40 tokens, so this is mainly a short repeated-content issue, not evidence that many long policy sections were missed.

The internal run uses top-20 neighbor retrieval with an embedding cutoff. A global exact-hash channel avoids dependence on that cap. It should still rank down short, context-dependent content. This coverage result applies only to exact content, not semantic recall.

### Similarity-chain clusters are not proven reuse groups

The existing internal clustering script unions every accepted pair. Recomputing this graph over the audited English task/activity subset produces a largest connected component of **121 sections with 2,210 accepted edges**. Treating all members as equivalent would imply 7,260 pair relationships, including **5,050 without an audited positive edge**. The French counterpart has 118 sections, 1,953 edges, and 4,950 additional pairs without a positive edge.

Those missing edges may be untested, excluded from this cohort, or rejected; they are not all proven conflicts. The result establishes that transitive closure adds claims that the accepted edges alone do not justify. Keep discovery families separate from approved reuse groups. For semantic reuse groups, check every proposed member against the approved content and scope constraints; use pairwise compatibility checks where needed, and reject bridge-based merges that violate scope. Partial overlap is not transitive equivalence.

## 5. A defensible role for FrameNet

FrameNet supplies schemas for situations and their participants, such as an inspector verifying some content using evidence. It is a semantic resource; reading the resource does not automatically annotate arbitrary ORT sentences. See the [official FrameNet project](https://icsi.berkeley.edu/projects/framenet-project/) and [NLTK FrameNet documentation](https://www.nltk.org/howto/framenet.html).

I exercised the repository's existing English mapper with BERT disabled on **240 deterministic hash-selected distinct first sentences**, selected from 9,339 eligible sentences of at least eight whitespace-separated words:

| Probe result | Count |
|---|---:|
| A configured frame was emitted | 119 / 240 (49.6%) |
| No configured frame was emitted | 121 / 240 |
| Mapped sentences with no extracted role values | 21 / 119 |
| Mapped sentences without a matched official lexical unit | 57 / 119 |
| Mapped sentences missing at least one configured role | 119 / 119 |

This measures **coverage of the current rules**, not correctness, and does not evaluate the optional BERT path or all of FrameNet. Some configured roles are optional or legitimately implicit; the last row is not a 100% error rate. The first-sentence sample is not representative of every instruction position. The English resource was not applied to French as if it were a validated French parser.

In the actual FTS and Cúram sentences, the mapper emits **Verification** for both. It extracts FTS as `Means`, but extracts no role value for Cúram. The independent domain-system scan correctly preserves `fts` and `curam`. In the ROE task sentence, it extracts only “agent,” losing “Non-complex” and the objects/systems to which review applies.

**Recommended contribution:** use FrameNet to structure and explain aligned events, with explicit domain extensions for system, RFS value, authority level, condition, modality, negation, temporal constraint, and outcome. Retain the source span for every extracted value. Keep unknown values unknown. A shared frame supports “same kind of operation”; matching arguments and applicability are still required for “same instruction.” Different frames can also describe related perspectives, so frame mismatch should not automatically reject a pair.

Test the incremental benefit rather than making FrameNet a mandatory acceptance gate: compare (A) lexical/embedding/cross-encoder baseline, (B) baseline plus reference expansion and domain constraints, and (C) B plus frame/argument evidence. Keep C in automated decisions only if it improves measured errors or reviewer effort on a held-out set. It can still be useful as a reviewer explanation if it adds no classification benefit.

## 6. Proposed approach, aligned with this dataset

| Stage | Implementable behavior | Why it matters here |
|---|---|---|
| Resolve and retain provenance | Read map order; expand conrefs; retain headings, section titles, parent publication, task/activity, language, link targets, table cells, and step order | Raw extracted text omitted RFS table differences |
| Global exact discovery | Hash normalized expanded XML bodies and eligible existing internal elements | Exhaustive exact discovery without top-k dependence |
| Candidate retrieval | Combine existing embeddings with lexical retrieval; compare within each language; use type/heading/system as routing features, with a path for cross-type matches | 328 English exact activity–task pairs demonstrate why hard separation fails |
| Evidence alignment | Align existing paragraphs/steps/table rows inside candidate section pairs; record matched spans and unmatched material in both directions | Whole-section similarity hides reusable portions and changed conditions |
| Context and argument checks | Bind actors, systems, codes, thresholds, conditions, outcomes, and local references to aligned operations; add FrameNet evidence where coverage is adequate | “Same wording” can refer to a different operation or system |
| Cross-encoder assessment | Score aligned units with sufficient surrounding context; aggregate coverage in both directions; preserve contradictions and missing evidence | Current first-1,200-character / 256-token limits can hide later differences |
| Separate decisions | Store content relation independently from applicability/dependency status; retain confidence and evidence | Exact content can have different scope; partial reuse can coexist with variants |
| Conservative grouping | Group exact content for discovery; promote a proposed reuse group only after scope/dependency checks; avoid connected-component equivalence for partial/semantic edges | Prevents unsafe merges through similarity chains |
| Targeted review | Route high-value exact groups first, then variants and semantic candidates; unresolved stays unresolved | Reduces the amount of judgment the user must supply |

The audit measured 3,816 English bodies longer than 1,200 characters in the prior section profile. This is an exposure count, not the number misclassified due to truncation. Preserve DITA as the section unit while scoring aligned existing elements or overlapping model-input windows when necessary. Do not replace a long-section decision with a score from its opening alone.

No external LLM is required for this design. Existing embeddings and cross-encoder remain local candidate/evidence tools. A client expert can review the small, prioritized exceptions. No LLM was used to label all pairs in this audit.

Suggested output contract for the KMT team: source section IDs; exact source element/span locations; parent documents; language and publication type; content relationship; matched coverage in each direction; differing fields and evidence; resolved dependencies; applicability status (`compatible`, `different`, `unknown`); proposed reuse-family ID; reviewer decision and version. “Reusable” should be a separately approved state, not a synonym for similarity.

## 7. Validation and next decision

Start with the 629-group substantive shortlist, the 35 duplicated common-source groups, and the RFS/security-check counterexamples. Select a manageable first pilot, such as 20 policy/instruction groups plus 10 system/RFS variants. Review each group's applicability and currency, not thousands of pair scores individually.

The delivered **42-pair review queue** is a deterministic, diverse triage sample across both languages and review signals. Its human decision fields are blank. It is not a random accuracy benchmark and must not be used directly to claim overall precision.

For a formal evaluation, independently label a stratified held-out sample covering exact, variant, partial, semantic-candidate, and unresolved pairs; task/activity combinations; both languages; and long sections. Separate tuning examples from the holdout by publication/content family to limit repeated-text leakage. Include sampled rejected candidates and a separately searched set of missed matches to assess retrieval. If reporting aggregate precision from stratified sampling, weight by stratum size and report uncertainty. Measure content-relation accuracy and safe-reuse precision separately. Agree with the client on acceptable risk before choosing an automatic-acceptance threshold.

The immediate business decision is **which repeated policy families the client wants to govern together**. Engineering can produce evidence and reject known incompatibilities. It cannot infer absent policy ownership, effective dates, or the client's tolerance for shared maintenance.

## 8. Reproducibility and limits

The audit expands the body XML rather than performing a full DITA publishing build. It repairs known same-language common-note/table relative paths by exact filename and logs those repairs. It flags unsupported key/range references rather than silently treating them as equal; none were flagged in the audited bodies. Zero detected source issues does not certify every DITA publishing feature or business rule.

The body-text inventories originate from saved pipeline nodes. Exact matches are recomputed from the current corresponding DITA files. Shared-source analysis covers common files referenced by inspected maps, not every orphan file in the corpus. Content fingerprints normalize case/whitespace and exclude local IDs/styling. Token counts use the existing pipeline tokenizer and may include link-description text; they are ranking measures, not publishing word counts. Plain text alone is not used to flatten table or step structure for exact matching.

Reproduce from `D:\Deduplication_Agent`:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
py audit_ort_knowledge_reuse.py
py analyze_ort_reuse_patterns.py
py -m unittest test_audit_ort_knowledge_reuse -v
```

Nine regression tests passed, covering source-resolution failure, circular conrefs, E/M table changes, reference targets, partial overlap, context separation, system changes, French signals, and significant punctuation. No production classifier thresholds or client DITA files were changed. Input/code hashes are in `input_and_code_manifest.csv`.

Key evidence files are all in **D:\Deduplication_Agent\outputs\ort_knowledge_reuse_audit**:

- `exact_section_opportunities.csv` and `exact_section_group_members.csv`: ranked full-section groups and every member.
- `repeated_internal_spans.csv`: repeated existing elements, occurrence paths, and text.
- `duplicate_common_source_files.csv`: distinct common-source files with equal expanded content.
- `en/pair_audit.csv` and `fr/pair_audit.csv`: every audited positive pair, original scores, category, and review signals.
- `en/exact_pairs_absent_saved_candidates.csv` and the French counterpart: exact pairs missed by the saved candidate lists.
- `framenet_coverage_probe.csv` and `framenet_document_examples.csv`: reproducible local FrameNet evidence.
- `review_queue.csv`: 42 varied pairs with blank review fields.
- `run_summary.json`, `pattern_summary.json`, and `reference_repairs.csv`: machine-readable method/results and reference repairs.
