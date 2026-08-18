# Validation report

Sample Brain's local validation report closes the original `PROJECT_META.md`
validation contract without exposing private sample paths.

Run it against a local catalog:

```powershell
python tools/validate_report.py --db data/catalog.db --out reports/VALIDATION_REPORT.md
```

The generated report is local and `reports/` is gitignored. It checks:

- catalog consistency (`samples` versus `features`)
- BPM plausibility using explicit BPM tokens in filenames as weak labels
- key/root plausibility using explicit key+mode filename tokens as weak labels
- loop/one-shot and coarse instrument Autotype quality from explicit path/filename tokens
- current key-confidence distribution against the FL export gate (`0.55`)

Weak labels are deliberately conservative: a missing filename/folder hint is
reported as missing evidence, not as a model failure. Raw sample paths are not
written into the report.
