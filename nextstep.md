Task 1
As a Knowledge Architect,
I want the selected knowledge base content to be mapped to the approved enterprise ontology,
so that concepts, entities, document sections, and relationships are represented consistently across the unified knowledge platform.
The alignment activity will identify the relevant ontology classes, properties, and relationships for the in-scope knowledge base content. Existing terminology, metadata, and business concepts will be mapped to the corresponding ontology elements. Where no suitable ontology element exists, the gap will be documented for review rather than creating new concepts without approval.
The outcome of this story is a validated mapping between the selected knowledge base content and the ontology, including traceability to the original source.

AC1 – Ontology Elements Identified
Given an approved ontology and an in-scope knowledge base dataset
When the alignment is performed
Then the relevant ontology classes, properties, and relationships are identified for the knowledge base content.
AC2 – Content Mapped to Ontology
Given the identified ontology elements
When the knowledge base content is analyzed
Then each in-scope concept, entity, or content section is mapped to the most appropriate ontology element where a valid match exists.
AC3 – Source Traceability Preserved
Given a completed ontology mapping
When the mapping results are reviewed
Then each mapped element includes a reference to its original knowledge base, document, and source content.
AC4 – Unresolved Mappings Documented
Given content that cannot be confidently mapped to the existing ontology
When the alignment is completed
Then the content is recorded as an unresolved mapping or ontology gap for subject matter expert review.
AC5 – Mapping Results Validated
Given the completed mapping output
When it is reviewed by the designated knowledge or ontology stakeholder
Then mappings can be approved, rejected, or corrected before being used in the unified knowledge base.



Task 2

Candidate frames from the expository sections
#	Concept	Corpus evidence	Candidate FrameNet frame(s)	Disposition
1	Eligibility / Qualification	"Maternity benefits can be paid if one of the following qualifying conditions is met" (major attached, 600 hrs; CER 420 hrs)	Meet_specifications, Compliance, possibly Capability — none is a clean fit	New — likely A6 induction candidate (QUALIFY frame: Candidate, Benefit, Criterion_set, Period_of_applicability)
2	Entitlement	"To be entitled..., a client must meet both of the following conditions"	Deserving, Being_obligated (inverted) — weak fits	New — probably same induced family as #1, but note the semantic distinction: qualification establishes the claim, entitlement conditions the payment. Worth one research story to decide one frame or two
3	Evidentiary sufficiency / proof	"the client must provide a signed statement attesting to the pregnancy"; e-signature counts, verbal attestation does not when officer completes INS5168	Documents (Document, Bearer, Issuer, Right), Evidence (Support, Proposition), Submitting_documents	New as a layer — the step-by-step VERIFY frame checks; this content defines what satisfies Unconfirmed_content. This is exactly the "What You Need to Look For" ≈ FE-recognition-rules mapping — it's the acceptability conditions on Medium/Unconfirmed_content fillers for A1, not a new procedural frame
4	Deontic permission	"The BP can be extended"; "A Level 1 officer can terminate the disentitlement if..."	Permitting, Deny_or_grant_permission, Prohibiting_or_licensing	Extends A2 — yesterday's A2 scoped prohibition + requirement; permission is the missing third deontic modality. Note the authority-level binding (Level 1 vs Level 2) as a candidate core FE (Authorized_role), which the DD document didn't surface
5	Sanction imposition	"A D25 disentitlement is imposed if the client has not accumulated at least 600 insurable hours" (D25/D27/D36)	Rewards_and_punishments, Fining (too specific)	New — distinct from APPROVE/REJECT: it maps conditions onto a typed penalty from an enumerated code set. The D-codes themselves are ontology slot fillers per the Reason-code principle
6	Diagnostic inference	"Based on the letter that was sent, the officer can determine the reason the D15 is imposed" (C-73 vs C-72/C-88 prefixes)	Evidence, Coming_to_believe	New — the inverse of Verification: inferring a hidden cause from a surface indicator, rather than confirming a claim. Classic Look-For content. Letter prefixes are another enumerated value set
7	Autonomous system behavior	"the system automatically changes the sex code to 8 and displays both the exact parental start week and the parental end week"	Cause_change family, but agentivity is the issue	New — every frame in the current inventory presupposes the officer as Agent. Here the system is an autonomous agent whose behavior the officer must anticipate (tacit knowledge, same category as the M163 finding). Candidate induced frame SYSTEM_EFFECT (Trigger_condition, System, Effected_change, Displayed_output)
8	Quantified limits / maximums	"Up to 15 weeks... may be paid"; 70 weeks (Pilot 24); 104 weeks BP extension; "maximum... cannot be exceeded"	Capacity, Sufficiency — poor fits	Not a frame — these are numeric parameter constraints. Recommend extending the enumerated-value-set principle: thresholds as typed ontology properties (per-BT maxima), referenced by frames rather than parsed as frames
9	Definitional / temporal window computation	"The maternity window... starts on the earlier of the following 2 dates... ends on the later of..."	None — this is min/max over date expressions	Not frame-semantic — a derived-parameter computation rule. Analogous to A5's structured-extraction determination; also feeds Epic B, since window membership is the Protasis of many downstream branches
What is genuinely new vs. step-by-step

The step-by-step sections of this document contain nothing outside the existing inventory — the numbered steps are Verification, Action/Transaction (M106/M107 field:value content, very heavy here), Referral (Level 2 reassignment, Integrity), Communication, and conditional branching, all already homed in A1–A5 and Epic B.

The new material is concentrated in the expository layers, and it clusters into three kinds:

New frame candidates (#1/2, #5, #6, #7) — Eligibility/Entitlement, Sanction imposition, Diagnostic inference, System behavior. Of these, Eligibility and System behavior look like A6 induction cases; Sanction and Diagnostic inference each have a plausible FrameNet anchor worth testing first.

Extensions to existing features (#3, #4) — evidentiary sufficiency rules attach to A1 as FE-filler acceptability conditions rather than a new frame; permission plus authority-level extends A2's deontic coverage from two modalities to three.

Non-frame knowledge types (#8, #9) — numeric thresholds and computed temporal windows, which belong in the ontology/structured-extraction lane, confirming that the three-layer mapping ("Know" ≈ frame definitions and parameters) includes content that should never pass through the frame parser at all.

Suggested research stories

Fitting the board's template, the highest-value cuts would be: a 2–3 day story under A2 testing Prohibiting_or_licensing/Permitting against the permission-plus-authority-level sentences (with a recommendation on whether Authorized_role needs induction); a 2-day story testing Rewards_and_punishments against the disentitlement sentences before inducing a sanction frame; a 2–3 day A6 story on the Eligibility/Entitlement pair (one induced frame or two); a 2-day story under A1 drafting the proof-of-pregnancy acceptability rules as Medium/Unconfirmed_content constraints, as the first concrete instance of the Look-For-as-FE-recognition-rules layer; and a short spike on SYSTEM_EFFECT, since it also bears on Epic B (system-triggered state changes are branch conditions the officer doesn't control).

One board-level observation: this is the first document analyzed that isn't Direct Deposit, so whatever lands from it doubles as an early data point for Feature C1's "≥3 structurally different procedures" criterion — worth tagging these stories accordingly.