# FrameNet recommendation for typed penalties under conditions

## Decision

Use `Rewards_and_punishments` as the primary FrameNet frame for an actual imposition of a disentitlement, disqualification, or penalty. It is the best semantic fit when an authorized actor applies an adverse consequence to a client for a stated reason.

Do not attempt to encode the whole rule in that frame alone. The corpus sentences also express a rule condition, a controlled code, and sometimes a termination or suppression event. Those are not all native core Frame Elements (FEs) of `Rewards_and_punishments`. Represent them as a small composite:

1. a `Rewards_and_punishments` event for imposition;
2. a project-level `RuleCondition` linked by `triggeredBy` (and optionally aligned to a FrameNet condition frame in a later annotation pass);
3. a controlled `PenaltyCode` entity linked to the frame's `Response`;
4. `Time` for a directly stated effective interval or boundary; and
5. a separate lifecycle event for terminate/rescind/suspend, rather than treating termination as another punishment.

For “does not impose” or “cannot impose,” retain the potential imposition event but mark it as negated or prohibited. Where an explicit agent prevents the imposition, `Preventing_or_letting` is a useful secondary candidate. For termination, use a lifecycle relation such as `terminatesPenalty` with the termination boundary; a dedicated domain lifecycle type is preferable to forcing the sentence into `Rewards_and_punishments`.

## Why this frame

The FrameNet description of `Rewards_and_punishments` concerns an `Agent` performing a `Response` as a consequence of the actions, beliefs, or circumstances associated with an `Evaluee`, with a `Reason` for the judgment. Its lexical units include punishment-oriented predicates such as *discipline*, *punish*, *penalty*, and *punishment*. This matches “the officer imposes D25 on the client because the qualifying-hours requirement is not met.”

It is a better primary choice than the near neighbours below:

| Candidate | Result of corpus test | Recommendation |
|---|---|---|
| `Rewards_and_punishments` | Captures authorized actor, affected client, adverse consequence, and reason. | Primary frame for positive imposition. |
| `Imposing_obligation` | Models creation of a duty, not denial of benefit or application of a sanction. | Reject as the primary frame. |
| `Preventing_or_letting` | Fits prevention/suppression wording such as “does not impose” or “cannot be imposed,” but not the penalty event itself. | Secondary frame or polarity treatment for suppression. |
| `Revenge` | Inherits the general punishment concept but implies retaliation and is inappropriate for administrative eligibility decisions. | Reject. |
| A generic condition frame | Can describe whether a rule antecedent holds, but omits the adverse consequence and its participants. | Use only as a companion to the primary frame. |

FrameNet distinguishes frames, their FEs, and lexical units, and supports frame-to-frame relations. The public FrameNet data page identifies Frame Index entries as the source for frame definitions and FEs and describes full-text annotation as marking evoked frames and their associated FEs. The current downloadable release is FrameNet 1.7, while the website may contain newer, less fully checked data.

## Frame Element and domain mapping

The following mapping preserves FrameNet semantics while meeting the business fields in AC3.

| Required meaning | Representation | Status |
|---|---|---|
| Who imposes | `Agent` | Native `Rewards_and_punishments` FE. Use the officer, Commission, agent, system, or other authorized body. |
| On whom | `Evaluee` | Native core FE. Usually the client or claimant. It may be implicit and resolved from document context. |
| Which penalty | `Response` | Native core FE for the adverse consequence. Link the span to a controlled `PenaltyCode` entity rather than using the free text as the identifier. |
| Why | `Reason` | Native core FE for the reason behind the judgment. It can point to the failed requirement at a descriptive level. |
| Under what condition | `RuleCondition` plus `triggeredBy` | Domain extension. Preserve logical operators, thresholds, negation, and exceptions. Do not collapse this into `Reason` if machine-executable logic is required. |
| Effective when | `Time`, `effectiveFrom`, `effectiveThrough` | `Time` is a native peripheral FE; normalized boundaries are domain extensions. |
| Terminated/rescinded/suspended when | Separate lifecycle event with `terminatesPenalty`, `rescindsPenalty`, or `suspendsPenalty` | Domain extension. The event references the original penalty instance/code and its temporal boundary. |
| Whether imposed | `polarity` / `modality` | Annotation metadata. Needed for “not imposed,” “may be imposed,” “must be imposed,” and “cannot be imposed.” |

Recommended normalized record for the motivating sentence:

```json
{
  "frame": "Rewards_and_punishments",
  "trigger": "is imposed",
  "agent": { "text": null, "status": "DNI", "resolvedFromContext": "officer" },
  "evaluee": { "text": "the client" },
  "response": {
    "text": "25 - Maternity benefits - Minor attached disentitlement (D25)",
    "code": "D25",
    "label": "Maternity benefits - Minor attached",
    "sanctionType": "disentitlement"
  },
  "reason": { "text": "has not accumulated at least 600 insurable hours" },
  "ruleCondition": {
    "operator": "lessThan",
    "left": "client.accumulatedInsurableHours",
    "right": 600,
    "unit": "hour"
  },
  "polarity": "positive",
  "modality": "asserted-rule",
  "source": {
    "documentId": 598,
    "path": "procedure/task/conv_regmat.json"
  }
}
```

`DNI` here means that the FE is not overtly expressed in the sentence but is recoverable as a definite participant from the procedural context. If the annotation system does not support FrameNet null-instantiation labels, use `implicit: true` instead.

## Corpus mappings

The examples below come from `outputs/procedure_pipeline/procedure_documents_with_clusters.csv`. Document ID and original `path` provide traceability to the source content.

### 1. D25 imposition: threshold condition

**Source:** document 598, `procedure/task/conv_regmat.json`

> A 25 - Maternity benefits - Minor attached disentitlement (D25) is imposed if the client has not accumulated at least 600 insurable hours.

- Frame/trigger: `Rewards_and_punishments` / “is imposed”
- Agent: implicit officer or authorized system (`DNI`)
- Evaluee: “the client”
- Response/code: D25, Maternity benefits - Minor attached disentitlement
- Reason: insufficient accumulated insurable hours
- RuleCondition: accumulated hours `< 600`
- Time: not stated in this sentence
- Polarity/modality: positive, asserted rule

### 2. D25 suppression: temporary exception

**Source:** document 598, `procedure/task/conv_regmat.json`

> As a result, the officer does not impose a D25 on claims with a BPC between w/c 2310 and w/c 2361.

- Potential frame/trigger: `Rewards_and_punishments` / “impose”
- Agent: “the officer”
- Evaluee: client associated with the qualifying claim (implicit)
- Response/code: D25
- RuleCondition: BPC within the inclusive range w/c 2310–w/c 2361
- Polarity: negative
- Secondary analysis: suppression/exception; optionally add `Preventing_or_letting` if an explicit cause of the non-imposition is annotated from preceding context

### 3. D25 termination: conversion boundary

**Source:** document 598, `procedure/task/conv_regmat.json`

> If the information on file allows for the disentitlement to be terminated, it is terminated on the Friday of the week before the conversion week.

- Event: `PenaltyTermination` domain lifecycle event; trigger “is terminated”
- Affected penalty: context-resolved D25/disentitlement
- Agent: implicit officer/system
- RuleCondition: information on file permits termination
- Termination time: Friday of the week immediately preceding the conversion week
- Normalization: `effectiveThrough = friday(previousWeek(conversionWeek))`

### 4. D33 imposition: condition and bounded duration

**Source:** document 18, `procedure/activity/calc_sick.json`

> When clients do not prove that they would be otherwise available for work for the entire period of incapacity or for part of that period, the officer imposes a 33 - Incapacity proven but not otherwise available disentitlement (D33) from the date on which the condition is not met until the end of the period of incapacity, or until the date on which the client is otherwise available for work.

- Frame/trigger: `Rewards_and_punishments` / “imposes”
- Agent: “the officer”
- Evaluee: “clients”
- Response/code: D33
- Reason/condition: failure to prove otherwise available for work
- EffectiveFrom: date on which the condition is not met
- EffectiveThrough: earlier applicable boundary among end of incapacity and restoration of availability
- Important: retain the disjunction in the temporal rule; a flat `Time` string is insufficient for execution

### 5. D34 imposition: status change and start rule

**Source:** document 15, `procedure/activity/calc_mat_par.json`

> If the officer is informed that the client is no longer caring for the child during the PW, the officer imposes a definite or indefinite 34 - Parental benefits entitlement conditions not met disentitlement (D34) starting the Monday after the week in which the client is no longer entitled to benefits.

- Frame/trigger: `Rewards_and_punishments` / “imposes”
- Agent: “the officer”
- Evaluee: “the client”
- Response/code: D34; duration class is definite or indefinite
- RuleCondition: client no longer caring for child during PW and officer informed
- EffectiveFrom: Monday following the loss-of-entitlement week

### 6. D42 imposition: misconduct finding

**Source:** document 41, `procedure/activity/dismissal.json`

> If the officer finds that the client was suspended due to misconduct, the officer imposes an indefinite 42 - Suspension from employment disentitlement (D42).

- Frame/trigger: `Rewards_and_punishments` / “imposes”
- Agent: “the officer”
- Evaluee: “the client”
- Response/code: indefinite D42
- Reason: suspension due to misconduct
- RuleCondition: officer finding confirms the misconduct-based suspension

### 7. D42 termination: alternative conditions

**Source:** document 41, `procedure/activity/dismissal.json`

> A D42 can be terminated when the suspension ends, if the client accumulates enough insurable hours of employment from another employer to qualify for benefits, or if the client is dismissed or quits.

- Event: `PenaltyTermination`; trigger “terminated”
- Affected penalty: D42
- Modality: permitted (“can”)
- RuleCondition: suspension ends OR qualifying hours from another employer are accumulated OR client is dismissed OR client quits
- Time: time at which the selected terminating condition becomes true

### 8. D5 termination: explicit temporal calculation

**Source:** document 58, `procedure/activity/labour_dispute.json`

> A D5 is terminated on the day before the date on which the labour dispute ends or on the day before the date on which the client became regularly employed elsewhere in insurable employment.

- Event: `PenaltyTermination`; trigger “is terminated”
- Affected penalty: D5
- RuleCondition: labour dispute ends OR client begins qualifying regular employment elsewhere
- Termination time: one day before the applicable condition date
- Normalization: `effectiveThrough = conditionDate - P1D`

### 9. D15 rescission versus termination

**Source:** document 26, `procedure/activity/claim_procedure.json`

> Once the missing information is received, the officer can terminate or rescind the disentitlement, depending on certain conditions and deadlines.

- Event: two alternative lifecycle operations, `PenaltyTermination` and `PenaltyRescission`
- Agent: “the officer”
- Affected penalty: D15 from document context
- RuleCondition: missing information received plus operation-specific conditions/deadlines
- Modality: permitted (“can”)
- Modeling note: rescission should invalidate the decision retrospectively; termination ends it prospectively. They must not be represented by one undifferentiated `end` relation.

## Annotation and implementation rules

1. Create a `Rewards_and_punishments` annotation only when the text asserts, requires, permits, or negates an imposition. Record polarity and modality independently.
2. Put the complete penalty phrase in `Response`, then resolve its code against an enumerated code set. Store code and label separately.
3. Use `Reason` for the human-readable rationale. Store executable antecedents in `RuleCondition`, preserving `AND`, `OR`, negation, comparisons, and scoped exceptions.
4. Annotate `Time` spans, but also normalize relative expressions against document variables such as `conversionWeek`.
5. Model `terminate`, `rescind`, and `suspend` as distinct lifecycle events linked to the original penalty. Do not annotate them as new punishment events.
6. Resolve omitted agents/evaluees from document context and mark the resolution as implicit. Do not invent an actor where the source provides none.
7. Keep source `document_id`, source `path`, exact sentence, and character offsets in production annotations.

## Acceptance-criteria assessment

- **AC1:** Met. `Rewards_and_punishments` and four near-neighbour strategies were tested against positive imposition, negative/suppressed imposition, termination, and rescission sentences.
- **AC2:** Met. The recommendation is the primary frame plus a condition/code/lifecycle composite.
- **AC3:** Met. Actor, affected party, code, condition, and effective time mappings are documented.
- **AC4:** Met. Nine corpus examples are mapped, including positive imposition and suppression/termination/rescission cases.

## References

- Berkeley FrameNet, “FrameNet Data”: https://berkeleyfn.framenetbr.ufjf.br/framenet_data
- FrameNet Constructicon of German, `Rewards_and_punishments` aligned entry (useful corroboration of the Berkeley frame definition and FE inventory): https://framenet-constructicon.hhu.de/framenet/frame?id=569
- Local corpus: `outputs/procedure_pipeline/procedure_documents_with_clusters.csv`

