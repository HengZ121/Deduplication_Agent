#!/usr/bin/env python3
"""Download and safely extract the NLTK FrameNet 1.7 corpus locally."""

from __future__ import annotations

import shutil
import urllib.request
import zipfile
from pathlib import Path


URL = "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/framenet_v17.zip"
ROOT = Path(__file__).resolve().parent / ".nltk_data_clean"
ARCHIVE = ROOT / "framenet_v17.zip"
CORPORA = ROOT / "corpora"
TARGET = CORPORA / "framenet_v17"
REQUIRED = ("frameIndex.xml", "frRelation.xml", "fulltextIndex.xml", "luIndex.xml", "semTypes.xml")


def installed() -> bool:
    return all((TARGET / filename).is_file() for filename in REQUIRED)


def main() -> None:
    if installed():
        print(f"FrameNet 1.7 is already installed at {TARGET}")
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    CORPORA.mkdir(parents=True, exist_ok=True)
    print(f"Downloading FrameNet 1.7 from {URL}")
    with urllib.request.urlopen(URL) as response, ARCHIVE.open("wb") as destination:
        shutil.copyfileobj(response, destination)
    print("Extracting corpus XML files (this may take a few minutes on Windows)")
    with zipfile.ZipFile(ARCHIVE) as archive:
        extraction_root = CORPORA.resolve()
        for member in archive.infolist():
            destination = (CORPORA / member.filename).resolve()
            if extraction_root not in destination.parents and destination != extraction_root:
                raise ValueError(f"Unsafe archive member: {member.filename}")
        archive.extractall(CORPORA)
    ARCHIVE.unlink(missing_ok=True)
    if not installed():
        raise RuntimeError("FrameNet extraction completed but required indexes are missing")
    print(f"FrameNet 1.7 installed at {TARGET}")


if __name__ == "__main__":
    main()

