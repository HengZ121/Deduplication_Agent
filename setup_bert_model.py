#!/usr/bin/env python3
"""Download the local BERT model used by the FrameNet demo.

The mapper loads this model with local_files_only=True at runtime, so the web app
does not unexpectedly call Hugging Face while a demo is running.
"""

from __future__ import annotations

from hybrid_frame_mapper import BERT_MODEL_NAME


def main() -> None:
    from transformers import AutoModelForQuestionAnswering, AutoTokenizer

    AutoTokenizer.from_pretrained(BERT_MODEL_NAME)
    AutoModelForQuestionAnswering.from_pretrained(BERT_MODEL_NAME)
    print(f"BERT QA model is available locally: {BERT_MODEL_NAME}")


if __name__ == "__main__":
    main()
