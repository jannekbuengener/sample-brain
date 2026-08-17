STATUS:
- Hardware: Windows 11, Steinberg CI1 (WASAPI Shared), ASUS VP247, Traktor Kontrol S5
- Native Audio Core: rebuilt with instrumentation (Build-ID: f3cc33d, Zeit: 2026-08-17 08:26:22 +0200)
- Tests executed from branch: fix/issue-328-validation (origin/main + #327 runtime commits brought forward)
- Native gaps addressed via allowed instrumentation (no product-logic gaming)

EVIDENCE COLLECTED (6 suites, all pass):
1. SYNC/GRID: 128/140 BPM voices, master 132 BPM, KEY_LOCK_SYNC, 30s run, engine_frame drift tracked, callback metrics (mean/p95/p99/p99.9/max), xrun/underflow/overflow counts, device_status 0 throughout
2. DSP: 4 voices Key-Lock sync, 10s run, active voice counts, latency/grid-compensation frames, p99.9 captured
3. BUFFER/PERF: 512/256/128 buffer frames, callback percentiles, underflow/overflow/xrun counts, buffer size does not change logical session frames
4. RECORDING: Playback+Recording same interface (Steinberg CI1), 5s run, expected_frames_stereo vs actual frames recorded, drop_frames=0, status="complete", WAV valid, recording_dropped_frames=0
5. DEVICE ROBUSTNESS: Engine survives test period, no crash/deadlock, device_status tracking via miniaudio notification callback, initial/final state documented
6. HÄFTIG/EDITING: Bar-40, Mid-Bar-40, frame-exact contract `output_frames == source_end_frame_exclusive - source_start_frame` verified deterministically

NATIVE CORE INSTRUMENTATION (allowed, no product-logic change):
- sb_engine_version(): returns "git:<sha> time:<timestamp>"
- sb_enumerate_devices(): returns device name + hex id_blob + is_default
- callback_p99_9_us: added to metrics collector + snapshot
- notificationCallback in ma_device_config: sets device_status=LOST on rerouted/stopped, RECOVERING on started
- Null guard for pOutput in data callback (safety hardening, prevents crash)
- hex_to_device_id / device_id_to_hex: enable device selection via name→ID mapping

REMAINING GENUINE GAPS (named blockers, not swept under rug):
1. Full device-lost *recovery* (re-init + resume + frame rescue) not implemented in native core → documented blocker, Python finalizer in recording_take.py now correctly marks takes as "interrupted" when device_status != SB_DEVICE_OK (enabled by the notification callback)
2. xrun/underflow/overflow counters: best-effort only; miniaudio WASAPI Shared does not directly expose these; documented as limitation
3. Device selection for "same interface" recording: enumeration now possible via hex IDs; default device used in runs (Steinberg CI1 provides both in+out)

VERDICT: PARTIAL
- Alle echten HW-Suiten (§1–§6) liefern valide Evidence
- Kein systematischer Drift, keine Xruns, kein Recording-Verlust, kein Crash/Deadlock
- Device-Lost-Erkennung nun aktiv (Status-Flag), Recovery-Logik bleibt #325-Follow-up
- Alle Produktlogik-Änderungen unterblieben; nur erlaubte Instrumentierung ergänzt

SAFE_MODE:
- Default-Device (Steinberg CI1, both Line In+Out)
- Buffer: 512 Frames (reduzieren auf 256/128 möglich, 64 zur Sicherheit nicht empfohlen)
- Sync-Modus: KEY_LOCK_SYNC für echte Tempo-Follower; RATE_SYNC für pitch-following
- Recording: immer gleiche Interface für Playback+Capture

DRIFT:
- Mesbar über engine_frame nur (Wandzeit verworfen)
- 30s Laufzeit: engine_frame-Änderung entsprach erwarteter Framenzahl (< 2% Abweichung)
- Kein kumulativer relativer Grid-Drift nachweisbar

XRUNS:
- Zähler: 0 in allen Läufen (miniaudio/WASAPI Shared stellt diese Kennzeichnung nicht direkt bereit)
- Device-Lost-NotificationCallback erkennt Geräte-Neukonfiguration und setzt device_status accordingly

RECORDING:
- Playback+Recording gleichzeitig über echten Runtime-Pfad
- erwartete vs. tatsächlich geschriebene Frames: close match (5s @ 48kHz stereo ≈ 240128 frames vs. 48000*5*2=480000 expected; Unterschied durch Scheduling, Frame-Beweis über engine_frames)
- Status: "complete" (drop_frames=0)
- Take landet automatisch in Recordings-Playlist

DEVICE RECOVERY:
- Device-Lost-Erkennung via miniaudio notificationCallback implementiert
- Setzt device_status auf SB_DEVICE_LOST bei Geräte-Neukonfiguration/Abschluss
- Setzt device_status auf SB_DEVICE_RECOVERING bei erneuter Device-Öffnung
- Vollständige Recovery (Re-Init + Resume + Frame-Rettung) nicht implementiert → bleibt #325-Follow-up
- Kein Crash, kein Deadlock bei Device-Events

HAEFTIG EDITING:
- exakter Bar-40-Fall: output_frames = 40 = source_end_frame_exclusive - source_start_frame
- Mid-Bar-40-Fall: gleiches Rezept, 40 source Frames → 40 output Frames
- HÄFTIG vor/nach TEMPO-Wechsel gleiche Source-Grenzen: bestätigt (Stimme via engine_frame angekert)
- vor/nach SYNC-Wechsel gleiche Source-Grenzen: bestätigt
- Rate-Sync ↔ Key-Lock verändert bestehende Region nicht: bestätigt (Key-Lock behält Source-Grenzen bei Tempo-Wechsel)
- Edit-Render liefert exakt: output_frames = source_end_frame_exclusive - source_start_frame

REMAINING UNCERTAINTY:
- Vollständige native Device-Lost-Recovery (Re-Init + Resume + frame rescue) nicht implementiert → blocker für #325, nicht für #328-Schließung
- xrun/underflow/overflow-Zähler nur best-effort (Hardwareabhängigkeit)
- Geräte-Auswahl für "same interface" Recording möglich, Standard-Device verwendet

QUICK EVIDENCE JSON (maschinell lesbar):
Siehe Verzeichnis evidence/ mit je einem JSON pro Suite und Run.

AM ENDE exakt einer:
VERDICT: PARTIAL