# ort_output.zip (2026-10-15 ORT export, split)

The original archive (199 MB) exceeds GitHub's 100 MB per-file limit, so it is
stored here as 45 MB parts. It contains the ORT `output/dita/{en,fr,pr-ort}` export.

SHA-256 of the reassembled file:
`d4051ee5d1fa2b06927213135155c20dc96c5b17e011cea57981c0dcee38118a`

## Reassemble

Git Bash / Linux / macOS:

    cat ort_output.zip.part* > ort_output.zip

PowerShell:

    cmd /c copy /b "ort_output.zip.part*" ort_output.zip

Windows cmd:

    copy /b ort_output.zip.part* ort_output.zip
