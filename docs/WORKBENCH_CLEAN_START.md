# Screen-1 Clean Start — source-driven progressive disclosure (#693)

Parent: [#691](https://github.com/jannekbuengener/sample-brain/issues/691).  
Shared visual states: [#700](https://github.com/jannekbuengener/sample-brain/issues/700) / [`WORKBENCH_VISUAL_ACCEPTANCE.md`](WORKBENCH_VISUAL_ACCEPTANCE.md).  
Add Source: [#589](https://github.com/jannekbuengener/sample-brain/issues/589).  
Library loaders after explicit node selection: [#576](https://github.com/jannekbuengener/sample-brain/issues/576).

## Product default

Every normal QML Screen-1 launch begins **neutral**. Clean Start is product
behaviour, not a first-run special case.

Canonical launch composition:

```text
Source Navigation | Calm Canvas
```

Registered Sources and library data remain on disk. Nothing is deleted by Clean
Start.

Not active at normal launch:

- Source / Root / Subfolder / All Samples / Catalog / Playlist/Collection
- Sample Browser as an active working pane
- Harmonic Match
- Live Kit as an active working pane
- Sample selection
- Preview / Transport
- Scroll position as visible working context

## Source-driven disclosure

```text
CLEAN_START
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
- a clear Select-Source / Add-Source path.

## Transient vs preference state

| Kind | Examples | Normal launch |
|------|----------|---------------|
| Persistent library data | registered Sources, cache rows | kept |
| UI preferences (later #696) | panel ratios, density, motion, optional startup Source | may apply only via explicit Startup Preset |
| Transient session | active Source, browser selection, preview, harmony open/results, scroll | **never** restored on normal launch |

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
- scroll position as a session snapshot.

Resolve rules:

1. Missing preset file → Clean Start.
2. Corrupt / invalid JSON / wrong version / incomplete fields → Clean Start
   (`persistable=False` semantics; no crash).
3. Preset with `startup_source_node_id` that resolves to an available selectable
   node → Active Source for that node (Browser + Live Kit; Harmony closed;
   `selected_index = -1`).
4. Preset Source missing / offline / unresolvable → Clean Start (fail closed).

Module seam: `src/workbench_qml_startup.py`.

## Visual acceptance

Product projection must honour v2 state IDs:

- `screen1-clean-start`
- `screen1-active-source`

Evidence stays outside the repository. Owner Visual Acceptance remains separate
from agent self-attestation.

## Non-goals

- Elastic proportional resize (#694)
- Full display Preferences / Startup Preset UI (#696)
- Live Kit content redesign
- Session snapshot system
- Tk `WorkbenchApp._restore_last_folder` (legacy path)
- Changing #576 scope loaders (only auto-selection of row 0 is superseded)

## Authority

On conflicts for normal startup visibility / restore:

`#693 > #691 > #700 fixture docs > historical #503/#518 startup restore`

After the user explicitly selects a navigation node, #576 remains authoritative
for scope loading. #589 remains authoritative for explicit Add Source activation.
