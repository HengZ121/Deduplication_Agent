# Frame Candidate Statistics

This note documents how candidate FrameNet frames were counted across `procedure.zip`.

## Goal

The goal is to discover which FrameNet frames appear to fit the procedure dataset by counting lexical evidence across the sample corpus. `procedure.zip` is treated as the sample dataset.

This is a discovery/statistics pass, not a final semantic annotation pass. A counted frame means at least one official FrameNet lexical unit for that frame appeared in a sentence. It does not mean the sentence has been fully disambiguated or that frame elements have been reliably extracted.

## Output

The generated CSV is:

```text
outputs/framenet_candidate_frame_counts.csv
```

Columns:

- `frame`: FrameNet frame name.
- `frameId`: FrameNet frame ID.
- `sentenceOccurrences`: number of sentences where this frame had at least one lexical-unit match.
- `matchedLexicalUnitOccurrences`: total lexical-unit matches for the frame.

## Method

The first implementation attempted to call candidate matching sentence by sentence. That was too slow because it repeatedly scanned thousands of FrameNet lexical units for every unmatched sentence.

The current implementation uses an indexed approach:

1. Load NLTK FrameNet 1.7 once.
2. Read all official lexical units with `registry._fn.lus()`.
3. Generate lightweight surface forms for each lexical unit.
4. Build an index:

```text
surface form -> candidate FrameNet frame(s)
```

Examples:

```text
receive, receives, received, receiving -> Receiving
benefit, benefits -> Conferring_benefit, Social_event, ...
terminate, terminates, terminated, terminating -> Activity_stop
```

Then the script processes the procedure corpus:

1. Read supported files from `procedure.zip`.
2. Extract text from `.json`, `.txt`, `.md`, and `.docx` files.
3. Split text into sentences using the same sentence splitter as the mapper.
4. Tokenize each sentence into words and short phrases.
5. Look up each token/phrase in the lexical-unit index.
6. Count each frame at most once per sentence.
7. Save aggregate frame counts to CSV.

This changes the expensive operation from repeated full FrameNet scans to dictionary lookups.

## Run Summary

Command:

```powershell
py count_framenet_candidates.py
```

Observed run summary:

```text
documents processed: 856
sentences processed: 164,942
matched sentences: 118,849
candidate frames found: 919
FrameNet LU surface forms indexed: 22,423
runtime: 11.04 seconds
```

## Top Candidate Frames

The top rows from the generated CSV were:

| Frame | Frame ID | Sentence Occurrences | LU Match Occurrences |
|---|---:|---:|---:|
| Statement | 43 | 27,628 | 50,094 |
| Text | 298 | 23,041 | 24,779 |
| Commerce_buy | 171 | 18,068 | 18,106 |
| Relative_time | 81 | 16,602 | 21,953 |
| Deciding | 363 | 16,280 | 17,049 |
| Social_event | 125 | 15,434 | 15,569 |
| Claim_ownership | 550 | 14,967 | 29,190 |
| Predicting | 425 | 14,352 | 14,352 |
| Calendric_unit | 229 | 14,160 | 16,664 |
| Coming_to_believe | 23 | 13,507 | 13,616 |

## Interpretation

High counts should be treated as ranking evidence, not final annotation truth.

Some frames are high because procedure text contains broad and frequent lexical units. For example, frames such as `Statement`, `Text`, `Relative_time`, and `Deciding` are expected to appear often in procedural documents. Domain-relevant frames such as `Coming_to_believe`, `Conferring_benefit`, `Activity_stop`, `Submitting_documents`, and `Rewards_and_punishments` should be reviewed against source examples in a controlled environment before being promoted into implemented mappings.

## Caveats

- This pass is lexical, not contextual disambiguation.
- Common lexical units can inflate broad frames.
- A sentence can count toward multiple frames.
- Frame elements are not extracted in this statistics pass.
- Counts are useful for candidate discovery and prioritization, but not sufficient for ontology approval.

## Related Files

- `count_framenet_candidates.py`: statistics script.
- `outputs/framenet_candidate_frame_counts.csv`: generated frame-count output.
- `framenet_mapper.py`: production/demo mapper for confirmed and candidate events.
