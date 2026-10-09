# ORT content reuse: findings and proposed pilot

**Recommendation:** identify repeated content and applicability separately. Keep the existing DITA sections, and show repeated passages inside them. A duplicate-content match should not automatically mean that all occurrences can share one maintained source.

## Measured proportions

We inspected **29,727 nonempty English/French task and activity section bodies** and re-audited **26,865 accepted cross-document duplicate pairs**.

| Audit type | English (13,998 pairs) | French (12,867 pairs) |
|---|---:|---:|
| Exact expanded content and structure | 28.00% | 24.77% |
| Template/value/reference variant candidate | 33.00% | 34.90% |
| Partial overlap observed | 19.82% | 20.33% |
| Semantic-equivalence candidate, unconfirmed | 16.14% | 15.90% |
| Related or unresolved | 3.04% | 4.10% |

These describe the pipeline's accepted pair pool. They are not a verified error rate or the percentage of all client documents that can be merged. The candidate categories use documented rules and saved scores; they still need applicability review.

## Three useful opportunities

1. **1,398 exact-content groups contain 4,105 physical section files.** A shortlist of 629 groups has at least 40 tokens, no detected local step jump, and matching extracted context signals. This is a review priority, not automatic approval.
2. **Partial reuse is substantial.** 4,510 English and 4,224 French non-exact accepted pairs contain an identical internal passage. A voluntary-disclosure paragraph appears in 61 English documents; an error-correction section has 15 exact copies; a levels-of-decision section has 19.
3. **Some sharing already exists.** 1,229 common-note/table source files are referenced by multiple documents. Separately, 35 groups contain 72 distinct common-source files with identical expanded content. Avoid counting existing sharing as new savings.

## Why whole-section similarity is insufficient

- The original access-code examples were accepted with scores above 0.999 even though they refer to FTS versus Cúram and different indicator literals. The classifier did not check system identity.
- Quit and Dismissal RFS sections share wording but have different triggers. Expanding their referenced tables reveals E/M example differences hidden by raw text extraction.
- 819 accepted exact-content pairs still differ in extracted parent-context signals. Identical body text does not establish common applicability.
- The largest English connected component has 121 sections and 2,210 accepted pair links. Treating the whole component as equivalent would imply another 5,050 pair relationships without a directly accepted edge in the audited subset.

## FrameNet's useful, bounded role

Use FrameNet to explain **what action is being described and who/what participates**, alongside explicit system, RFS, authority, condition, and outcome fields. A shared frame is not an equivalence decision.

The existing rule-only English mapper emitted a frame for 119 of 240 sampled first sentences. It assigned the same Verification frame to the FTS and Cúram examples and failed to extract Cúram. This is a coverage probe, not an accuracy score or an evaluation of the optional BERT path. Test FrameNet's incremental benefit against a simpler reference-and-domain-constraint baseline before making it an acceptance gate.

## Proposed pilot and success criteria

Start with 20 repeated policy/instruction groups and 10 system/RFS variant families. Deliver the repeated spans, differences, dependencies, and applicability questions to the client owner. Leave implementation of the shared source to the KMT team.

Reuse existing embeddings for discovery and the cross-encoder for aligned evidence. Add expanded-XML fingerprints, explicit domain constraints, and conservative grouping. Score complete relevant instructions instead of only a long section's opening. This does not require sending pairs to an external LLM.

Evaluate separately: accuracy of the repeated-content relation; false acceptance of incompatible reuse; retrieval of known exact matches; and reviewer time per approved group. Keep a held-out, expert-labeled set. No confirmed semantic precision or safe-consolidation savings are claimed yet.

**Available now:** a detailed report, ranked opportunities, pair-level evidence, FrameNet examples, and a 42-pair review queue. Nine regression tests passed. Client source files and production decisions were not modified.

Full folder: **D:\Deduplication_Agent\outputs\ort_knowledge_reuse_audit**

Full report: [RESEARCH_REPORT.md](D:/Deduplication_Agent/outputs/ort_knowledge_reuse_audit/RESEARCH_REPORT.md)
