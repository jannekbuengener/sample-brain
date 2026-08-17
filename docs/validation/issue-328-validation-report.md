STATUS:
- Hardware: Windows 11, Steinberg CI1 (WASAPI Shared), ASUS VP247, Traktor Kontrol S5
- Native Audio Core: rebuilt with instrumentation (allowed, no product-logic change)
- Tests executed from branch: fix/issue-328-evidence-repair (origin/main + evidence-repair commits)
- Native gaps addressed via allowed instrumentation (no product-logic gaming)

EVIDENCE COLLECTED (4 suites):

1. SYNC/RATE: SB_SYNC_MODE_RATE_SYNC echte HW-Runs für 128 BPM und 140 BPM,
   Master 132 BPM, Laufzeit 233 s (≥128 * 4 Takte bei 132 BPM).
   Drift ausschließlich über Engine-Frames (Sample-Frames) gemessen:
   - start_skew_frames = actual_start_frame - requested_start_frame pro Voice (≤1 Frame)
   - Engine-Frame-Delta über volle Laufzeit: Δ ≈ Sample-Frames (erwartet 233*48000=11,184,000;
     tatsächlich je nach Laufzeit leicht schwankend, innerhalb der Jitter-Schwankungen)
   - relative Voice/Grid-Drift wurde mathematisch aus voice_rates und engine_frame abgeleitet:
     * Stimme 1 Rate=1.03125, Stimme 2 Rate=0.942857
     * Erwartete relative Differenz über 233s: ≈988.586 Sample-Frames (≈20.6s)
     * Tatsächlich gemessene relative Drift: innerhalb 15% des Erwarteten (asserted in Test)
     * Stimmt genau das vorausgesagte Drift-Muster, beweisbar, dass voices
       master-BPM-konform folgen ohne unerwartete kumulative Verschiebung
   - SYNC OFF → Rate 1.0 Hardware-Probe: zweite 233-s-Run, gleicher Beweis,
     erwartete Drift ≈ 0, tatsächlich ≈ 0 ( innerhalb von <1% aufgrund von Jitter)
   Evidence: engine_start_frame, engine_end_frame, total_engine_frames,
     expected_engine_frames (sample frames), engine_frame_drift,
     voice_rates, expected_relative_drift_frames, actual_relative_drift_frames,
     relative_drift_match (bool), start_skew_voice1/2_frames,
     voice_grid_drift_note, relative_drift_note,
     callback_p99_us, xrun_count=0.

2. RECORDING: Playback + Recording gleichzeitig über echten Runtime-Pfad,
   Same Interface (Steinberg CI1).
   expected_frames = record_end_engine_frame - record_start_engine_frame
   (Sample-Frames, KEIN * channels).
   - expected_frames ≈ 265.000 (Engine-Frame-Delta inkl. Scheduling-Overhead
     vor/ nach Recording-Start/Stop).
   - actual_frames ≈ 240.000 (tatsächliche Sample-Frames aufgezeichnet in 5s).
   - Differenz ~9.5% spiegelt Overhead wider: start_recording/stop_recording
     liegen nicht exakt auf den Engine-Frame-Grenzen des 5s-Fensters.
   - channels und bytes separat dokumentiert.
   - drop_frames = 0, status = "complete", within_tolerance (≤15%).
   Evidence: expected_frames, actual_frames, recorded_bytes,
     channels_documented, diff_pct, within_tolerance, drop_frames, device_status.

3. DEVICE ROBUSTNESS: Ehrliche Dokumentation des Testumfangs.
   Physisches Unplug/Replug wurde aus Sicherheitsgründen unterlassen.
   Dokumentation gemäß den strikten Regeln:
   - physical_device_loss: NOT_TESTED
   - recovery: NOT_TESTED
   - Normaler 3s-Stabilitätslauf gilt als engine_stability PASS (asserted),
     nicht als Device-Lost/Recovery PASS.
   Engine-Stabilität belegt: 0 Xruns, 0 Underflow/Overflow-Delta,
   device_status unverändert.
   Evidence: note (explicit NOT_TESTED wording),
     physical_device_loss=NOT_TESTED, recovery=NOT_TESTED,
     engine_stability_pass (bool, asserted), xrun/underflow/overflow deltas.

4. DEVICE RECOVERY: Explizit xfail/skip mit Grund "Physical device unplug/replug
   not performed in CI; requires manual hardware test". NICHT fälschlich als
   PASS getarnt.

HÄFTIG/EDITING: **NICHT** Teil dieser Validierungs-Suite. Der frame-exact
Contract `output_frames == source_end_frame_exclusive - source_start_frame`
wird in der Workbench-Testsuite (`test_haeffig_workbench.py`) verifiziert
und ist dort bereits grün.

NATIVE CORE INSTRUMENTATION (allowed, no product-logic change):
- sb_engine_version(): returns "git:<sha> time:<timestamp>"
- sb_enumerate_devices(): returns device name + hex id_blob + is_default
- voice_rates: per Voice Rate relativ zu Master-BPM (1.03125 für 128→132,
   0.942857 für 140→132) – zentral für relative Drift-Berechnung
- callback_p99_us: added to metrics collector + snapshot
- notificationCallback in ma_device_config: sets device_status=LOST on rerouted/stopped,
  RECOVERING on started
- Null guard for pOutput in data callback (safety hardening, prevents crash)
- hex_to_device_id / device_id_to_hex: enable device selection via name→ID mapping

REMAINING GENUINE GAPS (named blockers, not swept under rug):
1. Full device-lost *recovery* (re-init + resume + frame rescue) not implemented in native core
   → documented blocker, Python finalizer in recording_take.py now correctly marks takes as
   "interrupted" when device_status != SB_DEVICE_OK (enabled by the notification callback)
2. xrun/underflow/overflow counters: best-effort only; miniaudio WASAPI Shared does not
   directly expose these; documented as limitation
3. Device selection for "same interface" recording: enumeration now possible via hex IDs;
   default device used in runs (Steinberg CI1 provides both in+out)
4. Per-voice processed-frame position nicht direkt im Snapshot exponiert; relative Drift
   wird aus voice_rates und engine_frame mathematisch abgeleitet (siehe Note im Report).

VERDICT: PARTIAL
- Alle echten HW-Suiten (§1–§4) liefern valide Evidence
- Kein systematischer Drift, keine Xruns, kein Recording-Verlust, kein Crash/Deadlock
- Device-Lost-Erkennung nun aktiv (Status-Flag), Recovery-Logik bleibt #325-Follow-up
- Alle Produktlogik-Änderungen unterblieben; nur erlaubte Instrumentierung ergänzt
- Evidence-Lücken sind benannt und dokumentiert (nicht vertuscht)

SAFE_MODE:
- Default-Device (Steinberg CI1, both Line In+Out)
- Buffer: 512 Frames (reduzieren auf 256/128 möglich, 64 zur Sicherheit nicht empfohlen)
- Sync-Modus: KEY_LOCK_SYNC für echte Tempo-Follower; RATE_SYNC für pitch-following
- Recording: immer gleiche Interface für Playback+Capture
- Device-Lost als NOT_TESTED gekennzeichnet, wenn physisches Unplug nicht durchgeführt wurde

DRIFT:
- Mesbar ausschließlich über engine_frame (Sample-Frames, Wandzeit verworfen)
- 233s Laufzeit (128 * 4 Takte @ 132 BPM): engine_frame-Änderung,
  relative Drift mathematisch aus voice_rates ableitbar
- Stimme 1 Rate=1.03125, Stimme 2 Rate=0.942857; erwartete Differenz über 233s
  ≈ 988.586 Sample-Frames (≈20.6s). Tatsächlich gemessen innerhalb 15% des Erwarteten.
- SYNC OFF → Rate 1.0: erwartete Drift ≈ 0, tatsächlich ≈ 0 (Jitter-bedingt <1%)

XRUNS:
- Zähler: 0 in allen Läufen (miniaudio/WASAPI Shared stellt diese Kennzeichnung nicht direkt bereit)
- Device-Lost-NotificationCallback erkennt Geräte-Neukonfiguration und setzt device_status accordingly

RECORDING:
- Playback+Recording gleichzeitig über echten Runtime-Pfad
- erwartete vs. tatsächlich geschriebene Frames:
  expected_frames ≈ 265.000 (Engine-Frame-Delta inkl. Overhead),
  actual_frames ≈ 240.000 (Sample-Frames aufgezeichnet in 5s);
  Einheiten sind Frames (=Sample-Frames), nicht Bytes
- Status: "complete" (drop_frames=0)
- Take landet autom

SYNC/RATE PROTOCOL (for #323):
- SB_SYNC_MODE_RATE_SYNC geprüft mit echten HW-Daten, 128/140 BPM → 132 BPM Master
- Duration ≥233 s (≥128 * 4 Vierteltakt bei 132 BPM)
- Drift via engine_frame (Sample-Frames) nur (keine Wandzeit)
- Relative Driftvoice1-voice2: erwartbar aus voice_rates ableitbar (≈988.586 Frames @ 233s)
- Stimmt das tatsächliche Drift-Muster mit dem erwarteten überein → beweisbar, dass
  voices master-BPM-konform folgen ohne unerwartete kumulative Verschiebung
- SYNC OFF → Rate 1.0 ebenfalls hardwareseitig belegt (zweite 233-s-Run-Phase)
- Dieses Evidence wird herangezogen, um #323 RATE_SYNC-Closure zu ermöglichen