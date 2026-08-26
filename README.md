# Deduplication Agent: FrameNet Penalty Mapper

This repository contains a local demo for mapping administrative penalty text into FrameNet-aligned JSON. The current focus is the `framenet_*` mapper/UI: it extracts penalty lifecycle events, validates them against NLTK FrameNet 1.7 where possible, and renders a browser-based annotated document view.

## What It Does

The mapper combines three layers:

1. Domain rules for penalty lifecycle events such as imposition, termination, rescission, and suspension.
2. Optional spaCy dependency parsing for syntactic evidence, including agent, evaluee, condition, and time spans.
3. NLTK FrameNet 1.7 corpus lookup for official frame validation and candidate-frame fallback.

Confirmed domain events currently map to frames such as:

- `Rewards_and_punishments` for penalty imposition.
- `Activity_stop` for termination.
- `Activity_pause` for suspension.
- `Meet_specifications` for eligibility, qualification, and entitlement-condition statements.
- `Submitting_documents` for proof/document submission requirements.
- `Deny_or_grant_permission` for deontic permission and authority-level statements.
- `Coming_to_believe` for diagnostic inference from evidence such as letters or code prefixes.
- `Cause_change` for autonomous system behavior and state/display changes.
- domain-only lifecycle events where no exact FrameNet frame is assigned.

Numeric limits and derived temporal windows are processed as structured domain rules, not FrameNet frames. They are kept out of official frame assignment because Task 2 identifies them as parameter/computation knowledge rather than frame-semantic events.

## Domain Frame Canonicalization

`procedure_sentences_with_multiple_frames.csv` is intentionally a high-recall
lexical-candidate report. A shared word such as `meet`, `file`, `set`, or `rate`
can therefore produce several FrameNet senses that are not valid in the
procedure context.

Run the precision-oriented canonicalization stage after generating that report:

```powershell
py canonicalize_frame_candidates.py
```

The canonicalizer preserves the raw candidates for audit, but downstream output
uses a controlled procedure-domain inventory. It applies context rules for the
highest-frequency lexical collisions, separates structured non-frame knowledge
(rates, totals, history labels, waiting-period states), and routes unresolved
domain candidates to review rather than forcing a frame assignment.

Outputs:

- `outputs/procedure_sentences_canonicalized.csv`
- `outputs/procedure_frame_canonicalization_summary.json`

When no supported penalty lifecycle trigger is found, the mapper can still return `FrameNetCandidate` records by searching visible lexical-unit matches across the NLTK FrameNet registry. These are explicitly marked as `candidate_only`; they are evidence, not confirmed semantic parses.

## Setup

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Install the optional spaCy English model:

```powershell
py -m spacy download en_core_web_sm
```

Install FrameNet 1.7 data:

```powershell
py setup_framenet_data.py
```

The setup script downloads and extracts FrameNet into `.nltk_data_clean/corpora/framenet_v17`, which the registry loader checks before falling back to the user's global NLTK data paths.

## Running The Demo UI

Start the local web app:

```powershell
py framenet_ui.py
```

Open:

```text
http://127.0.0.1:8765/
```

Paste text or upload a supported document, then click `Map to JSON`. The UI shows:

- JSON output.
- highlighted source text for mapped semantic spans.
- syntactic and official FrameNet evidence.
- candidate FrameNet frames for otherwise-unmapped sentences.

Supported upload formats are `.txt`, `.md`, `.json`, and `.docx`.

## Hybrid Frame Demo

The repository also includes a focused hybrid mapper for 11 representative employment/social-benefit frames, including `Rewards_and_punishments`, `Verification`, `Scrutiny`, `Being_employed`, `Have_as_requirement`, `Evidence`, `Submitting_documents`, `Assessing`, `Request`, `Receiving`, and `Activity_stop`.

The rule layer provides deterministic candidate detection. A local BERT QA model (`deepset/bert-base-cased-squad2`) is then used in two explicit ways:

1. BERT frame scorer: computes similarity between the sentence and a frame prompt built from the domain rule description, official FrameNet frame definition, and official FrameNet lexical units.
2. BERT QA element extraction: asks frame-specific questions enriched with official FrameNet frame-element definitions, then extracts source-text spans for configured frame elements.

Raw FrameNet exemplar sentences are not used by default because they are general-domain and often do not resemble employment/social-benefit procedure language. Procedure-derived exemplars can be added later as curated training/evaluation data.

Download the local BERT model once before running the BERT-enhanced demo:

```powershell
py setup_bert_model.py
```

At runtime the mapper uses `local_files_only=True`, so the web app does not call the network during a demo. If the model is missing, the JSON reports BERT as unavailable and falls back to rule-based extraction.

Generate the static demo:

```powershell
py generate_hybrid_frame_demo.py
```

Open:

```text
outputs/hybrid_frame_demo.html
```

Generate a reproducible CSV of 50 real dataset texts targeted to the official
FrameNet `Verification` frame (ID 1230), with local BERT scores, extracted frame
elements, the highest-ranked competing frame, and source-document provenance:

```powershell
py generate_verification_frame_csv.py
```

The output is `outputs/verification_frame_bert_mappings_50.csv`. Generation
fails rather than silently falling back when the local BERT model or FrameNet
1.7 corpus is unavailable.

The static demo uses real sentences sampled from `procedure.zip`, two per configured frame, so it is stable and does not require live dataset scanning during presentation.

## JSON Shape

Top-level output includes:

- `schemaVersion`
- `sourceDocument`
- `annotationMethod`
- `syntacticParser`
- `frameNetRegistry`
- `eventCount`
- `confirmedEventCount`
- `candidateEventCount`
- `events`
- `warnings`

A confirmed event includes fields such as:

- `eventType`
- `frame`
- `trigger`
- `frameElements`
- `frameNet`
- `dependencyAnalysis`
- `ruleCondition`
- `penaltyCode`
- `polarity`
- `modality`
- `source`

An unmatched sentence with FrameNet candidates is represented as:

```json
{
  "eventType": "FrameNetCandidate",
  "frame": null,
  "mappingStatus": "candidate_only",
  "candidateFrames": [
    {
      "frame": "Receiving",
      "matchedLexicalUnit": "receive.v",
      "matchedText": "receive",
      "confidence": "lexical_match_candidate"
    }
  ]
}
```

## Client Environment Notes

NLTK FrameNet is a local corpus reader, not a hosted API. The app does not need live network access during mapping if dependencies and `framenet_v17` are already installed.

In locked-down client environments, online downloads may fail because of registry, proxy, or SSL certificate restrictions. If that happens, prepare the corpus offline and copy it into one of NLTK's data paths, for example:

```text
C:\Users\<user>\nltk_data\corpora\framenet_v17
```

Verify FrameNet availability with:

```powershell
py -c "from nltk.corpus import framenet as fn; print(len(fn.frames()))"
```

If FrameNet data is unavailable, confirmed domain mapping still works, but official FrameNet validation and candidate-frame fallback are limited.

## Tests

Run the mapper test suite:

```powershell
py -m unittest -q test_framenet_mapper.py
```

Tests that require optional local resources, such as the FrameNet corpus or spaCy model, are skipped automatically when those resources are not installed.

## Duplicate Detection for Procedure JSON or KMT DITA

`run_procedure_pipeline.py` accepts both the original `procedure.zip` JSON
dataset and an extracted KMT DITA directory. For DITA, each `.ditamap` is one
article: its referenced topics are read in map order and local `conref` common
notes are expanded into the article text. Shared files under `common_notes` are
not treated as independent documents.

Run the KMT dataset with:

```powershell
py run_procedure_pipeline.py --input KMT_dita --output-dir outputs/kmt_dita_pipeline --require-api-key
```

Input format is auto-detected. Because KMT is bilingual, automatic mode disables
English-only TF-IDF stop words and restricts candidate pairs to the same language.
Use `--language-scope all` only when cross-language translation matching is the
intended task. The legacy `--zip procedure.zip` option remains supported.
