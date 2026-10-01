# Workbench Browser Column Arrangement Contract (#767)

## Purpose

Defines the default Screen-1 Browser sample-row information order for
compact density. This is a layout/projection contract over existing Browser
row chrome (#603/#692). It does not change density tokens, search, audition,
virtualization, Live Kit, Harmonic Match logic, or packaging.

## Default column order

```text
Waveform / Preview
→ Sample Name
→ BPM
→ Favorite
→ Key
→ Length
```

Scan intent: audio shape → identity → tempo → personal marker → harmony → duration.

## Favorite (not a rating)

Favorite is the compact personal-marker column from #766:

- empty star = not favorite
- filled star = favorite
- no 1–5 rating domain
- no renderer-local favorite state; persistence is Python/domain-owned

This slice implements the Favorite column + persistence wiring. Full Favorites
navigation/scope in the compact top icon bar is owned by #766
(`LibraryScopeKind.FAVORITES` / `scope:favorites`).

## Column behavior

- Waveform remains the primary audio affordance; click still auditions.
- Sample Name receives the largest flexible text width (`Layout.fillWidth`).
- BPM / Favorite / Key / Length use fixed/preferred widths and stay aligned
  between header and row.
- Favorite is a small fixed interaction column.
- Sample Type may remain secondary (for example after Length) but must not
  displace the default order above.
- Add-to-Kit remains available and must not dominate the metadata scan path.

## Density (frozen for this slice)

Do not change:

- `densityRowHeight=30`
- `densityVerticalInset=4`
- `densityHorizontalInset=8`
- `densityWaveformHeight=22`
- `densityRowSpacing=8`
- `densityDividerHeight=1`
- `densityActionHitTarget=24`

## Interaction preserved

Waveform click → preview, row selection, ↑/↓, Esc stop, search focus
protection, virtualization, and Add-to-Kit remain intact.

## Non-scope

- #776 typography/meta color weight (independent PR; do not duplicate here)
- density retarget, CLEAN_START, Elastic layout changes
- waveform render/animation redesign
- Live Kit / Screen 2 / state IDs / audio / catalog / search / harmony logic
- Favorites navigation surface (delivered by #766; this contract does not
  reimplement it)
- Rekordbox clone, cue/deck/DJ controls, packaging

## Typography note versus #776

Sample Name stays primary. BPM/Key/Length secondary text color is the desired
end-state owned by #776 when merged. This contract owns column order and
Favorite wiring only; it keeps `origin/main` text-color reality unless #776
is already on main.
