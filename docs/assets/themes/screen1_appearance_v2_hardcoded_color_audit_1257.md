# Screen-1 Appearance V2 Hardcoded Color Audit (#1257)

**Status:** ACTIVE_SUPPORTING evidence for [#1257](https://github.com/jannekbuengener/sample-brain/issues/1257)  
**Exact-head baseline:** `9218e6d09d8cc372e4c6cddb51f2dd440d184567`  
**Exit:** `SCREEN1_APPEARANCE_V2_TOKENIZED`

```text
Python Appearance Authority (#1253)
        ↓
#1255 themeAuthority / resolved snapshot
        ↓
semantic V2 tokens
        ↓
Screen-1 QML components (#1257)
```

Disposition values only: `TOKENIZED` | `PROTECTED_SEMANTIC` | `PLATFORM_OWNED` | `JUSTIFIED_LITERAL` | `OUT_OF_SCOPE_OWNER`.

## Authority surfaces

| FILE / COMPONENT | CURRENT COLOR SOURCE | SEMANTIC ROLE | V2 TOKEN | DISPOSITION |
|---|---|---|---|---|
| `workbench_appearance.py` | Python derivation | V2 authority | dotted semantic keys | TOKENIZED |
| `workbench_theme.project_appearance_snapshot_for_qml` | Appearance snapshot | #785 compat + V2 overlay | `semantics` + `tokens` | TOKENIZED |
| `workbench_qml._qml_theme_authority_bridge` | projected snapshot | renderer bridge | camelCase + `tokenSnapshot` | TOKENIZED |
| `workbench_qml` `QtObject id: theme` | `themeAuthority.*` | Screen-1 facade | semantic roles | TOKENIZED |
| `workbench_native_window_chrome.py` | `windowChrome.*` | native caption | `windowChrome.*` | PLATFORM_OWNED |
| Appearance popover primitive editors | `baseAccent/Background/Foreground` | raw user primitives | primitives (not fills) | OUT_OF_SCOPE_OWNER |
| #1256 Settings UI | not in this slice | settings surface | — | OUT_OF_SCOPE_OWNER |
| #1293 Library rail insets | geometry only | rail inset | — | OUT_OF_SCOPE_OWNER |

## Active Screen-1 consumers (summary)

| FILE / COMPONENT | CURRENT COLOR SOURCE | SEMANTIC ROLE | V2 TOKEN | DISPOSITION |
|---|---|---|---|---|
| ApplicationWindow / workspace canvas (#1205) | `theme.surfaceRoot` | canvas | `surface.canvas` | TOKENIZED |
| Panel disclosure seams (#1204) | hover / divider / secondary | hover + hairline | `surface.hover` / `border.subtle` / `text.secondary` | TOKENIZED |
| Program Chrome header/footer | header / text / accent / divider | chrome | `windowChrome.background`-aligned header + text/accent/border | TOKENIZED |
| Library pane / rows / icons (#1248) | library surface + protected accents | product Library | `surfaceLibrary` + `protectedHighlight.*` | PROTECTED_SEMANTIC |
| Library focus ring | `libraryFocusRing` | non-Accent focus | protected / secondary-derived | PROTECTED_SEMANTIC |
| Browser surface / rows / waveform | panel / selection / hover / waveform | browser presentation | `surface.panel` / `surface.selected` / `surface.hover` / accent+secondary waveform | TOKENIZED |
| Browser / analysis error chrome | `theme.statusError` | destructive/error | `status.error` | TOKENIZED |
| Harmonic Matches surfaces | panel / selection / hover / text | matches presentation | surface/text/interaction | TOKENIZED |
| Live-Kit HUD (#1207) | raised/panel + accent feedback | HUD presentation | `surface.raised` / accent-owned actions | TOKENIZED |
| Live-Kit export failure text | `theme.statusError` | error | `status.error` | TOKENIZED |
| Search / rename placeholders | `theme.textMuted` | muted placeholder | `text.muted` | TOKENIZED |
| Menus / popovers / raised prefs | elevated + selection + focus | raised surfaces | `surface.raised` / `surface.selected` / `interaction.focus` | TOKENIZED |
| Footer / context hint (#1210) | header + secondary | chrome + hint | chrome / `text.secondary` | TOKENIZED |
| Onboarding / preparing (#1213) | canvas / panel / accent progress | readiness presentation | `surface.canvas` / `surface.panel` / `accent.base` | TOKENIZED |
| Disabled text/controls | `theme.textDisabled` | disabled | `text.disabled` | TOKENIZED |
| Pressed accent edges | `theme.interactionPressed` | pressed | `interaction.pressed` | TOKENIZED |
| Hover / selected / focus | hover / selected / focusRing | interaction | `surface.hover` / `surface.selected` / `interaction.focus` | TOKENIZED |
| `"transparent"` fills | named color | non-paint | — | JUSTIFIED_LITERAL |
| Library label fade `Qt.rgba(surfaceLibrary, 0)` | theme surface alpha | #1248 fade only | surfaceLibrary | JUSTIFIED_LITERAL |

## Raw primitive rule

Normal Screen-1 components must not bind `background` / `foreground` / `accent` primitives when a semantic role exists. Accent-owned UI continues through `theme.actionActive` (`accent.base`) or explicit accent family tokens. Protected status/highlights never collapse onto Accent.

## Non-goals preserved

- No #1256 Settings UI
- No #1293 Library rail geometry
- No #1214 native chrome rewrite
- No QML color derivation / persistence
- No geometry or #1249 typography scale rewrite
