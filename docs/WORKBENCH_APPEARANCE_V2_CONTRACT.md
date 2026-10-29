# Workbench Appearance V2 Contract — Sample Brain

**Status:** ACTIVE_SUPPORTING — contract freeze for [#1252](https://github.com/jannekbuengener/sample-brain/issues/1252)
**Parent:** [#1251](https://github.com/jannekbuengener/sample-brain/issues/1251) Appearance System V2
**Runtime implementation:** [#1253](https://github.com/jannekbuengener/sample-brain/issues/1253)
**Persistence migration:** [#1254](https://github.com/jannekbuengener/sample-brain/issues/1254)
**QML bridge:** [#1255](https://github.com/jannekbuengener/sample-brain/issues/1255)
**Settings UI:** [#1256](https://github.com/jannekbuengener/sample-brain/issues/1256)
**Screen-1 adoption:** [#1257](https://github.com/jannekbuengener/sample-brain/issues/1257)
**Final acceptance:** [#1258](https://github.com/jannekbuengener/sample-brain/issues/1258)
**Machine-readable companion:** [`assets/themes/appearance.v2.contract.json`](assets/themes/appearance.v2.contract.json)

```text
APPEARANCE_V2_CONTRACT_FROZEN
```

This document freezes the **normative contract plane** for Appearance V2. It does not implement Theme Core V2, migrate preference files, create QML controls, restyle Screen 1, or change Windows DWM behavior.

The delivered #785 Theme Core remains the compatibility baseline. V2 evolves that owner instead of creating a second palette/state system.

## 1. Architecture boundary

```text
Python Appearance Authority
    ↓
resolved Appearance state
    ↓
deterministic semantic token snapshot
    ↓
QML projection
    ↓
components bind semantic roles

QML user intent
    ↓
typed command
    ↓
Python Appearance Authority
```

Hard rules:

- Python owns Appearance state resolution and token derivation.
- QML does not persist Appearance values and does not derive competing colors.
- Persistence stores user intent/explicit overrides; derived tokens are regenerated.
- Background / Foreground / Accent remain the small user-editable color primitive set.
- Colored semantic meaning does **not** imply Accent ownership.
- The contract is local/offline-first; no account or cloud dependency.

## 2. Compatibility with #785 Theme Core

Current `src/workbench_theme.py` and `docs/assets/themes/presets.v1.json` remain shipped/runtime authority until #1253/#1254 land.

At V2 neutral Contrast (`50`), the existing dark preset result must remain exact:

| #785 token | V2 semantic role |
|---|---|
| `accent` | `accent.base` |
| `textPrimary` | `text.primary` |
| `textSecondary` | `text.secondary` |
| `surfaceWorkspace` | `surface.canvas` |
| `surface` | `surface.panel` |
| `surfaceRaised` | `surface.raised` |
| `divider` | `border.subtle` |
| `hover` | `surface.hover` |
| `selected` | `surface.selected` |
| `focusRing` | `interaction.focus` |

For default Blood at V2 neutral Contrast this means Theme Core Blood defaults remain exact, including the #1205 canvas target (`background` `#0b0d10`, `surfaceWorkspace`/`surface.canvas` `#0d0f12`, `#e4e6ea` foreground, `#8f0e24` Accent and the derived surface ladder). Appearance V2 must not redefine the #1205 workspace visual target.

Existing v1 named custom themes must retain their name, selected state when valid, and normalized `accent/background/foreground` triplet during #1254 migration.

## 3. Canonical Appearance state

### Global state

| Field | Values / bounds | Default | Rule |
|---|---|---|---|
| `mode` | `system | light | dark` | `dark` | Preserve current dark #785 behavior; System resolves OS scheme and falls back to dark when unavailable. |
| `separateLightDark` | boolean | `false` | Shared overrides by default; independent scheme overrides only when enabled. |
| `uiFontSize` | integer `12..18` logical px | `14` | Semantic UI typography scale only; no automatic pane/control geometry scaling. |
| `codeFontSize` | integer `10..18` logical px | `12` | Independent monospace/code role. |
| `motionMode` | `system | on | reduced | off` | `on` | Reuses #696; see Motion compatibility below. |

### Profile state

Each Appearance profile may carry:

- `themeRef`
- explicit `background`
- explicit `foreground`
- explicit `accent`
- `contrast` (`0..100`, default `50`)

No derived semantic token is user-owned profile state.

### Shared vs separated profiles

`separateLightDark = false`:

1. Resolve the active scheme (`dark`, `light`, or System result).
2. Resolve that scheme's theme variant.
3. Apply one shared explicit override set.
4. Validate accessibility.
5. Derive semantic tokens.

`separateLightDark = true`:

- light and dark explicit overrides are independent;
- switching schemes never deletes or overwrites the inactive profile;
- mode switching changes only the resolved profile, not ownership.

A v1 theme supplies an exact dark variant. A missing light variant uses the V2 neutral-light fallback:

```text
background = #f7f7f5
foreground = #171719
accent     = selected theme Accent
```

This fallback is a compatibility bridge, not a claim that every future preset must share one light background/foreground pair.

## 4. Motion compatibility — correction to the initial #1251 shorthand

The repository already has an active Display Preferences contract under **#696**:

```text
on | reduced | off
```

Appearance V2 must reuse that owner. It must **not** introduce a second independently persisted `reduceMotion` state.

The V2 canonical field is therefore:

```text
motionMode = system | on | reduced | off
```

Resolution:

- `on` → full presentation motion allowed;
- `reduced` → same functional outcome with reduced presentation motion;
- `off` → no feature-motion work where the #696 contract permits;
- `system` → platform Reduce Motion true → `reduced`; false → `on`; unavailable → `on`.

This is an explicit compatibility correction: the issue shorthand “Reduce Motion System/On/Off” is normalized onto the existing #696 motion authority rather than forking state.

## 5. Semantic token model

### Surface

- `surface.canvas`
- `surface.panel`
- `surface.raised`
- `surface.hover`
- `surface.selected`

### Text

- `text.primary`
- `text.secondary`
- `text.muted`
- `text.disabled`

### Border

- `border.subtle`
- `border.default`
- `border.strong`

### Accent

- `accent.base`
- `accent.hover`
- `accent.active`
- `accent.subtle`
- `accent.onAccent`

### Interaction

- `interaction.focus`
- `interaction.selection`
- `interaction.pressed`
- `interaction.disabled`

### Protected status / product semantics

- `status.error`
- `status.warning`
- `status.success`
- `status.info`
- `protectedHighlight.*`

### Other semantic families

- `typography.ui`
- `typography.code`
- `motion.effective`
- `windowChrome.background`
- `windowChrome.foreground`
- `windowChrome.border`

Normal components consume semantic roles. Raw primitives are reserved for the derivation layer or a role explicitly defined as the primitive itself (`accent.base`).

## 6. Ownership / derivation matrix

| Family | Owner |
|---|---|
| `surface.*` | Background + Foreground + bounded Contrast; selected additionally consumes Accent |
| `text.primary` | Foreground |
| `text.secondary/muted/disabled` | Foreground + Background + bounded Contrast |
| `border.*` | Background + Foreground + bounded Contrast |
| `accent.base` | Accent |
| `accent.hover/active` | Accent mixed toward Foreground at fixed ratios |
| `accent.subtle` | Background + Accent + bounded Contrast |
| `accent.onAccent` | whichever of Background/Foreground has higher WCAG contrast against Accent |
| `interaction.focus` | Accent with accessibility guard; base Accent is never mutated |
| `interaction.selection` | `surface.selected` |
| `interaction.pressed` | `accent.active` |
| `status.*` | protected scheme palette, independent from user Accent/Contrast |
| `protectedHighlight.*` | owning product/consumer semantic contract; never implicit Accent alias |
| `typography.ui` | UI font preference + semantic type scale |
| `typography.code` | independent code font preference |
| `windowChrome.*` | mappings from surface/text/border semantics for #1214 |

## 7. Protected colors

Global Accent must **not** recolor semantic meaning by accident.

Protected families:

- destructive / error;
- warning;
- success / positive confirmation;
- informational / status;
- accessibility-critical feedback where an Accent alias would fail contrast;
- music/product-specific highlights whose identity matters independently from Accent.

Frozen status palette:

| Role | Dark | Light |
|---|---|---|
| Error | `#e06a74` | `#a93245` |
| Warning | `#d2a64f` | `#8a5d12` |
| Success | `#69ad82` | `#2f714c` |
| Info | `#75a7c8` | `#346f96` |

These values do not follow Accent and do not move with the Contrast control.

Product-specific protected highlights remain owned by their consumer contract. Example: #1248's Library navigation icon accents remain semantically intentional and must not all become the global Accent. #1252 does not overwrite their exact visual contract.

## 8. Contrast model

Contrast is an integer `0..100`. `50` is neutral and preserves #785 dark tokens exactly.

Contrast changes **derived separation**, not user primitives.

Interpolation is piecewise linear through anchors at `0`, `50`, `100`, using the existing Theme Core linear sRGB-channel `mix_hex` rounding semantics.

| Semantic role / mix direction | 0 | 50 | 100 |
|---|---:|---:|---:|
| `text.secondary` FG→BG | .68 | .55 | .42 |
| `text.muted` FG→BG | .78 | .68 | .58 |
| `text.disabled` FG→BG | .86 | .78 | .70 |
| `surface.canvas` BG→FG | .004 | .008 | .016 |
| `surface.panel` BG→FG | .014 | .028 | .056 |
| `surface.raised` BG→FG | .03 | .06 | .12 |
| `surface.hover` BG→FG | .04 | .075 | .13 |
| `surface.selected` BG→Accent | .14 | .22 | .32 |
| `border.subtle` BG→FG | .05 | .10 | .20 |
| `border.default` BG→FG | .075 | .15 | .30 |
| `border.strong` BG→FG | .10 | .20 | .40 |
| `accent.subtle` BG→Accent | .10 | .16 | .24 |

Fixed Accent interaction ratios:

```text
accent.hover  = mix(accent, foreground, 0.12)
accent.active = mix(accent, foreground, 0.20)
```

Contrast must **not** change:

- `background`
- `foreground`
- `accent.base`
- `accent.hover`
- `accent.active`
- `accent.onAccent`
- `status.*`
- `protectedHighlight.*`

Golden low/default/high vectors are pinned in the machine-readable companion.

## 9. Accessibility guards

- `text.primary` against the base/background context must meet at least **4.5:1**.
- visible focus indication must meet at least **3:1** against adjacent colors.
- `accent.onAccent` chooses Background or Foreground by higher WCAG contrast.
- a custom profile that fails required primary readability is rejected on commit; the last valid profile remains authoritative.
- accessibility repair may adjust a **derived** focus/on-accent token but must never silently rewrite the user's primitive Background/Foreground/Accent.
- protected status colors are not recolored by Contrast.

## 10. Typography

The approved Screen-1 scale from #1248/#1249 is the default V2 semantic baseline:

| Role | Size / line height |
|---|---|
| Caption | `12 / 16` |
| Standard UI | `14 / 20` |
| Content | `16 / 26` |
| Section | `14 / 18`, weight `500` |
| Page/pane-title reference | `24 / 29` |

`uiFontSize = 14` is neutral. Other supported UI sizes compute:

```text
uiScale = uiFontSize / 14
```

Semantic font sizes and line heights scale by `uiScale` and round to the nearest `0.5` logical px.

This setting does **not** automatically scale pane widths, row heights, icon boxes, hit targets, or other geometry. A component may adapt geometry only through its own explicit layout contract.

Code typography is independent:

```text
codeFontSize = 10..18, default 12
codeLineHeight = round_to_nearest_0.5(codeFontSize * 1.5)
```

No bundled font is required by this contract; use the platform/existing product monospace path.

## 11. Persistence boundary

#1252 freezes the **state semantics**, not the storage JSON shape.

#1254 owns the versioned persistence schema and migration execution.

Required persistence behavior:

- store user intent / explicit overrides only;
- do not persist the full derived token snapshot;
- preserve valid #785 selected preset and custom theme triplets;
- no QML-owned second store;
- no account/cloud dependency;
- corrupt/future state fails closed without blocking launch;
- no private paths, sample data, DB/index/cache references, credentials or machine identity.

## 12. Consumer boundaries

| Existing owner | V2 relationship |
|---|---|
| #1205 | Workspace visual target remains owned there; V2 supplies semantic surface authority. |
| #1214 | Native Windows chrome remains owned there; it consumes `windowChrome.*`. |
| #1248 | Library geometry/icon/type contract stays intact at default Appearance settings. |
| #1249 | Screen-1 typography defaults stay intact; V2 supplies the semantic type scale. |
| #894 | Delivered dark solid-surface/no-glow hierarchy remains preserved. |
| #895 | Delivered secondary-control chrome remains preserved. |
| #696 | Existing `on | reduced | off` motion preference semantics are reused, not forked. |

## 13. Golden cases

The machine-readable companion pins at least:

1. Blood dark / Contrast 50 exact #785 compatibility;
2. Carbon dark / Contrast 50;
3. custom Background/Foreground/Accent;
4. Blood Contrast 25 / 50 / 75;
5. radically different red vs green Accents with unchanged protected status colors;
6. unseparated shared profile behavior;
7. separated Light/Dark profile behavior;
8. independent UI / code font sizing.

These are contract vectors for #1253/#1254/#1255. They are **not** proof that runtime V2 exists before those issues land.

## 14. Hard out of scope for #1252

- runtime Theme Core V2 implementation;
- preference-schema migration execution;
- QML bridge implementation;
- Appearance settings UI;
- Screen-1 component migration/restyling;
- Windows DWM implementation;
- Arrangement / Live work;
- cloud theme sync/accounts;
- arbitrary CSS/QML skin scripting;
- private samples, DBs, indexes, caches, credentials or machine-specific state.

## 15. Downstream implementation order

```text
#1252 Contract freeze
   ↓
#1253 Python Core  ─────┐
#1254 Persistence ──────┤
                       ↓
                  #1255 QML Bridge
                    ↓           ↓
           #1256 Settings   #1257 Screen-1 adoption
                    \           /
                     ↓         ↓
                   #1258 Acceptance
```

No downstream child may reinterpret protected-color ownership, neutral #785 compatibility, Contrast scope, or the #696 motion compatibility rule without an explicit contract change.

---

`APPEARANCE_V2_CONTRACT_FROZEN`
