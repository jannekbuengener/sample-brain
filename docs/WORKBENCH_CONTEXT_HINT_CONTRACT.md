# Workbench Context Hint Contract (#770)

## Purpose

Screen 1 shows a small context hint / legend for icon-only controls. Hover or
keyboard focus / selection on a supported control updates one shared hint
surface. Cursor-adjacent tooltips are not the primary discoverability path for
these controls.

## Placement

#830 (`docs/PROGRAM_CHROME_CONTRACT.md`) owns the global footer band. The hint
is display-only status text inside that band. Placement authority for the
**central info zone** is the focused footer-context centering slice (issue
title: `[QML][UX] Centered footer context info with hover/selection priority`;
refs #770 #837 #880):

- at the bottom of the window, inside the program footer
- geometrically centered on the **full footer width** (window/footer midpoint),
  not merely in the leftover space between left and right controls
- LEFT zone keeps existing scope/utility (#837); RIGHT zone keeps existing
  status (may be empty/neutral); CENTER is a true center layer
- CENTER must not use `RowLayout` leftover width if that shifts optical center
- long text elides / fail-soft; must not overlap left or right hit areas; no
  layout jumps when text appears or clears
- visually small and calm; matches #880 slim footer chrome (no box/chip/
  background block/toolbar look; no attention-seeking animation)
- uses existing Screen-1 theme tokens
- does not steal unnecessary workspace height
- does not overlap Browser rows, transport, or other actionable chrome

No drag, dock, snap, free positioning, or placement persistence in V1.

Content/state ownership stays separate from placement so a later modular
layout/snap system can move the surface without rewriting hint semantics.

## Hint priority (deterministic)

```text
hovered actionable control          (HOVER)
    >
keyboard-focused control OR browser sample selection (SELECTION)
    >
neutral / empty                     (DEFAULT)
```

SELECTION has two existing sources, resolved in this order after hover clears:

1. keyboard-focused supported control via the shared hint seam (`focusedId`)
2. browser sample selection via the existing `selectedBrowserIndex` /
   `browserRows` projection (no parallel selection state machine)

Do not invent a second selection state machine or a second display-string
authority for control descriptors. Sample selection display text is a thin
projection of the already-selected browser row metadata (single formatter on
the Python/renderer seam), not a new product selection owner.

When hover ends but a supported control still has keyboard focus, restore that
control hint. When hover ends with no focused control but a browser sample is
still selected, restore the sample selection context. When neither hover nor
relevant selection is active, show the neutral empty state. Hover is temporary
and must not destroy selection identity. The hint surface itself must never
take keyboard focus.

### Sample selection display (footer center)

When SELECTION resolves to a selected browser sample row, show one quiet
compact line from existing projected row fields:

```text
<name> · <bpm> · <key> · <type>
```

Reuse the existing Browser row projection values (`display_name` / `bpm` /
`key` / `sample_type`, including their existing missing-state `"—"` tokens).
Do not invent new metadata, duplicate formatting in QML, or grow footer height.

## Descriptor / state seam

Supported controls expose:

- stable semantic ID
- short label
- concise help text

A shared ephemeral UI-state seam owns the current hint content. QML may report
hover/focus (selection) intents and render the resolved display text. No new
persistence, DB, or global product-state authority.

Display format:

```text
<label> — <help>
```

### V1 semantic IDs (Library icon navigation)

| Semantic ID | Label | Help |
|-------------|-------|------|
| `library.scope.sources` | Sample Sources | analysierte Sample-Quellen |
| `library.scope.all_samples` | All Samples | alle Samples im Workspace |
| `library.scope.collections` | Collections | gespeicherte Sample-Sammlungen |
| `library.scope.favorites` | Favorites | markierte Samples |
| `library.scope.recordings` | Recordings | lokale Aufnahmen |
| `library.add_source` | Add Source | lokalen Sample-Ordner hinzufügen |

#837 removes the visible Catalog navigation control; Catalog core/loaders remain
outside this hint table. Favorites, Collections, and Recordings must remain
distinct. Help strings must not contradict each other across duplicate
registrations.

`library.add_source` may bind the existing compact Calm-Canvas `+` control.
The permanent text `Add Source` header button is not required for V1.

## Accessibility

Icon-only controls retain meaningful `Accessible.name` values. The context
hint supplements discoverability; it does not replace accessibility metadata.
The hint is not a focus target and must not introduce a tooltip dependency for
the Library scope controls.

## Non-scope

- #768 Drag & Drop, #780/#781/#782 chrome slices
- panel reordering, docking, snap system
- tutorial / onboarding / modal help
- Screen 2/3, audio/harmony changes
- general design-system rewrite
- background colors / surface hierarchy (separate next slice)
- program chrome height redesign (#880 baseline stands)
- footer scope control redesign, navigation, Pattern/Bars/Song
