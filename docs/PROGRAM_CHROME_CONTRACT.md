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
   - Screen navigation in the center, in this order: Browser, Live Kit, Step Sequencer, Arrangement.
   - Global transport / tempo on the right: existing transport, BPM / Tempo,
     time signature, SYNC, and other current global controls that already live
     in that zone (including the display-preferences overflow).
     **No Harmonic Match header button** — #843 removed `harmonicMatchButton`;
     Harmonic Matches open/retarget from the Sample Context Menu, and #845
     remains collapse/reopen owner.
2. **Bottom footer**
   - A short footer band.
   - Existing navigation / utility on the left.
   - Existing status on the right.

Changes to this frame need an explicit Owner decision.

## What the image does not authorize

The rest of the screenshot is context only. Do not adopt or redesign:

- the Pattern / BARS / 8 · 16 · 32 row
- Bars 1–8 of 16
- Song time
- `+ Channel`
- step-sequencer rows, lanes, groups, mute/solo, or arrangement mini-maps
- any other screen-specific body

Pattern Core, sequencer playback, and Screen 2 stay on their own contracts. This file does not rename modules, issues, or Python types from Channel Rack to Step Sequencer. The center label **Step Sequencer** is chrome copy for the existing Screen-2 route.

**Arrangement** is a reserved center label. Screen 3 is not built (`PRODUCT_WORKFLOW_CANON.md`). Do not add an Arrangement workspace, route, or command to imitate the label.

**Live Kit** stays the existing Screen-1 panel. The center **Live Kit** item is
chrome navigation only — it does not add a new screen, a new Live Kit state, or a
second disclosure/materialization authority.

| Session state | Center **Live Kit** chrome |
|---|---|
| Active source, `live_kit_materialized == false` | Visible label may name Live Kit; the action is **disabled / inert**. It must **not** materialize the Live Kit merely by activating this program-chrome control. Progressive disclosure stays owned by the existing Add-to-Kit / materialization path. |
| After materialization (`live_kit_materialized == true`) | Uses **only** the existing Live Kit presentation / reveal / collapse seams (#845 and current adapter commands). No second loader, no new panel owner. |

#831 must implement that table; it must not invent a parallel Live Kit domain or
materialization path from program chrome.

**Browser** selects Screen 1 workspace focus through existing navigation. **Step
Sequencer** routes through the existing Screen-2 open command (`openChannelRack` /
return path). **Arrangement** is visible but inert: reserved label only, no Screen 3
route, disabled or non-navigating until a future scoped issue authorizes it.

## Footer reuse

[#837](https://github.com/jannekbuengener/sample-brain/issues/837) still owns which Library scopes exist and that they dispatch the existing scope intents. This contract supersedes only the geometric claim that those icons must sit strictly above a separate hint-only footer: the approved band places existing utility on the left and existing status on the right.

- Reuse Collections and Favorites. Do not add a second copy in the Library pane.
- Sample Sources, All Samples, and Recordings stay available through the existing #837 scope set. Do not delete them to match the crop, and do not invent a new control for them.
- Do not add Song clock, pattern-step counters, or a `Local` badge unless a current projection already exposes that text.
- [#770](https://github.com/jannekbuengener/sample-brain/issues/770) still owns hint priority and the rule that the hint surface takes no focus. Horizontal centering is superseded: the hint shares this footer band and must not overlap the utility or status hit areas.

## Narrow supersession

| Older rule | Still true | Superseded for this frame only |
|---|---|---|
| #782 header comment: identity left, producer center, secondary right | Tempo, SYNC, and display-preferences ownership | Zone order. Navigation is center. Transport/tempo is right. |
| #786 / brand README: no brain logo, lockup, or claim in the header | That prohibition | Nothing. Identity stays product text. |
| #843 (DONE_MERGED_CLOSED): Harmonic Matches from Sample Context Menu | Open/retarget via `open_harmonic_matches_for_row`; #845 collapse ownership | Header `harmonicMatchButton` is gone. Right program-chrome must not reintroduce it. |
| #770: hint is bottom-center | Hint semantics | Horizontal placement inside the footer band. |
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
| `tests/test_workbench_context_hint_770.py` | Current hint placement freeze | Hint placement inside the footer band (right), not a separate centered strip. |

Until #831 lands, those tests continue to describe current `main` runtime
geometry. They do not block acceptance of this canon document, and #830 must
not weaken them prematurely.
