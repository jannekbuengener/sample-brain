# Sample Brain — Windows Screen 1 Pilot (tester build)

## What this is
Portable Windows build of Sample Brain Screen 1 for external testers.
No Python, Git, Visual Studio, or repo checkout required.

## Install
1. Extract the ZIP to any writable folder (for example Desktop or Documents).
2. Open the extracted `SampleBrain` folder.
3. Double-click `SampleBrain.exe`.

Windows may show SmartScreen for an unsigned pilot build. Choose
**More info → Run anyway** if you trust this build from the Sample Brain owner.

## First run flow
1. Confirm Clean Start (calm empty workspace).
2. Add Source → choose a local sample folder you own.
3. Wait for Analyze/Index to finish.
4. Browse the library and audition samples (↑/↓, Esc stops).
5. Run Harmonic Match from a browser sample.
6. Add samples from Browser and Match into Live Kit until the kit is complete.
7. Export the Live Kit to a local folder you choose.
8. Open the exported files outside Sample Brain to confirm they play.
9. Quit the app, start `SampleBrain.exe` again, and confirm required state persists
   (sources/library) without restoring transient preview/match selection noise.

## Build identity
See `BUILDINFO.txt` next to this note for Source SHA, Build ID, and versions.

## Bug reports
Report issues to the Sample Brain owner with:
- Build ID from `BUILDINFO.txt`
- Short steps to reproduce
- What you expected vs what happened
Do not attach private sample libraries or personal catalog databases.
