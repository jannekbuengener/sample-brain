# Program chrome contract (#830)

**Status:** ACTIVE_SUPPORTING  
**Issue:** [#830](https://github.com/jannekbuengener/sample-brain/issues/830) under [#829](https://github.com/jannekbuengener/sample-brain/issues/829)  
**Renderer:** PySide6 / Qt Quick / QML. This file does not change runtime.

## Reference

Owner decision 2026-10-04 names one design authority for the global program frame:

| Field | Value |
|---|---|
| Asset | `docs/assets/portfolio/references/program_chrome/owner_program_chrome_ba928fbe.jpg` |
| SHA-256 | `5ae5703a74d02af175d2f47b8802f4a96b3783b8be69ad6be86ef4f832a20183` |
| Origin | SuperDesign draft `ba928fbe-e27d-4177-8d13-608e9eb2a7e0` (v8, Step Sequencer Grouped) |
| Preview | https://p.superdesign.dev/draft/ba928fbe-e27d-4177-8d13-608e9eb2a7e0 |

The file is the Owner screenshot, stored byte-identical. Do not recompress, crop, recolor, or redraw it. The draft id is provenance, not a second authority.

Do not read pixel, hex, or spacing numbers out of the scaled screenshot. Preserve the low, calm bar height, dark neutral ground, fine separators, restrained accent, and the horizontal hierarchy.

## What the image authorizes

Only the global frame:

1. **Top program bar**
   - Product identity on the left: existing text `Sample Brain`. Not the brain signet, not the `SAMPLE BRAIN` lockup, not the claim.
   - Product-mode navigation in the center for the three upper modes: **Edit**, **Arrangement**, **Live**
     (working labels; final visible copy may remain `TBD_OWNER_COPY` where not frozen by #1076).
     Historical reference chrome may still show Browser / Live Kit / Step Sequencer labels — those are
     **not** current top-level product modes (see mode/tool classification below).
   - Global transport / tempo on the right: existing transport, BPM / Tempo,
     time signature, SYNC, and other current global controls that already live
     in that zone (including the display-preferences overflow).
     **No Harmonic Match header button** — #843 removed `harmonicMatchButton`;
     Harmonic Matches open/retarget from the Sample Context Menu, and #845
     remains collapse/reopen owner.
2. **Bottom footer**
   - A short footer band.
   - Existing navigation / utility on the left.
   - Context info in a true center layer, geometrically centered on the full
     footer width (not RowLayout leftover between left and right).
   - Existing status on the right (may be empty/neutral; must not steal center).

Changes to this frame need an explicit Owner decision.

## What the image does not authorize

The rest of the screenshot is context only. Do not adopt or redesign:

- the Pattern / BARS / 8 · 16 · 32 row
- Bars 1–8 of 16
- Song time
- `+ Channel`
- step-sequencer rows, lanes, groups, mute/solo, or arrangement mini-maps
- any other screen-specific body

Pattern Core, sequencer playback, and historical Screen-2 seams stay on their own contracts. This file does not rename modules, issues, or Python types from Channel Rack to Step Sequencer.

## Product modes vs tools / capabilities (#1076)

Current product modes (upper positions):

| Mode | Type | Contents (semantic) | Not |
|---|---|---|---|
| **Edit** | MODE | Browser, Library, Harmonic Matches, classic Live Kit tool, optional Edit docking tools (#1069) | Step Sequencer as mandatory Edit content; Arrangement; Live |
| **Arrangement** | MODE | Step Sequencer / Pattern programming, Arrangement structure (blocks/groups/masks/end marker) | Demo Export Kit; Live; Edit docking targets |
| **Live** | FUTURE_MODE | Later performance perspective | Current chrome action; layout/MIDI/multi-track (owned later by #1088) |

Classification of common chrome / historical terms:

| Item | Class | Owner / note |
|---|---|---|
| Browser / Library / Harmonic Matches | TOOL / CAPABILITY inside **Edit** | Not top-level modes |
| Live Kit | TOOL inside **Edit** (#1077) | Not a top-level mode; not Arrangement; not Export |
| Step Sequencer / Channel Rack (product sense) | CAPABILITY inside **Arrangement** | Not a top-level mode; historical Screen-2 / `channel_rack` symbols remain technical evidence |
| Export Kit | ACTION (Demo) | Distinct from Arrangement Entry |
| Arrangement Entry | ACTION (full version) | Deliberate Edit→Arrangement transition (#1078); CTA copy open; ≠ Export Kit |
| Screen 1 / Screen 2 / Screen 3 | HISTORICAL_TERM | Delivery evidence only; not current product pages |

**Live Kit** reveal/collapse remains owned by existing progressive-disclosure / adapter seams (#845 and current commands). Program chrome must not invent a second Live Kit state owner. When a center control still names Live Kit historically, treat it as Edit-tool summon/reveal — not mode navigation.

**Arrangement** mode navigation is gated by docs-frozen `arrangement_mode_enabled` (default False; see `WORKBENCH_FEATURE_SETTINGS.md`) and later #1078/#1082 eligibility. **Live** remains unavailable / parked under [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088) until explicit re-entry.

## Footer reuse

[#837](https://github.com/jannekbuengener/sample-brain/issues/837) still owns which Library scopes exist and that they dispatch the existing scope intents. This contract supersedes only the geometric claim that those icons must sit strictly above a separate hint-only footer: the approved band places existing utility on the left, context info in a true full-width center layer, and existing status on the right.

- Reuse Collections and Favorites. Do not add a second copy in the Library pane.
- Sample Sources, All Samples, and Recordings stay available through the existing #837 scope set. Do not delete them to match the crop, and do not invent a new control for them.
- Do not add Song clock, pattern-step counters, or a `Local` badge unless a current projection already exposes that text.
- [#770](https://github.com/jannekbuengener/sample-brain/issues/770) still owns hint priority (Hover > Selection/focus > Default/empty) and the rule that the hint surface takes no focus. Selection includes keyboard-focused supported controls and, when none are focused, the existing browser sample selection projection. The focused footer-context centering slice re-authorizes geometric centering on the full footer midpoint inside this band; the hint must not overlap the utility or status hit areas.

## Narrow supersession

| Older rule | Still true | Superseded for this frame only |
|---|---|---|
| #782 header comment: identity left, producer center, secondary right | Tempo, SYNC, and display-preferences ownership | Zone order. Navigation is center. Transport/tempo is right. |
| #786 / brand README: no brain logo, lockup, or claim in the header | That prohibition | Nothing. Identity stays product text. |
| #843 (DONE_MERGED_CLOSED): Harmonic Matches from Sample Context Menu | Open/retarget via `open_harmonic_matches_for_row`; #845 collapse ownership | Header `harmonicMatchButton` is gone. Right program-chrome must not reintroduce it. |
| #770: hint is bottom-center | Hint semantics; Hover > Selection/focus > empty | #831 temporarily placed the hint on the right. The focused footer-context centering slice restores full-footer-width geometric centering inside this band (not a separate strip outside the footer). |
| #837: secondary icons above a hint-only footer | Scope set and intent dispatch | Those icons occupy the left side of this footer band (no second Library-pane copy). |
| `WORKBENCH_LIBRARY_NAVIGATION_CONTRACT.md` historical pane-bottom bar wording | Scope intents and Catalog invisibility | **Placement authority is this file (#830):** global footer left. The navigation contract no longer authorizes a competing pane-local geometry. |

Screen-1 colors stay on Theme Core. This reference is not a palette.

## Implementation test supersession (#831)

This file is docs/canon-only. #830 does **not** rewrite product/QML runtime
tests onto the not-yet-implemented #831 end state.

The following frozen tests still describe **pre-#831 / current `main` runtime**
geometry (including pane-local Library scope chrome). #831 must retarget them
together with the actual QML migration. Until then they remain green CURRENT
RUNTIME freezes — **not** authority against this #830 canon.

| Frozen test area | Pre-#831 meaning | What #831 must change |
|---|---|---|
| `tests/test_workbench_qml_producer_command_zone.py` | Current producer/header zone layout | Require center navigation and right transport zone (no Harmonic Match header button — already removed by #843). |
| `tests/test_workbench_qml_screen2_channel_rack.py` | Screen-2 surface forbids | Allow reserved **Arrangement** label in program-chrome navigation only; keep forbidding Screen 3 / Playlist / Mixer surfaces. |
| `tests/test_workbench_library_bottom_icons_837.py` | Pane-local bottom icon geometry above the app footer | Move scope utility into the global footer band (left). |
| `tests/test_workbench_library_scope_evidence.py` | Pane-local `libraryScopeBar` geometry (`bar.y() > 80`, below `libraryContentHost`, etc.) | Retarget those placement assertions with the QML footer migration. Do **not** treat the current pane-local freeze as a veto of #830 footer placement. |
| `tests/test_workbench_qml_library_tree.py` | `libraryScopeBar` must follow `libraryContentHost` inside `libraryPane` | Retarget when the bar moves into the global footer band. |
| `tests/test_workbench_context_hint_770.py` | Historical right-side footer placement freeze from #831 | Retarget to full-footer-width geometric centering inside the footer band (true center layer; not RowLayout leftover). |

#831 has landed. Remaining rows above that still describe historical pre-migration
freezes must be retargeted only with the scoped product change that owns the new
geometry (including the footer-context centering slice for hint placement).
