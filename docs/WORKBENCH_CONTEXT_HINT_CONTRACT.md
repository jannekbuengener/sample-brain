# Workbench Context Hint Contract (#770)

## Purpose

Screen 1 shows a small context hint / legend for icon-only controls. Hover or
keyboard focus on a supported control updates one shared hint surface.
Cursor-adjacent tooltips are not the primary discoverability path for these
controls.

## Placement

#830 (`docs/PROGRAM_CHROME_CONTRACT.md`) owns the global footer band. The hint
is status text inside that band, on the right, display-only. It must not cover
utility hit areas and it is not its own centered strip.

- at the bottom of the window, inside the program footer, on the right
- visually small and calm
- uses existing Screen-1 theme tokens
- does not steal unnecessary workspace height
- does not overlap Browser rows, transport, or other actionable chrome

No drag, dock, snap, free positioning, or placement persistence in V1.

Content/state ownership stays separate from placement so a later modular
layout/snap system can move the surface without rewriting hint semantics.

## Hint priority (deterministic)

```text
hovered actionable control
    >
keyboard-focused actionable control
    >
neutral / empty
```

When hover ends but a supported control still has keyboard focus, restore the
focus hint. When neither hover nor relevant focus is active, show the neutral
empty state. The hint surface itself must never take keyboard focus.

## Descriptor / state seam

Supported controls expose:

- stable semantic ID
- short label
- concise help text

A shared ephemeral UI-state seam owns the current hint content. QML may report
hover/focus intents and render the resolved display text. No new persistence,
DB, or global product-state authority.

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
