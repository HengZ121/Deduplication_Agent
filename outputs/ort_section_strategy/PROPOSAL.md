# A section-based duplicate detector for the ORT task/activity dataset

## Recommendation

Keep each existing DITA file as the section unit. Build a map-aware section index, retrieve similar sections across activity and task publications, then distinguish equivalent section content from scope-dependent variants and related explanations. Preserve document context as evidence, without requiring whole-document equivalence or treating the task/activity distinction as a barrier to comparison.

The output should identify duplicated content and its occurrences. Deciding how to author a unified copy remains a later task. A content-duplicate finding and a judgment about whether a section can be moved unchanged are separate fields.

## What the dataset actually contains

This audit uses the English `unzipped/ort_new_dita/dita/en_EN` branch underlying the saved pipeline. It profiles all activity/task maps, not only RFS examples. The broader export also contains supporting and other categories; counts below deliberately describe activity/task publications. French was not profiled in this new audit.

| Observed property | Activity | Task |
|---|---:|---:|
| Publication maps | 101 | 780 |
| Nonempty section bodies in the current pipeline | 910 | 13,589 |
| XML `concept` bodies in that pipeline | 910 | 8,210 |
| XML `task` bodies in that pipeline | 0 | 5,379 |
| Median body words, current tokenizer | 59 | 93 |
| Bodies longer than the scorer's 1,200-character prefix | 109 | 3,707 |

Every one of the 14,499 body nodes under these two directories can be associated with a task/activity `.ditamap` in the audit. This means the missing parent context can be restored with a deterministic map-to-topic join, rather than inferred by an LLM. The pipeline counts are body-node counts, not the total number of DITA files; structural empty sections are absent from them.

Business document type is encoded by the path (`en_EN/activity/...` or `en_EN/task/...`). The current `kg_nodes.csv` column named `document_type` stores the XML root type instead. A task publication's background section is often `<concept>`, so filtering that column for `task` would discard 8,210 sections belonging to task publications. None of the 881 inspected maps has `othermeta`; the map title, path, and topic-reference hierarchy provide the directly available context.

### Stable section roles

All 101 activity maps have these top-level headings:

`Summary → What you need to know → Regional considerations → What you need to look for → What do you want to do? → Policy reference`

All 780 task maps contain Summary, What you need to know, Regional considerations, What you need to look for, and Policy reference; 776 also contain Step by step. Preserve the four exceptions listed in `additional_observations.json`, rather than imposing an assumed template.

Several template headings have empty bodies. For example, `activity/roe_rfs/what_do_you_want_to_do.dita` has an empty `<conbody/>`. Preserve such files as structural context, not duplicate-content candidates. Their absence from body text does not mean the hierarchy should be discarded.

### Cross-type matching is necessary

The saved internal classifications contain 11,048 task–task, 2,592 activity–task, and 358 activity–activity cross-document edges labeled duplicate. These are historical model decisions, not validated ground truth; 372 edges within a shared parent publication were excluded from those counts.

The observed cross-type matches include substantive identical sections, not just generic headings. For example:

- `activity/adj_rfs_review/conditions_for_creating_the_wi.dita`
- `task/adj_rfs_review_man_ret/conditions_for_creating_the_wi.dita`

Both contain the same 39-word condition for creating an ADJ RFS Review work item, under **What you need to know**. Their parent titles differ in specificity. That alone should not erase the shared-section finding. Keep the parent scope visible when considering its eventual reuse.

Outside RFS, `activity/direct_deposit/error_code_c850.dita` and `task/changing_dd/error_code_c850.dita` contain identical extracted instructions, with the same external WECS link and the same `common_notes/note_c_0089.dita` reference. The source differs in whitespace, illustrating why conservative whitespace normalization is useful.

## A concrete comparison record

Create one source-section record and retain each map occurrence separately. A shared note may occur in multiple documents with different context; do not overwrite its parent with a single arbitrary document.

```text
source_section_id: stable identifier of the DITA source
occurrence_id: map + topic-reference position
source_path: en_EN/task/.../conducting_a_detailed_security_check_level_1.dita
document_map: en_EN/task/.../envoyer-code-acces-issue-access-code-curam.ditamap
business_document_type: task
document_title: Issuing an access code — Cúram
xml_topic_type: task
section_title: Conducting a detailed security check
heading_path: Step by step > Level 1
body_original: source body and XML element locations
body_resolved: body with conref content resolved
reference_dependencies: notes, tables, xrefs, document-local step targets
```

Separate evidence of local scope from the document title: `Cúram` appears in the publication title, `Level 1` in the map ancestry, and an individual system/action may appear in the body. Preserve where each value came from. Do not assume every section in a Cúram-titled document describes a Cúram-specific operation.

`section_context_inventory.csv` is an actual map-to-section join produced by this audit, with 24,827 topic-reference occurrences across the 881 maps. Its fields are a practical starting point for this record.

## Proposed detection flow

### 1. Prepare the existing sections without changing their boundaries

Reuse `DitaTopicResolver` and map traversal. Resolve `conref` tables into the owning section's comparison view; retain canonical reference IDs alongside the text. Keep table row/column structure and step order. Store original text as well as conservatively normalized text. Normalize whitespace, but preserve meaningful identifier punctuation such as `/REP/`.

Keep navigation links as links. Local Note/Warning/Callout references should be registered as dependencies and made available to comparison when relevant; a generic label such as “Note” cannot stand in for the referenced content. Link targets themselves can differ while visible link labels match.

There are 5,443 common-note occurrences pointing to 3,865 distinct note files in the activity/task maps. Multiple uses of one canonical file are **existing reuse**. Separate physical files with repeated content are **duplicate copies**. Report those separately so repeated reference occurrences do not inflate the number of independently maintained copies.

### 2. Retrieve candidate sections through several complementary routes

- Exact canonical-body matches, including resolved content and meaningful reference identity.
- Lexical near-matches for copied sections with small edits.
- Semantic matches for paraphrased sections.
- Section-title and heading-role matches to find likely peers efficiently.

Search activity–activity, task–task, and activity–task. Prioritize peers with comparable roles, such as children of What you need to know across both types, or procedural sections under Step by step across tasks. Keep a global content-based route to catch duplicates with different headings: the audit found identical content titled **Entitlement to CCB** in an activity and **Untitled section** in a task.

Use titles and roles as retrieval/ranking signals, not hard exclusions. Document families can also improve candidate priority, but the export does not establish a complete authoritative activity-to-task hierarchy; any inferred family link must be marked as inferred.

Some activity-to-task links are directly available: `activity/earnings/task_breakdown.dita` describes tasks for different earnings types and links to them; `activity/voluntary_leaving/processing_the_claim.dita` links to `vllevel2_ic`. Use observed links as candidate-priority evidence. Their absence is not a negative signal: the RFS activity's retained choice section is empty. A navigation link is not automatically a parent-child declaration.

### 3. Judge the section pair, using two separate views

**Content view:** original/resolved body, table and step structure, and the exact changed spans. This establishes what is repeated.

**Context view:** parent map title, business type, section title, heading ancestry, and relevant linked material. This resolves whether the repeated instruction means the same thing in both occurrences.

The reviewer should answer:

1. Does the entire existing section repeat the same information or instructions?
2. If not, which existing paragraphs, XML elements, or spans are shared, and what changes?
3. Do the changes affect the actor, system, trigger, object, decision, exception, authority, or outcome?
4. Does the section rely on surrounding content, a linked note/table, or document-local step numbering?

Inspect these semantic fields when they occur or differ; do not require an expensive universal ontology extraction for every section. Deterministic exact/reference comparisons should run first, with model review concentrated on paraphrases, meaningful edits, and ambiguous context.

Compare full section content. The current scorer uses only a 1,200-character prefix, so 3,816 of the 14,499 activity/task bodies exceed that limit. For long sections, use a verifier that can read them or align existing XML elements internally and inspect all differences. The reported unit remains the original DITA section. A matching prefix must never establish full-section equivalence.

### 4. Return content relationship and context/dependency status separately

| Content relationship | Interpretation |
|---|---|
| Exact section duplicate | Same resolved content and relevant structure/references after conservative normalization |
| Equivalent section | Different wording, same instructions and information |
| Partial section overlap | Only part of the existing section is duplicated; report source-element/span evidence |
| Template variant | Shared wording but a substantive slot or branch differs |
| Related, not duplicate | Same topic or title, different information, behavior, or action |
| Unresolved | Insufficient source or confidence for a stronger decision |

Attach a separate status: context compatible, applicability review needed, document-local dependency, already shared source, or missing-reference issue. These flags do not erase an observed textual duplicate. They prevent the downstream team from mistaking content similarity for an unconditional permission to substitute a shared copy.

For verified groups, retain pair evidence and enforce compatibility when adding a section. A chain of similar sections is insufficient proof that every member is equivalent. Keep partial-overlap and template-variant links outside full-section equivalence groups.

## Examples that should shape the implementation

| Actual example | Proposed handling |
|---|---|
| Activity/task Conditions for creating the WI | Exact section duplicate; preserve both parent scopes. A positive example for cross-type retrieval. |
| Activity/task Error code C850 | Exact extracted content with matching link/note dependencies; retain source occurrences. |
| Replacing an access code in the activity and Cúram task | Near-duplicate candidate: “agent to replace” vs “officer to reissue.” Review these terms in context; the Cúram parent title alone must not reject the shared general explanation. |
| Detailed security check in those same publications | Template variant/partial overlap because the system-specific identification instruction changes FTS to Cúram. The shared general security content should remain discoverable. |
| RFS Linking the ROE and the matching period of employment | Same heading, different subject of the action: activity describes automatic system linking, while the task describes manual Non-complex agent review when no link exists. Related sections, not equivalent as a whole. |
| Quit versus Dismissal sections with different conref tables | Resolve tables before deciding equality. The previous audit found seven raw-identical RFS pairs whose expanded bodies differ. |
| Step by step > Level 1 versus Level 2 | Use inherited authority level as context and inspect the actual action/permission differences. Do not assume sameness or difference from the level label alone. |

Task sections also have procedural dependencies. For example, `task/roe_quit/linking_the_roe_and_the_matching_period_f71580ff_non-complex.dita` contains six XML steps but refers onward to steps 7 and 18. A section can be duplicated while still depending on document-local numbering. Preserve those edges; where numbering can be reliably resolved, compare target actions rather than assuming different numbers always mean different rules. Where it cannot be resolved, mark the dependency unresolved. Do not invent a destination from the number alone.

## A bounded pilot

Use three families already inspected: RFS, access codes, and direct deposit. Include activity–task positives, task–task variants, identical headings with different actions, different headings with identical content, common-note reuse, conref differences, level-specific tasks, and long sections with differences after character 1,200.

Create a small domain-reviewed evaluation set with independent labels for **content relationship** and **context/dependency status**. Include a fixed sample of negatives and audit retrieval misses; do not evaluate only pairs the old classifier accepted. Measure:

- precision and recall of duplicate-section retrieval and final decisions;
- cross-type recall, so activity/task partitioning cannot silently lose matches;
- false equivalence from systems, RFS categories, authority, or hidden tables;
- correct identification of partial overlap and existing shared references;
- review volume and group purity.

No new accuracy figure is claimed here. First compare the pilot against the frozen saved output, then expand it to all activity/task sections if its evidence is better.

## Files and reproducibility

Run `py profile_ort_sections.py` from the repository root. It makes no model or paid API calls and does not change production classifications.

- `summary.json`: audited counts and heading patterns.
- `publication_inventory.csv`: the 881 task/activity maps.
- `section_context_inventory.csv`: topic occurrences with parent type, title, hierarchy, and source path.
- `business_vs_xml_type.csv`: the business/XML type distinction.
- `activity_task_identical_examples.csv`: 33 saved cross-type exact-body examples with at least 35 tokenizer words, excluding Summary and Policy reference headings; these are evidence candidates, not a fully validated benchmark.
- `additional_observations.json`: long-section counts, task-template exceptions, and shared-note occurrence counts.

The source files above are under `unzipped/ort_new_dita/dita/en_EN/`. Earlier table-expansion and first-three-row evidence remains under `outputs/ort_rfs_research/`.
