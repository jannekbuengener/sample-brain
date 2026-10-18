## 2026-08-09 - QML Custom Icon Buttons Accessibility
**Learning:** Custom icon-only buttons built from QML `Item` + `MouseArea` + `Label`/`Text` (such as favorite toggles) lack default accessibility semantics and are unannounced to screen reader users unless explicitly configured.
**Action:** Always attach `Accessible.role: Accessible.Button`, `Accessible.name` (dynamically reflecting active/inactive state), and `Accessible.onPressAction` to custom QML icon buttons.
