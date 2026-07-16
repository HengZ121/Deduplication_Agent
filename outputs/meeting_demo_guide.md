# FrameNet penalty demo — meeting guide

## 30-second opening

“The question was whether FrameNet already has one frame that represents a coded penalty, its trigger condition, and its termination rule. My finding is that `Rewards_and_punishments` is the correct primary frame for the imposition event, but a single FrameNet frame is not enough for executable policy logic. I therefore recommend a composite that keeps FrameNet semantics and adds structured condition, code, and lifecycle fields.”

## Demo flow (3–5 minutes)

1. Start with **D25 — threshold imposition**. Point out the five columns: condition, Frame, participants, typed consequence, and time.
2. Say: “FrameNet gives us `Agent`, `Evaluee`, `Response`, `Reason`, and `Time`. D25 is resolved against a controlled code list, while `< 600 hours` stays as machine-readable rule logic.”
3. Switch to **D25 — temporary suppression**. Say: “The same words can be negated. This must not create a positive penalty event; polarity and the exception interval are explicit.”
4. Switch to **D25 — termination boundary**. Say: “Termination changes an existing penalty. It is a lifecycle event linked to D25, not a second punishment.”
5. Optionally show **D33** for a bounded interval or **D5** for `OR` plus date arithmetic.

## The decision to ask the team to approve

Approve this minimum annotation model:

- primary Frame: `Rewards_and_punishments` for positive/negated imposition;
- native FEs: `Agent`, `Evaluee`, `Response`, `Reason`, `Time`;
- controlled entity: `PenaltyCode`;
- domain fields: `RuleCondition`, `polarity`, `modality`, `effectiveFrom`, `effectiveThrough`;
- lifecycle events: terminate, rescind, and suspend remain distinct.

## Likely questions and short answers

**Why not put the condition in `Reason`?**  
`Reason` is suitable for the human-readable rationale, but it does not preserve operators such as `< 600`, negation, `AND/OR`, exceptions, or relative-date calculations.

**Why not use `Imposing_obligation`?**  
That frame creates a duty. D25 denies entitlement or applies an adverse consequence, so `Rewards_and_punishments` is the closer semantic match.

**Is disentitlement really punishment?**  
FrameNet is being used for linguistic semantics, not a legal characterization. The frame best matches an authorized actor applying an adverse consequence for a reason. The domain type still records `disentitlement`, `disqualification`, or monetary `penalty` precisely.

**What about “does not impose”?**  
Annotate the potential imposition with negative polarity and retain the exception condition. Do not assert that a penalty instance exists.

**What is the difference between terminate and rescind?**  
Termination ends an existing decision prospectively. Rescission invalidates it retrospectively. They must remain separate lifecycle operations.

**Was this tested on more than the supplied sentence?**  
Yes. Nine traced examples were mapped from the local procedure corpus, covering imposition, suppression, termination, and rescission.

## Safe closing

“Today I am asking for agreement on the semantic pattern, not claiming that the full automatic extractor is complete. Once the pattern is approved, the next implementation step is a JSON schema and an extraction/evaluation pass over the annotated examples.”

