# DITA file word counts

Each CSV has three columns: `file_name`, `word_count`, and `content`. File names are
relative to the dataset root, preserving the language and folder to avoid collisions.

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
  attributes and prolog/metadata are excluded. References are not expanded.
- Shared/duplicate files remain separate rows. `.ditamap` files are excluded.
- Uses the existing pipeline Unicode word tokenizer: contractions and hyphenated
  words count as single tokens; numeric tokens also count.
- These are file-level counts, not the previous body-node-only box-plot counts.

Run from the repository root:

```powershell
py count_dita_file_words.py --root unzipped/kmt_dita_1/kmt_dita --branches en fr --output outputs/file_word_counts/kmt_file_word_counts.csv
py count_dita_file_words.py --root unzipped/ort_new_dita/dita --branches en_EN fr_FR --output outputs/file_word_counts/ort_file_word_counts.csv
```
