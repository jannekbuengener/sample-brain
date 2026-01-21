# RENAME_PREVIEW.ps1
# Generated: 2026-01-21T06:58:52
# Safe by default: does NOT rename unless you pass -Apply.

param([switch]$Apply)

$errors = 0

# Techno Samples (test)\60er Projekt 124 bpm Clap 1.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\60er Projekt 124 bpm Clap 1.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\60er Projekt 124 bpm Clap 1, --, [LOOP] - 124BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\60er Projekt 124 bpm Clap 2.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\60er Projekt 124 bpm Clap 2.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\60er Projekt 124 bpm Clap 2, --, [LOOP] - 124BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\60er Projekt 124 bpm Clap 3.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\60er Projekt 124 bpm Clap 3.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\60er Projekt 124 bpm Clap 3, --, [LOOP] - 124BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\60er Projekt 124 bpm Clap Holz - Part_2.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\60er Projekt 124 bpm Clap Holz - Part_2.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\60er Projekt 124 bpm Clap Holz, --, [LOOP] - 124BPM, Em, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\Clap loop 128bpm.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Clap loop 128bpm.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Clap loop 128bpm, --, [LOOP] - 128BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\clap voll.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\clap voll.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\clap voll, --, [LOOP] - 142BPM, Fm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\CLAP_2_LOOP_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_2_LOOP_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_2_LOOP_Jannek Büngener, --, [LOOP] - 117BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\CLAP_3_LOOPJannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_3_LOOPJannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_3_LOOPJannek Büngener, --, [LOOP] - 125BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\CLAP_9_LOOP(Pre-Shifted REALISTIC)_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_9_LOOP(Pre-Shifted REALISTIC)_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_9_LOOP(Pre-Shifted REALISTIC)_Jannek Büngener, --, [LOOP] - 116BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\claps loop2_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\claps loop2_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\claps loop2_Jannek Büngener, --, [LOOP] - 138BPM, Em, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\Musical_Taste_Organic_CLAP_4_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Musical_Taste_Organic_CLAP_4_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Musical_Taste_Organic_CLAP_4_Jannek Büngener, --, [LOOP] - 117BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\Musical_Taste_Snap_SEELE_LOOP.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Musical_Taste_Snap_SEELE_LOOP.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Musical_Taste_Snap_SEELE_LOOP, --, [LOOP] - 125BPM, Bm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\TOK_2_LOOP Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\TOK_2_LOOP Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\TOK_2_LOOP Jannek Büngener, --, [LOOP] - 117BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\Clap Raw Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Clap Raw Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Clap Raw Jannek Büngener, --, [ONE-SHOT] - 120BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\CLAP_1_ Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_1_ Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_1_ Jannek Büngener, --, [LOOP] - 120BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\CLAP_4_SHOT_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_4_SHOT_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_4_SHOT_Jannek Büngener, --, [ONE-SHOT] - 120BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\CLAP_5_SHOT_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_5_SHOT_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_5_SHOT_Jannek Büngener, --, [ONE-SHOT] - --BPM, Fm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\CLAP_6_SHOT_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_6_SHOT_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_6_SHOT_Jannek Büngener, --, [ONE-SHOT] - 120BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\CLAP_7_SHOT_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_7_SHOT_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_7_SHOT_Jannek Büngener, --, [LOOP] - 120BPM, Fm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\CLAP_10_SHOT_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_10_SHOT_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\CLAP_10_SHOT_Jannek Büngener, --, [ONE-SHOT] - --BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\Clap2_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Clap2_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Clap2_Jannek Büngener, --, [ONE-SHOT] - 120BPM, Dm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\Schalter an aus.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Schalter an aus.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Schalter an aus, --, [LOOP] - 101BPM, Cm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\Clap 1.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Clap 1.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Clap 1, --, [LOOP] - 120BPM, Fm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\Clap 2.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Clap 2.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Clap 2, --, [LOOP] - 120BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\16th 1 loop 144 bpm.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\16th 1 loop 144 bpm.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\16th 1 loop 144 bpm, --, [LOOP] - 144BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 1 offbeat 144bpm.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 1 offbeat 144bpm.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 1 offbeat 144bpm, --, [LOOP] - 144BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 2  closed 132bpm.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 2  closed 132bpm.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 2 closed 132bpm, --, [LOOP] - 132BPM, Cm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 2 (konsolidiert) (konsolidiert) - Part_2.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 2 (konsolidiert) (konsolidiert) - Part_2.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 2 (konsolidiert) (konsolidiert), --, [LOOP] - 136BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 3 132bpm.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 3 132bpm.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 3 132bpm, --, [LOOP] - 132BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 4 (asynchron) Loop.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 4 (asynchron) Loop.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 4 (asynchron) Loop, --, [LOOP] - 133BPM, D#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 6 132bpm.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 6 132bpm.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 6 132bpm, --, [LOOP] - 132BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 7 Loop.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 7 Loop.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 7 Loop, --, [LOOP] - 129BPM, G#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 8 short 124bpm.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 8 short 124bpm.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 8 short 124bpm, --, [LOOP] - 124BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH open Loop - Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH open Loop - Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH open Loop, --, [LOOP] - 133BPM, Em, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\hi hat open Loop.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\hi hat open Loop.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\hi hat open Loop, --, [LOOP] - 133BPM, G#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\Kessel Hat Loop 144bpm.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Kessel Hat Loop 144bpm.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Kessel Hat Loop 144bpm, --, [LOOP] - 144BPM, A#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\MT HH Loop 1 Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\MT HH Loop 1 Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\MT HH Loop 1 Jannek Büngener, --, [LOOP] - 126BPM, Cm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\sddf.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\sddf.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\sddf, --, [ONE-SHOT] - 120BPM, A#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\Selee Loop_HH.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Selee Loop_HH.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Selee Loop_HH, --, [LOOP] - 123BPM, Dm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 1.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 1.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 1, --, [ONE-SHOT] - 120BPM, Gm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 2.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 2.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 2, --, [LOOP] - 120BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 3.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 3.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 3, --, [ONE-SHOT] - 120BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 4.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 4.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 4, --, [LOOP] - 136BPM, C#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 5.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 5.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 5, --, [ONE-SHOT] - 120BPM, Gm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 6.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 6.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 6, --, [LOOP] - 136BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 7.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 7.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 7, --, [LOOP] - 120BPM, G#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 8.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 8.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 8, --, [ONE-SHOT] - 120BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 9.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 9.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 9, --, [ONE-SHOT] - 120BPM, A#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 10.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 10.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 10, --, [ONE-SHOT] - 120BPM, A#m, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 11.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 11.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 11, --, [ONE-SHOT] - 120BPM, Bm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 12.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 12.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 12, --, [LOOP] - 120BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\HH 13.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 13.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\HH 13, --, [LOOP] - 144BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\Selee Loop_HH+ - Part_1.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Selee Loop_HH+ - Part_1.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\Selee Loop_HH+, --, [LOOP] - 120BPM, Am, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Techno Samples (test)\umt_hat_808.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\umt_hat_808.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Techno Samples (test)\umt_hat_808, --, [ONE-SHOT] - 120BPM, Bm, dark-driving.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\African Singer shake it shake it.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\African Singer shake it shake it.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\African Singer shake it shake it, --, [LOOP] - 167BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Aku Aku.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Aku Aku.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Aku Aku, --, [LOOP] - 235BPM, A#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Atmos - Creapy 1.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Atmos - Creapy 1.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Atmos, --, [LOOP] - 178BPM, G#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Atmos - Hornissen Sturzflug.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Atmos - Hornissen Sturzflug.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Atmos, --, [LOOP] - 80BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Bass_shot_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass_shot_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass_shot_Jannek Büngener, --, [FX] - 304BPM, Am, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Heatshot.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Heatshot.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Heatshot, --, [LOOP] - 161BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\human race.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\human race.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\human race, --, [LOOP] - 152BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Kasse_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Kasse_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Kasse_Jannek Büngener, --, [LOOP] - 129BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Kehlkopfgesang.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Kehlkopfgesang.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Kehlkopfgesang, --, [LOOP] - 120BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\MT_beep_Sound_Jannek Büngener.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\MT_beep_Sound_Jannek Büngener.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\MT_beep_Sound_Jannek Büngener, --, [LOOP] - --BPM, Bm, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\natives.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\natives.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\natives, --, [LOOP] - 161BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\nEUER sOUND - Part_1.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\nEUER sOUND - Part_1.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\nEUER sOUND, --, [FX] - 120BPM, G#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Neuer Soundflp.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Neuer Soundflp.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Neuer Soundflp, --, [LOOP] - 172BPM, Em, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Pauke Atmosferisch Loop.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Pauke Atmosferisch Loop.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Pauke Atmosferisch Loop, --, [LOOP] - 133BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Phoenix - Piano Chords Loop.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Phoenix - Piano Chords Loop.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Phoenix, --, [LOOP] - 133BPM, D#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\RYTHM_1_LOOP_Jannek Büngener.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\RYTHM_1_LOOP_Jannek Büngener.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\RYTHM_1_LOOP_Jannek Büngener, --, [LOOP] - 117BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Selee Loop_IMPACT.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Selee Loop_IMPACT.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Selee Loop_IMPACT, --, [LOOP] - 123BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Selee Loop_inpact - Part_1.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Selee Loop_inpact - Part_1.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Selee Loop_inpact, --, [LOOP] - 126BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Selee Loop_inpact - Part_2.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Selee Loop_inpact - Part_2.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Selee Loop_inpact, --, [LOOP] - 167BPM, D#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Trumpets.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Trumpets.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Trumpets, --, [LOOP] - 126BPM, Em, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\white noise Distorded.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\white noise Distorded.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\white noise Distorded, --, [LOOP] - 103BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Bass SFX_F(23).wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass SFX_F(23).wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass SFX_F(23), --, [LOOP] - 148BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Bass SFX_F(28).wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass SFX_F(28).wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass SFX_F(28), --, [LOOP] - 152BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Bass SFX_F(30).wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass SFX_F(30).wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass SFX_F(30), --, [LOOP] - 133BPM, D#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Bass SFX_F(37).wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass SFX_F(37).wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass SFX_F(37), --, [LOOP] - 123BPM, F#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Bass SFX_F(19).wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass SFX_F(19).wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass SFX_F(19), --, [LOOP] - 115BPM, F#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Bass SFX_F(21).wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass SFX_F(21).wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bass SFX_F(21), --, [LOOP] - 88BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Digital TV Glitch 1.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Digital TV Glitch 1.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Digital TV Glitch 1, --, [FX] - 103BPM, Cm, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Digital TV Glitch 2.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Digital TV Glitch 2.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Digital TV Glitch 2, --, [FX] - 123BPM, F#m, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Digital TV Glitch 3.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Digital TV Glitch 3.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Digital TV Glitch 3, --, [FX] - 215BPM, D#m, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Digital TV Glitch 4.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Digital TV Glitch 4.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Digital TV Glitch 4, --, [FX] - 157BPM, Em, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Elementing Glitch 1.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Elementing Glitch 1.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Elementing Glitch 1, --, [FX] - 112BPM, A#m, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Elementing Glitch 2.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Elementing Glitch 2.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Elementing Glitch 2, --, [FX] - 144BPM, Cm, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Fast Glitch 1.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Fast Glitch 1.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Fast Glitch 1, --, [FX] - 235BPM, C#m, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Fast Glitch 2.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Fast Glitch 2.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Fast Glitch 2, --, [FX] - 304BPM, C#m, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Fast Glitch 3.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Fast Glitch 3.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Fast Glitch 3, --, [FX] - 207BPM, Am, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Fast Glitch 4.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Fast Glitch 4.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Fast Glitch 4, --, [FX] - 178BPM, F#m, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\No Signal Glitch 1.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\No Signal Glitch 1.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\No Signal Glitch 1, --, [FX] - 115BPM, Cm, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\No Signal Glitch 2.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\No Signal Glitch 2.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\No Signal Glitch 2, --, [FX] - 235BPM, C#m, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\No Signal Glitch 3.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\No Signal Glitch 3.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\No Signal Glitch 3, --, [FX] - 152BPM, Cm, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\No Signal Glitch 4.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\No Signal Glitch 4.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\No Signal Glitch 4, --, [FX] - 94BPM, Cm, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\No Signal Glitch 5.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\No Signal Glitch 5.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\No Signal Glitch 5, --, [FX] - 129BPM, Fm, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Noise Glitch 1.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Noise Glitch 1.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Noise Glitch 1, --, [FX] - 140BPM, Cm, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Noise Glitch 2.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Noise Glitch 2.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Noise Glitch 2, --, [LOOP] - 144BPM, C#m, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Noise Glitch 3.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Noise Glitch 3.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Noise Glitch 3, --, [FX] - 157BPM, Cm, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Noise Glitch 4.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Noise Glitch 4.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Noise Glitch 4, --, [FX] - 112BPM, D#m, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Noise Glitch 5.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Noise Glitch 5.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Noise Glitch 5, --, [LOOP] - 287BPM, Dm, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - ATMOS - 01.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - ATMOS - 01.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - --BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - ATMOS - 02.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - ATMOS - 02.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - --BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - ATMOS - 03.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - ATMOS - 03.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - --BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - ATMOS - 04.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - ATMOS - 04.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 88BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - ATMOS - 05.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - ATMOS - 05.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 52BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - ATMOS - 06.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - ATMOS - 06.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 75BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - ATMOS - 07.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - ATMOS - 07.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 88BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - ATMOS - 08.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - ATMOS - 08.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 129BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - ATMOS - 09.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - ATMOS - 09.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 120BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - ATMOS - 10.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - ATMOS - 10.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 98BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - ATMOS - 11.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - ATMOS - 11.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 91BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - BRAMS - 02.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - BRAMS - 02.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 215BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - BRAMS - 03.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - BRAMS - 03.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 74BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - BRAMS - 04.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - BRAMS - 04.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 105BPM, Gm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - BRAMS - 05.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - BRAMS - 05.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 148BPM, F#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - BRAMS - 06.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - BRAMS - 06.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 126BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - BRAMS - 07.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - BRAMS - 07.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 178BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Generdyn - BRAMS - 01.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn - BRAMS - 01.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Generdyn, --, [LOOP] - 258BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\01 Carlo Galliani - Fx - Positron [Sound Effects Vol.4].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\01 Carlo Galliani - Fx - Positron [Sound Effects Vol.4].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\01 Carlo Galliani, --, [LOOP] - 96BPM, D#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\01 Carlo Galliani - Fx- Beam [Sound Effects Vol.7].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\01 Carlo Galliani - Fx- Beam [Sound Effects Vol.7].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\01 Carlo Galliani, --, [LOOP] - 152BPM, Am, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\01 Carlo Galliani - Fx- Crazy Birds [Sound Effects Vol.5].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\01 Carlo Galliani - Fx- Crazy Birds [Sound Effects Vol.5].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\01 Carlo Galliani, --, [LOOP] - 235BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\02 Carlo Galliani - Fx - Space Station [Sound Effects Vol.4].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\02 Carlo Galliani - Fx - Space Station [Sound Effects Vol.4].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\02 Carlo Galliani, --, [LOOP] - 133BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\02 Carlo Galliani - Fx- Bedlam [Sound Effects Vol.7].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\02 Carlo Galliani - Fx- Bedlam [Sound Effects Vol.7].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\02 Carlo Galliani, --, [LOOP] - 120BPM, D#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\02 Carlo Galliani - Fx- Electro Rizer [Sound Effects Vol.5].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\02 Carlo Galliani - Fx- Electro Rizer [Sound Effects Vol.5].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\02 Carlo Galliani, --, [LOOP] - 157BPM, Gm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\03 Carlo Galliani - Fx - UFO [Sound Effects Vol.4].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\03 Carlo Galliani - Fx - UFO [Sound Effects Vol.4].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\03 Carlo Galliani, --, [LOOP] - 157BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\03 Carlo Galliani - Fx- Broken Bells [Sound Effects Vol.7].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\03 Carlo Galliani - Fx- Broken Bells [Sound Effects Vol.7].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\03 Carlo Galliani, --, [LOOP] - 120BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\03 Carlo Galliani - Fx- Flange Combo [Sound Effects Vol.5].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\03 Carlo Galliani - Fx- Flange Combo [Sound Effects Vol.5].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\03 Carlo Galliani, --, [LOOP] - 115BPM, Em, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\04 Carlo Galliani - Fx - Whoosh [Sound Effects Vol.4].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\04 Carlo Galliani - Fx - Whoosh [Sound Effects Vol.4].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\04 Carlo Galliani, --, [LOOP] - 129BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\04 Carlo Galliani - Fx- Broken Transmission [Sound Effects Vol.7].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\04 Carlo Galliani - Fx- Broken Transmission [Sound Effects Vol.7].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\04 Carlo Galliani, --, [LOOP] - 140BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\04 Carlo Galliani - Fx- Flyby [Sound Effects Vol.5].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\04 Carlo Galliani - Fx- Flyby [Sound Effects Vol.5].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\04 Carlo Galliani, --, [LOOP] - 120BPM, Am, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\05 Carlo Galliani - Fx - Wormhole [Sound Effects Vol.4].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\05 Carlo Galliani - Fx - Wormhole [Sound Effects Vol.4].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\05 Carlo Galliani, --, [LOOP] - 144BPM, Am, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\05 Carlo Galliani - Fx- Crashing [Sound Effects Vol.7].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\05 Carlo Galliani - Fx- Crashing [Sound Effects Vol.7].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\05 Carlo Galliani, --, [LOOP] - --BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\05 Carlo Galliani - Fx- Growl [Sound Effects Vol.5].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\05 Carlo Galliani - Fx- Growl [Sound Effects Vol.5].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\05 Carlo Galliani, --, [LOOP] - --BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\06 Carlo Galliani - Fx - Apha [Sound Effects Vol.4].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\06 Carlo Galliani - Fx - Apha [Sound Effects Vol.4].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\06 Carlo Galliani, --, [LOOP] - 178BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\06 Carlo Galliani - Fx- Crazy Tom [Sound Effects Vol.7].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\06 Carlo Galliani - Fx- Crazy Tom [Sound Effects Vol.7].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\06 Carlo Galliani, --, [LOOP] - 120BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\06 Carlo Galliani - Fx- Leader [Sound Effects Vol.5].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\06 Carlo Galliani - Fx- Leader [Sound Effects Vol.5].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\06 Carlo Galliani, --, [LOOP] - 120BPM, E, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\07 Carlo Galliani - Fx - Bounce [Sound Effects Vol.4].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\07 Carlo Galliani - Fx - Bounce [Sound Effects Vol.4].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\07 Carlo Galliani, --, [LOOP] - 144BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\07 Carlo Galliani - Fx- Dance Sample [Sound Effects Vol.7].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\07 Carlo Galliani - Fx- Dance Sample [Sound Effects Vol.7].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\07 Carlo Galliani, --, [LOOP] - 199BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\07 Carlo Galliani - Fx- Machine [Sound Effects Vol.5].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\07 Carlo Galliani - Fx- Machine [Sound Effects Vol.5].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\07 Carlo Galliani, --, [LOOP] - 117BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\08 Carlo Galliani - Fx- Air [Sound Effects Vol.4].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\08 Carlo Galliani - Fx- Air [Sound Effects Vol.4].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\08 Carlo Galliani, --, [LOOP] - 152BPM, Em, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\08 Carlo Galliani - Fx- Data Transmission [Sound Effects Vol.7].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\08 Carlo Galliani - Fx- Data Transmission [Sound Effects Vol.7].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\08 Carlo Galliani, --, [LOOP] - 115BPM, Am, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\08 Carlo Galliani - Fx- Muted Combo [Sound Effects Vol.5].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\08 Carlo Galliani - Fx- Muted Combo [Sound Effects Vol.5].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\08 Carlo Galliani, --, [LOOP] - --BPM, Em, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\09 Carlo Galliani - Fx- Combo [Sound Effects Vol.4].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\09 Carlo Galliani - Fx- Combo [Sound Effects Vol.4].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\09 Carlo Galliani, --, [LOOP] - 191BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\09 Carlo Galliani - Fx- Detuner [Sound Effects Vol.7].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\09 Carlo Galliani - Fx- Detuner [Sound Effects Vol.7].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\09 Carlo Galliani, --, [LOOP] - --BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\09 Carlo Galliani - Fx- Razor [Sound Effects Vol.5].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\09 Carlo Galliani - Fx- Razor [Sound Effects Vol.5].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\09 Carlo Galliani, --, [LOOP] - 140BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\10 Carlo Galliani - Fx- Combo 2 [Sound Effects Vol.4].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\10 Carlo Galliani - Fx- Combo 2 [Sound Effects Vol.4].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\10 Carlo Galliani, --, [LOOP] - 133BPM, Gm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\10 Carlo Galliani - Fx- Electronic War [Sound Effects Vol.7].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\10 Carlo Galliani - Fx- Electronic War [Sound Effects Vol.7].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\10 Carlo Galliani, --, [LOOP] - 167BPM, Em, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\10 Carlo Galliani - Fx- Shutdown [Sound Effects Vol.5].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\10 Carlo Galliani - Fx- Shutdown [Sound Effects Vol.5].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\10 Carlo Galliani, --, [LOOP] - 115BPM, Am, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\11 Carlo Galliani - Fx- Combo 3 [Sound Effects Vol.4].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\11 Carlo Galliani - Fx- Combo 3 [Sound Effects Vol.4].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\11 Carlo Galliani, --, [LOOP] - 126BPM, D#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\11 Carlo Galliani - Fx- Engine Start [Sound Effects Vol.7].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\11 Carlo Galliani - Fx- Engine Start [Sound Effects Vol.7].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\11 Carlo Galliani, --, [LOOP] - 178BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\12 Carlo Galliani - Fx- Error [Sound Effects Vol.7].wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\12 Carlo Galliani - Fx- Error [Sound Effects Vol.7].wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\12 Carlo Galliani, --, [LOOP] - 148BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Airplane-Over-Crowd-01.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Airplane-Over-Crowd-01.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Airplane-Over-Crowd-01, --, [LOOP] - 157BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Apollo-11-Eagle-Has-Landed.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Apollo-11-Eagle-Has-Landed.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Apollo-11-Eagle-Has-Landed, --, [LOOP] - 85BPM, A#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Apollo-11-Eagle-Has-Landed-Extended.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Apollo-11-Eagle-Has-Landed-Extended.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Apollo-11-Eagle-Has-Landed-Extended, --, [LOOP] - 115BPM, Em, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Apollo-11-Thats-One-Small-Step-for-a-Man.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Apollo-11-Thats-One-Small-Step-for-a-Man.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Apollo-11-Thats-One-Small-Step-for-a-Man, --, [LOOP] - 55BPM, A#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Apollo-11-We-Have-a-Lift-Off.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Apollo-11-We-Have-a-Lift-Off.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Apollo-11-We-Have-a-Lift-Off, --, [LOOP] - 99BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Apollo-12-All-Weather-Testing.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Apollo-12-All-Weather-Testing.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Apollo-12-All-Weather-Testing, --, [LOOP] - 62BPM, A#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Apollo-13-Houston-Weve-Had-a-Problem.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Apollo-13-Houston-Weve-Had-a-Problem.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Apollo-13-Houston-Weve-Had-a-Problem, --, [LOOP] - 136BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Bell-Pitch-Up.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bell-Pitch-Up.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bell-Pitch-Up, --, [LOOP] - 123BPM, Em, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Bell-Pitch-Up-And-Down.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bell-Pitch-Up-And-Down.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Bell-Pitch-Up-And-Down, --, [LOOP] - 126BPM, Em, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Birds-Chirping-Owl-Hooting.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Birds-Chirping-Owl-Hooting.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Birds-Chirping-Owl-Hooting, --, [LOOP] - 108BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Cassini-Enceladus-Sound.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Cassini-Enceladus-Sound.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Cassini-Enceladus-Sound, --, [LOOP] - 129BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Cassini-Saturn-Radio-Emissions-1.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Cassini-Saturn-Radio-Emissions-1.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Cassini-Saturn-Radio-Emissions-1, --, [LOOP] - 11BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Cassini-Saturn-Radio-Emissions-2.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Cassini-Saturn-Radio-Emissions-2.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Cassini-Saturn-Radio-Emissions-2, --, [LOOP] - 115BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Cassini-Shields-Up.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Cassini-Shields-Up.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Cassini-Shields-Up, --, [LOOP] - 126BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Chorus-Radio-Waves-within-Earths-Atmosphere.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Chorus-Radio-Waves-within-Earths-Atmosphere.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Chorus-Radio-Waves-within-Earths-Atmosphere, --, [LOOP] - 120BPM, F#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Computers-are-in-Control.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Computers-are-in-Control.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Computers-are-in-Control, --, [LOOP] - 112BPM, G#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Corner-Cafe-Traffic.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Corner-Cafe-Traffic.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Corner-Cafe-Traffic, --, [LOOP] - 115BPM, F#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Delta-IV-Launch.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Delta-IV-Launch.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Delta-IV-Launch, --, [LOOP] - 117BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\DEMO.mp3
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\DEMO.mp3'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\DEMO, --, [LOOP] - 120BPM, Dm, cinematic-tense.mp3'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Downpour.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Downpour.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Downpour, --, [LOOP] - 117BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Early-Satellite-Communications-Project-Relay.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Early-Satellite-Communications-Project-Relay.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Early-Satellite-Communications-Project-Relay, --, [LOOP] - 133BPM, A#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Go-at-Throttle-Up.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Go-at-Throttle-Up.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Go-at-Throttle-Up, --, [LOOP] - 66BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Harp-Flutter-02.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Harp-Flutter-02.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Harp-Flutter-02, --, [LOOP] - 191BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\High-Metal-Bell-01.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\High-Metal-Bell-01.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\High-Metal-Bell-01, --, [LOOP] - 123BPM, Am, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Jet-Flyover-Distant-Birds.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Jet-Flyover-Distant-Birds.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Jet-Flyover-Distant-Birds, --, [LOOP] - 117BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\JFK-Return-Him-Safely-to-Earth.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\JFK-Return-Him-Safely-to-Earth.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\JFK-Return-Him-Safely-to-Earth, --, [LOOP] - 115BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\JFK-We-Choose-the-Moon.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\JFK-We-Choose-the-Moon.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\JFK-We-Choose-the-Moon, --, [LOOP] - 123BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\JFK-We-Choose-the-Moon-with-Apollo-11-Launch.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\JFK-We-Choose-the-Moon-with-Apollo-11-Launch.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\JFK-We-Choose-the-Moon-with-Apollo-11-Launch, --, [LOOP] - 136BPM, A#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Juno-Crossing-Jupiters-Bow-Shock.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Juno-Crossing-Jupiters-Bow-Shock.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Juno-Crossing-Jupiters-Bow-Shock, --, [LOOP] - 120BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Juno-Morse-code-HI-received-from-Earth.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Juno-Morse-code-HI-received-from-Earth.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Juno-Morse-code-HI-received-from-Earth, --, [LOOP] - 120BPM, Gm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Jupiters-Largest-Moon-Ganymede.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Jupiters-Largest-Moon-Ganymede.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Jupiters-Largest-Moon-Ganymede, --, [LOOP] - 117BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Jupiter-Sounds-2001.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Jupiter-Sounds-2001.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Jupiter-Sounds-2001, --, [LOOP] - 92BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Kepler-Star-KIC7671081B-Light-Curve-Waves-to-Sound.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Kepler-Star-KIC7671081B-Light-Curve-Waves-to-Sound.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Kepler-Star-KIC7671081B-Light-Curve-Waves-to-Sound, --, [LOOP] - 161BPM, F, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Kepler-Star-KIC12268220C-Light-Curve-Waves-to-Sound.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Kepler-Star-KIC12268220C-Light-Curve-Waves-to-Sound.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Kepler-Star-KIC12268220C-Light-Curve-Waves-to-Sound, --, [LOOP] - 43BPM, A#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Large-Room-Vents.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Large-Room-Vents.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Large-Room-Vents, --, [LOOP] - 123BPM, A#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Lookin-At-It.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Lookin-At-It.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Lookin-At-It, --, [LOOP] - 140BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Mall-Crowd-Distant-Birds.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Mall-Crowd-Distant-Birds.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Mall-Crowd-Distant-Birds, --, [LOOP] - 178BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\MECO.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\MECO.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\MECO, --, [LOOP] - 86BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Mercury-6-God-Speed.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Mercury-6-God-Speed.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Mercury-6-God-Speed, --, [LOOP] - 161BPM, G#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Mercury-7-Fireflies.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Mercury-7-Fireflies.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Mercury-7-Fireflies, --, [LOOP] - 61BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Muted-Traffic-Rumble.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Muted-Traffic-Rumble.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Muted-Traffic-Rumble, --, [LOOP] - 117BPM, Am, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Nice-to-be-in-Orbit.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Nice-to-be-in-Orbit.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Nice-to-be-in-Orbit, --, [LOOP] - 94BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\On-its-way-to-Orbit.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\On-its-way-to-Orbit.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\On-its-way-to-Orbit, --, [LOOP] - 120BPM, G#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Plasmaspheric-Hiss.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Plasmaspheric-Hiss.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Plasmaspheric-Hiss, --, [LOOP] - 133BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Press-to-ATO.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Press-to-ATO.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Press-to-ATO, --, [LOOP] - 152BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Quindar-Sound-2.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Quindar-Sound-2.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Quindar-Sound-2, --, [LOOP] - 96BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Radar-Echoes-From-Titans-Surface.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Radar-Echoes-From-Titans-Surface.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Radar-Echoes-From-Titans-Surface, --, [LOOP] - 136BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Rain-Under-Umbrella.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Rain-Under-Umbrella.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Rain-Under-Umbrella, --, [LOOP] - 140BPM, Gm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Rainy-Porch.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Rainy-Porch.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Rainy-Porch, --, [LOOP] - 103BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Rainy-Streetcorner.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Rainy-Streetcorner.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Rainy-Streetcorner, --, [LOOP] - 140BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Rubber-Shoes-on-Rug.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Rubber-Shoes-on-Rug.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Rubber-Shoes-on-Rug, --, [LOOP] - 120BPM, A#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Sad-Strings.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Sad-Strings.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Sad-Strings, --, [LOOP] - 199BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Speeding-Through-Titans-Haze.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Speeding-Through-Titans-Haze.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Speeding-Through-Titans-Haze, --, [LOOP] - 58BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Sputnik-Beep.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Sputnik-Beep.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Sputnik-Beep, --, [LOOP] - 112BPM, Bm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\STS-7-That-Was-Definitely-an-E-ticket.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\STS-7-That-Was-Definitely-an-E-ticket.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\STS-7-That-Was-Definitely-an-E-ticket, --, [LOOP] - 99BPM, E, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\STS-26-Liftoff.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\STS-26-Liftoff.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\STS-26-Liftoff, --, [LOOP] - 129BPM, Cm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\STS-41D-Liftoff.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\STS-41D-Liftoff.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\STS-41D-Liftoff, --, [LOOP] - 89BPM, D#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\STS-131-Sound-of-Launch.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\STS-131-Sound-of-Launch.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\STS-131-Sound-of-Launch, --, [LOOP] - 136BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\STS-135-Countdown-to-Launch.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\STS-135-Countdown-to-Launch.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\STS-135-Countdown-to-Launch, --, [LOOP] - 115BPM, A#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\STS-135-Launch-Commentary.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\STS-135-Launch-Commentary.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\STS-135-Launch-Commentary, --, [LOOP] - 112BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Ultra-Cold-Liquid-Helium-3.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Ultra-Cold-Liquid-Helium-3.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Ultra-Cold-Liquid-Helium-3, --, [LOOP] - 91BPM, A#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Voyager-1-Three-Tsunami-Waves-in-Interstellar-Space.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Voyager-1-Three-Tsunami-Waves-in-Interstellar-Space.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Voyager-1-Three-Tsunami-Waves-in-Interstellar-Space, --, [LOOP] - 51BPM, C#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Voyager-Interstellar-Plasma-Sounds.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Voyager-Interstellar-Plasma-Sounds.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Voyager-Interstellar-Plasma-Sounds, --, [LOOP] - 51BPM, Dm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Voyager-Lightning-on-Jupiter.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Voyager-Lightning-on-Jupiter.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Voyager-Lightning-on-Jupiter, --, [LOOP] - 11BPM, G#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Wheel-Stop.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Wheel-Stop.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Wheel-Stop, --, [LOOP] - 89BPM, A#m, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

# Cinematic Samples (test)\Whistler-Waves.wav
$src = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Whistler-Waves.wav'
$dst = 'D:\PRODUCING\Schnuffis Soundvitriene\Samples\Cinematic Samples (test)\Whistler-Waves, --, [LOOP] - 120BPM, Fm, cinematic-tense.wav'
if (-not (Test-Path -LiteralPath $src)) { Write-Host "MISSING: $src"; $errors++; continue }
if ($Apply) {
  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }
  catch { Write-Host "FAIL: $src"; $errors++ }
} else {
  Write-Host "PREVIEW: Rename '$src' -> '$dst'"
}

if ($errors -gt 0) { Write-Host "Done with $errors error(s)."; exit 2 }
Write-Host "Done."; exit 0
