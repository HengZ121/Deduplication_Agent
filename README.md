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
- domain-only lifecycle events where no exact FrameNet frame is assigned.

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

