# Screen-1 Clean Start — source-driven progressive disclosure (#693 / #725 / #762)

Parent: [#691](https://github.com/jannekbuengener/sample-brain/issues/691).
Shared visual states: [#700](https://github.com/jannekbuengener/sample-brain/issues/700) / [`WORKBENCH_VISUAL_ACCEPTANCE.md`](WORKBENCH_VISUAL_ACCEPTANCE.md).
Add Source: [#589](https://github.com/jannekbuengener/sample-brain/issues/589).
Library loaders after explicit node selection: [#576](https://github.com/jannekbuengener/sample-brain/issues/576).
Collapsed First View / reveal affordance: [#725](https://github.com/jannekbuengener/sample-brain/issues/725).
Panel geometry after Active Source: [#694](https://github.com/jannekbuengener/sample-brain/issues/694) / [`WORKBENCH_ELASTIC_LAYOUT.md`](WORKBENCH_ELASTIC_LAYOUT.md).
Returning workspace with persisted Sources: [#762](https://github.com/jannekbuengener/sample-brain/issues/762).

## Product default

Screen-1 launch is **source-driven**, not unconditionally Clean Start.

```text
No persisted Sources     → Clean Start (Calm Canvas + Add Source)
≥1 valid persisted Source → Returning Workspace (Library + Browser)
```

[#762](https://github.com/jannekbuengener/sample-brain/issues/762) supersedes the older
#693/#725 “always Clean Start on every normal launch” rule for returning users
who already have registered Sources. Clean Start remains the correct First View
when the library has **no** usable registered Source.

### First use / no registered Sources

```text
Calm Canvas + primary Add Source + subtle edge affordance
```

Library / Source Navigation, Sample Browser, Harmonic Match, and Live Kit are
**not** materialised as panels. A small left-edge chevron/handle reveals the
Library manually without selecting a Source.

Registered Sources and library data remain on disk. Nothing is deleted by Clean
Start.

Not active on first-use / empty-library launch:

- Source / Root / Subfolder / All Samples / Catalog / Playlist/Collection
- Library / Source Navigation as an open panel
- Sample Browser as an active working pane
- Harmonic Match
- Live Kit as an active working pane
- Sample selection
- Preview / Transport
- Scroll position as visible working context

### Returning use / valid persisted Source(s)

```text
Library visible + active Source scope + Browser materialised
```

Authority for which Source to activate (smallest deterministic policy):

1. Explicit `startup_source_node_id` from the Startup Preset, when present and
   available.
2. Otherwise the first **available** registered Root from the existing library
   folder order (`list_library_folders` / `last_opened_at`, then stable id).
3. Missing/offline preferred Sources are skipped (registration kept); if another
   available persisted Source exists, fall there. If none are available → Clean
   Start (fail soft).

Returning launch must **not** restore transient session state (selection,
preview, harmony, transport, scroll, Live Kit disclosure). No general session
snapshot.
## Progressive disclosure

```text
No persisted Sources:
  COLLAPSED_CLEAN_START
    → optional edge reveal (no Source)
    → OPENED_NO_SOURCE  (Library + Calm Canvas)
    → user selects a Source (or Add Source analysis succeeds)
    → ACTIVE_SOURCE

Persisted valid Source(s) (#762):
  RETURNING_WORKSPACE
    → Library + Browser materialise automatically
    → Harmonic Match stays closed
    → Live Kit stays hidden until Add-to-Kit intent
```

After successful analysis / Source activation (#742/#747/#748/#762):

```text
Source Navigation | Browser
```

Both Library and Browser materialise together (no Library-only or Browser-only
half state). Live Kit is not co-materialised with Browser. It reveals only on
the first explicit Browser or Harmony Add-to-Kit intent (`live_kit_revealed`).
### Live Kit group disclosure (#743)

When the Live Kit pane first becomes visible, group disclosure defaults to
**all four groups collapsed**:

- Kick + Bass
- Drums
- Melodic
- Atmos / FX

`LiveKitPresentationState.active_group` starts as `None`. The first reveal
shows only the four compact group headers; slot rows appear only after an
explicit group expand. Zero expanded groups is valid. Accordion semantics
after that remain unchanged (one active group; clicking the active group
collapses it). Expand/collapse is presentation state only and must not
mutate Live-Kit assignments, Sample/Source selection, Preview, musical
session/preset state, or export/audition semantics.

Geometry for the Active Source workspace is owned exclusively by #694
(elastic ratios / persistence). `#725` owns only the No-Source presentation
flag `library_revealed`:

| Condition | Presentation |
|-----------|--------------|
| `has_active_source=False` and `library_revealed=False` | Collapsed Clean Start |
| `has_active_source=False` and `library_revealed=True` | Opened-no-source (Library visible) |
| `has_active_source=True` | #694 Elastic Layout alone |

`library_revealed` is transient No-Source presentation state. It is **not** a
second layout or session-restore authority. Source Selection does not persist
`library_revealed`. Reveal never writes #694 ratios. Restart / Clean Start
resets reveal to collapsed.

### Browser reveal rules

- small, restrained edge affordance (chevron/arrow preferred);
- hover may strengthen it slightly;
- no large button, no permanent red CTA;
- click opens Library deterministically (Opened-no-source);
- Reveal alone selects no Source, starts no Audition, and creates no
  Harmonic-Match anchor or results.

Rules for Source selection:

- activate exactly that Source;
- materialise the Browser via the existing #576 loader path;
- do **not** synthesise a Sample-row selection (`selected_index = -1`);
- do **not** auto-audition / start Preview;
- do **not** open Harmonic Match;
- do **not** reveal Live Kit (Add-to-Kit intent only; #742);
- do **not** restore prior session selection, harmony, preview, or scroll.

## Add Source (#589)

Adding a Source is an explicit user action. After successful registration /
analysis it **must** activate that exact new Source and materialise Library +
Browser automatically (no second manual Source selection).

Returning launch (#762) reuses the **same** persisted library Source authority
(`workbench_library.db` folders + optional Startup designation). It is not a
second Source database and not a general last-session snapshot.

## Calm Canvas

When no Source is active, the centre surface is a Calm Canvas:

- near-black;
- restrained Sample Brain / Brain identity;
- no feature catalogue;
- no mandatory heavy live blur;
- a clear Add-Source path as the primary action;
- optional Select-Source path after Library reveal.

## Transient vs preference state

| Kind | Examples | Normal launch |
|------|----------|---------------|
| Persistent library data | registered Sources, cache rows, `last_opened_at` | kept; drives Returning Workspace (#762) |
| UI preferences (#696) | panel visibility / layout ratios, density, motion, optional startup Source | see [`WORKBENCH_DISPLAY_PREFERENCES.md`](WORKBENCH_DISPLAY_PREFERENCES.md); Startup Source is an optional preference override, not required for Returning Workspace |
| Layout ratios (#694) | relative panel weights only | may restore on launch; never restores selection/harmony/preview |
| Transient No-Source reveal (`library_revealed`) | Library edge reveal without Source | **never** restored on empty Clean Start; Active Source materialisation sets Library visible |
| Transient session | browser selection, preview, harmony open/results, scroll, Live Kit disclosure | **never** restored on normal launch |

Panel **geometry** after Active Source is owned by
[`WORKBENCH_ELASTIC_LAYOUT.md`](WORKBENCH_ELASTIC_LAYOUT.md) (#694). Elastic
persistence restores ratios only and must not reopen transient session context.

Stale or corrupt preference / preset persistence must not crash. A missing or
offline designated Startup Source falls through to the next available persisted
library Source when one exists (#762); otherwise Clean Start.

## Startup Preset contract

Empty library → Clean Start. Persisted available Sources → Returning Workspace
(#762), without requiring “Set as Startup”. An explicit Startup Preset Source
remains an optional preference override when present and available.

Product Preferences UI, writers, Reset Layout, and Set-as-Startup ownership:
[`WORKBENCH_DISPLAY_PREFERENCES.md`](WORKBENCH_DISPLAY_PREFERENCES.md) (#696).

#693/#762 keep the **read/resolve** seam in `src/workbench_qml_startup.py`. #696
extends that seam with product write/UI.

Preset may store:

- schema `version`;
- panel visibility / layout ratios;
- density mode (first #696 slice: Compact only);
- motion mode (`on` \| `reduced` \| `off`; legacy `full` normalizes to `on`);
- optional `startup_source_node_id`.

Preset must **not** store:

- Sample selection;
- Preview / Transport;
- Harmonic Match results / transient anchor;
- scroll position as a session snapshot;
- transient `library_revealed` No-Source reveal state.

Resolve rules:

1. Missing / corrupt / invalid preset → ignore preset Source; still consider
   persisted library Sources (#762).
2. Preset with `startup_source_node_id` that resolves to an available selectable
   node → Active Source for that node (Library + Browser; Harmony closed; Live
   Kit hidden until Add-to-Kit; `selected_index = -1`).
3. Preset Source missing / offline / unresolvable → try next available persisted
   library Source; if none → Clean Start (fail soft; do not delete registration).
4. No preset Source and no available persisted Sources → Clean Start (collapsed).

Module seam: `src/workbench_qml_startup.py`.

## Visual acceptance

Product projection must honour existing v2 state IDs:

- `screen1-clean-start` — collapsed Source Navigation (Calm Canvas + Add Source
  + edge affordance); no source selected
- `screen1-active-source`

Additional #725 Runtime-/Interaction-Captures (not a parallel fixture family):

- `clean-start-collapsed` (maps to `screen1-clean-start`)
- `clean-start-reveal-hover`
- `opened-no-source`
- `active-source` (maps to `screen1-active-source`)

Evidence stays outside the repository. Agent visual/runtime acceptance owns
closure; see `WORKBENCH_VISUAL_ACCEPTANCE.md` operative rule. Historical v1
evidence stays frozen.

## Non-goals

- Live Kit content redesign
- Panel reordering
- Session snapshot system / last-session auto-resume
- Tk `WorkbenchApp._restore_last_folder` (legacy path)
- Changing #576 scope loaders (only auto-selection of row 0 is superseded)
- Parallel Visual-Acceptance state family / new REQUIRED_STATE_IDS_V2

Display Preferences UI, writers, and Startup designation product actions are
owned by #696 / [`WORKBENCH_DISPLAY_PREFERENCES.md`](WORKBENCH_DISPLAY_PREFERENCES.md).

## Authority

On conflicts for normal startup visibility / restore:

`#762 (Returning Workspace) > #725/#693 empty-library Clean Start > #691 > #700 fixture docs > historical #503/#518 startup restore`

Empty-library / First-use First View remains owned by #725/#693. Returning
Workspace with persisted Sources is owned by #762. After Active Source
materialisation, #694 is exclusive for panel geometry / ratios. After the user
explicitly selects a navigation node, #576 remains authoritative for scope
loading. #589 remains authoritative for explicit Add Source activation.
