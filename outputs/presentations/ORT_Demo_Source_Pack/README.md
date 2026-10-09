# ORT demo source pack

This pack accompanies the revised 15-slide main presentation and its source appendix.
Source DITA files are byte-for-byte copies. Their relative paths are preserved under `raw/`.
`ROW_FILES.csv` maps each slide row/example ID to every counted physical file and parent map.
Parent maps are provenance evidence; this selected pack is not a complete publishable DITA corpus.
Body conref dependencies are included. Xref-linked publications are not recursively copied.

Page 2 uses E01–E05. Page 3 uses P01–P04. Page 4 uses I01–I03.
Page 5 uses N01. Page 6 uses A01. Page 7 uses E02 and R01.
Open `index.html` for complete extracted bodies, original XML, and every row's file links.

Counting rule for page 3: group equal expanded body-structure fingerprints, count distinct
physical DITA paths and distinct parent maps. Token count is the existing audit tokenizer's
count of one expanded body, including link-description text. These are not counts of words
manually selected for a slide. IDs/styling and case/whitespace are normalized; body titles are separate.
The four rows are selected English groups from 1,398 bilingual groups containing 4,105 files.
The 629 review shortlist uses at least 40 tokens, no detected local step jump, and equal extracted
context signatures. It does not certify common policy scope.

Page 4 counts repeated existing internal XML elements, with each physical section counted once.
Several sections can occur in one publication, which explains 173 sections versus 113 documents.
Groups overlap, so their counts are not additive savings.

N01: the two common-note files have 16 and 2 map references respectively, 18 total
(see the audit source-reference table). Map reference counts exclude body conrefs.

The pair examples retain their actual audit labels, not new verified semantic judgments.
For E04 and E05 especially, similarity does not establish interchangeable applicability.
