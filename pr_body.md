Closes #322
Refs #318
Depends on completed #320 and #321

## Delivered
- **TEMPO**: `<wert> BPM` — tempo control with BPM display, immediate change when stopped, next-bar boundary when playing
- **SYNC**: globales SYNC-Flag als core Control (Checkbutton, keine 'Master Tempo' Variante)
- **SessionTransport als Zeitautorität** — GUI akkumuliert keine eigene musikalische Zeit
- **gemeinsamer Grid-/Transportzustand** — multiple voices/sample refer to same SessionTransport
- **Native-Audio-Fallback** — DLL unavailable → graceful preview-only mode, no crash
- **bestehender Preview-Pfad erhalten** — WorkbenchPreviewPlayer path beibehalten
- **Tests und Doku** — 34 #322 Tests, 17 Session-Grid Tests, 117 Workbench Regressionen, CLI Smokes PASS

## Baseline note
- `test_signed_int64_frame_limits_are_enforced` reproduziert bereits auf `origin/main` rot, nicht durch #322 verursacht, nicht innerhalb dieses Slices repariert

## Validation
- 34 #322 Tests PASS
- 17 Session-Grid Tests PASS  
- 117 Workbench Regressionen PASS
- CLI Smokes PASS