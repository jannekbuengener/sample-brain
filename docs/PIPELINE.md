# Pipeline (v1)

## Goal
Generate **consistent titles** in the format:

`HH, closed, [LOOP] - 132BPM, F#m, dark/vintage`

Rules:
- Existing title info wins.
- Analysis only fills missing parts.
- Genre is derived from folder path (or tags), not the title.

## What this pipeline produces
- `reports/TITLE_SUGGESTIONS.csv` (old title -> new title suggestions)
- `reports/RENAME_PREVIEW.ps1` (safe preview; only applies if you pass `-Apply`)

## Run
```powershell
pwsh -File .\make_title_suggestions.ps1
```

## Apply renames (optional)
```powershell
pwsh -File .\make_title_suggestions.ps1 -Apply
```

**Tip:** Run once without Apply, inspect the CSV, then decide.
