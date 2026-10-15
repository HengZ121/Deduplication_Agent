"""Export relative DITA file path, body type, word count, and extracted text content.

Counts the text physically stored in each .dita file, including titles, tables,
notes and body text. Excludes prolog/metadata and XML attributes/markup. Does not
expand conref/xref links, collapse duplicates, or count .ditamap organization files.
Reuses the project's Unicode word tokenizer (including French and contractions).
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from pathlib import Path
import xml.etree.ElementTree as ET

from run_passage_pipeline import word_tokens


def content_text(element: ET.Element) -> str:
    """Keep authored content in XML order; omit metadata and keyref subtrees."""
    if element.tag.rsplit('}', 1)[-1] in {'prolog', 'metadata'} or element.get('keyref'):
        return ''
    parts = [element.text or '']
    for child in element:
        parts.extend([content_text(child), child.tail or ''])
    return ' '.join(parts)


def body_type(root: ET.Element) -> str:
    """Name the topic's direct body element (conbody, refbody, taskbody, ...)."""
    for child in root:
        name = child.tag.rsplit('}', 1)[-1]
        if name.endswith('body'):
            return name
    return ''


def export_counts(root: Path, branches: list[str], output: Path) -> int:
    """Use paths relative to the dataset root so identical basenames stay distinct.

    Parse everything before writing. A bad XML file raises an error rather than
    silently omitting a file or recording an invented zero word count.
    """
    root = root.resolve()
    folders = [root / branch for branch in branches] if branches else [root]
    for folder in folders:
        if not folder.is_dir():
            raise FileNotFoundError(f'Dataset folder not found: {folder}')
        if not folder.resolve().is_relative_to(root):
            raise ValueError(f'Branch must be inside dataset root: {folder}')
    paths = sorted({path for folder in folders for path in folder.rglob('*.dita')})
    if not paths:
        raise ValueError(f'No .dita files found under {root}')
    def count_file(path):
        try:
            topic = ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise ValueError(f'Invalid XML in {path}: {exc}') from exc
        # Remove XML indentation while retaining the original wording,
        # punctuation, case and accents in the exported content column.
        text = ' '.join(content_text(topic).split())
        return path.relative_to(root).as_posix(), body_type(topic), len(word_tokens(text)), text
    # These exports contain tens of thousands of small files. Bounded parallel
    # reads reduce filesystem wait time; map preserves the sorted output order.
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(count_file, paths))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['file_path', 'body_type', 'word_count', 'content'])
        writer.writerows(rows)
    print(f'{output}: {len(rows):,} files; {sum(row[2] for row in rows):,} words')
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Dataset root directory')
    parser.add_argument('--branches', nargs='*', default=[], help='Optional subfolders to include')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export_counts(args.root, args.branches, args.output)


if __name__ == '__main__':
    main()
