# Issue #328 validation report

## Status

This validation is intentionally based on the actual render path, not on synthetic rate-derived drift.

The relevant proof is now stored directly in the engine snapshot as:
- `voice_rendered_click_count[SB_MAX_VOICES]`
- `voice_last_click_engine_frame[SB_MAX_VOICES]`

Both are updated only when a click is actually rendered into the output buffer. This avoids fake evidence that reconstructs a position from `voice_rates` and `engine_frame`.

## RATE_SYNC requirement

For the #323 scenario:
- Source voice 1: 128 BPM
- Source voice 2: 140 BPM
- Master: 132 BPM
- `RATE_SYNC` enabled

The real pass condition is:
- the two voices render approximately the same number of clicks during the same run
- the difference in their final rendered click frames is bounded to a small callback window
- the start skew for each scheduled voice remains within a 1-frame tolerance
- the running engine remains free of xrun faults during the safe run

That proof is taken directly from the render loop and is materially stronger than any mathematically reconstructed drift estimate.

## Rules for the evidence

- Do not derive "actual drift" from `voice_rates` alone.
- Do not claim equivalent click spacing if the clicks were not actually rendered.
- Do not conflate device-stability with explicit device-loss recovery testing.
- Device recovery remains `NOT_TESTED` unless a physical unplug/replug validation was performed.

## Verdict

VERDICT: PARTIAL

Reason:
- The render-path evidence is fixed and the test now checks the real output events.
- Full physical device-loss/recovery validation remains out of scope unless a hardware unplug/replug run is performed.
- The engine remains honest about that limitation rather than claiming a fake green result.

## Minimal acceptance criteria

RATE_SYNC passes when the following are true:
- `click_count_delta <= 1`
- `relative_last_click_offset_frames <= 512`
- `abs(start_skew_frames) <= 1` for each voice
- `xrun_count == 0`

SYNC OFF remains a separate check and is not treated as a RATE_SYNC proof.

## Notes

- The old drift explanation based on `abs(rate1-rate2) * duration * sample_rate` is intentionally removed.
- The actual render evidence is the authoritative source of truth for #323.
- Device recovery remains a distinct follow-up item and is not reported as a pass without hardware validation.
