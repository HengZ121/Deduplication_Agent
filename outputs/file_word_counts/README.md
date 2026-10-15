# DITA file word counts

Older CSVs have three columns: `file_name` (relative to the dataset root), `word_count`,
and `content`. CSVs written by the current script have four: `file_path` (relative to the dataset root,
e.g. `en/KA-01029_EN/ka-01029_summary.dita`), `body_type` (the topic's body element: `conbody`, `refbody`,
`taskbody`, `body`, or empty when the file has none), `word_count`, and `content`.

`content` is the full extracted text used to calculate `word_count`, with whitespace
collapsed for readability. Original wording, punctuation, case and accents are retained.
CSV quoting preserves commas and quotation marks within content.

- KMT root: `unzipped/kmt_dita_1/kmt_dita`; includes `en` and `fr`.
- ORT root: `unzipped/ort_new_dita/dita`; includes `en_EN` and `fr_FR`, matching
  the branches used in the earlier ORT analysis. Parallel exports `en`, `fr` and
  `pr-ort` are not included.
- Every `.dita` file in those branches is included, even empty files, shared
  notes/tables, and files outside the previous clustering inventory.
- Counts include titles and body text physically present in the XML. XML markup,
  attributes, prolog/metadata, and the fallback text inside `keyref` elements
  are excluded. References are not expanded.
- Shared/duplicate files remain separate rows. `.ditamap` files are excluded.
- Uses the existing pipeline Unicode word tokenizer: contractions and hyphenated
  words count as single tokens; numeric tokens also count.
- These are file-level counts, not the previous body-node-only box-plot counts.

- `kmt_2026-10-07_onedrive_zip_file_word_counts.csv` uses the current script on the KMT
  export inside `OneDrive_1_10-7-2026.zip` (root `unzipped/KMT_2026-10-07/output/dita`).
  In that export every `fr` file is a byte-identical copy of its `en` file (English text,
  `KA-*_EN` folders). `kmt_2026-10-07_file_word_counts.csv` came from a different export
  with real French (`KA-*_FR` folders).

Run from the repository root:

```powershell
py count_dita_file_words.py --root unzipped/kmt_dita_1/kmt_dita --branches en fr --output outputs/file_word_counts/kmt_file_word_counts.csv
py count_dita_file_words.py --root unzipped/ort_new_dita/dita --branches en_EN fr_FR --output outputs/file_word_counts/ort_file_word_counts.csv
py count_dita_file_words.py --root unzipped/KMT_2026-10-07/output/dita --branches en fr --output outputs/file_word_counts/kmt_2026-10-07_onedrive_zip_file_word_counts.csv
```
