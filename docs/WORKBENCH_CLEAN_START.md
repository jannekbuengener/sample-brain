# Screen-1 Clean Start — source-driven progressive disclosure (#693 / #725)

Parent: [#691](https://github.com/jannekbuengener/sample-brain/issues/691).
Shared visual states: [#700](https://github.com/jannekbuengener/sample-brain/issues/700) / [`WORKBENCH_VISUAL_ACCEPTANCE.md`](WORKBENCH_VISUAL_ACCEPTANCE.md).
Add Source: [#589](https://github.com/jannekbuengener/sample-brain/issues/589).
Library loaders after explicit node selection: [#576](https://github.com/jannekbuengener/sample-brain/issues/576).
Collapsed First View / reveal affordance: [#725](https://github.com/jannekbuengener/sample-brain/issues/725).
Panel geometry after Active Source: [#694](https://github.com/jannekbuengener/sample-brain/issues/694) / [`WORKBENCH_ELASTIC_LAYOUT.md`](WORKBENCH_ELASTIC_LAYOUT.md).

## Product default

Every normal QML Screen-1 launch begins **neutral**. Clean Start is product
behaviour, not a first-run special case.

Canonical First View (normal launch):

```text
Calm Canvas + primary Add Source + subtle edge affordance
```

Library / Source Navigation, Sample Browser, Harmonic Match, and Live Kit are
**not** materialised as panels. A small left-edge chevron/handle reveals the
Library manually without selecting a Source.

Registered Sources and library data remain on disk. Nothing is deleted by Clean
Start.

Not active at normal launch:

- Source / Root / Subfolder / All Samples / Catalog / Playlist/Collection
- Library / Source Navigation as an open panel
- Sample Browser as an active working pane
- Harmonic Match
- Live Kit as an active working pane
- Sample selection
- Preview / Transport
- Scroll position as visible working context

## Progressive disclosure

```text
COLLAPSED_CLEAN_START
  → optional edge reveal (no Source)
  → OPENED_NO_SOURCE  (Library + Calm Canvas)
  → user selects a Source (or Add Source completes)
  → ACTIVE_SOURCE
  → Browser materialises
  → Live Kit may appear as an active working pane
  → Harmonic Match stays closed until explicit toggle
```

After explicit Source selection:

```text
Source Navigation | Browser | Live Kit
```

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
- do **not** restore prior session selection, harmony, preview, or scroll.

## Add Source (#589)

Adding a Source is an explicit user action. After successful registration /
analysis it **may** activate that exact new Source and show its Browser.

This must never be generalised into “restore last Source on app launch”.

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
| Persistent library data | registered Sources, cache rows | kept |
| UI preferences (later #696) | panel visibility / layout ratios, density, motion, optional startup Source | may apply only via explicit Startup Preset |
| Layout ratios (#694) | relative panel weights only | may restore on launch; never restores Source/selection/harmony/preview |
| Transient No-Source reveal (`library_revealed`) | Library edge reveal | **never** restored; always collapsed |
| Transient session | active Source, browser selection, preview, harmony open/results, scroll | **never** restored on normal launch |

Panel **geometry** after Active Source is owned by
[`WORKBENCH_ELASTIC_LAYOUT.md`](WORKBENCH_ELASTIC_LAYOUT.md) (#694). Elastic
persistence restores ratios only and must not reopen session context.

Stale or corrupt preference / preset persistence fails closed to Clean Start.
It must not crash and must not silently fall back to another Source.

## Startup Preset contract (hook for #696)

Clean Start remains the default. A later explicit Startup Preset may override
it. This slice prepares the **read/resolve contract only** — no Preferences UI.

Preset may store:

- schema `version`;
- panel visibility / layout ratios;
- density mode;
- motion mode;
- optional `startup_source_node_id`.

Preset must **not** store:

- Sample selection;
- Preview / Transport;
- Harmonic Match results / transient anchor;
- scroll position as a session snapshot;
- transient `library_revealed` No-Source reveal state.

Resolve rules:

1. Missing preset file → Clean Start (collapsed).
2. Corrupt / invalid JSON / wrong version / incomplete fields → Clean Start
   (`persistable=False` semantics; no crash).
3. Preset with `startup_source_node_id` that resolves to an available selectable
   node → Active Source for that node (Browser + Live Kit; Harmony closed;
   `selected_index = -1`).
4. Preset Source missing / offline / unresolvable → Clean Start (fail closed).

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

Evidence stays outside the repository. Owner Visual Acceptance remains separate
from agent self-attestation. Historical v1 evidence stays frozen.

## Non-goals

- Full display Preferences / Startup Preset UI (#696)
- Live Kit content redesign
- Panel reordering
- Session snapshot system
- Tk `WorkbenchApp._restore_last_folder` (legacy path)
- Changing #576 scope loaders (only auto-selection of row 0 is superseded)
- Parallel Visual-Acceptance state family / new REQUIRED_STATE_IDS_V2

## Authority

On conflicts for normal startup visibility / restore:

`#725 (collapsed First View) > #693 > #691 > #700 fixture docs > historical #503/#518 startup restore`

After Active Source materialisation, #694 is exclusive for panel geometry /
ratios. After the user explicitly selects a navigation node, #576 remains
authoritative for scope loading. #589 remains authoritative for explicit
Add Source activation.
