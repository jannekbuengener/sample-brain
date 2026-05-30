# AGENTS.md - docs Scope

## Scope
- Applies to all files under `docs/`.

## Documentation Intent
- Keep docs aligned with actual repository behavior and current code contracts.
- Prefer short, decision-ready updates over speculative roadmap text.
- When uncertain, verify against `src/` and tests before writing claims.

## Key Doc Themes in this Repo
- Product and system requirements
- Pipeline and architecture guidance
- Integration and operational notes
- Backlog and branch/process policy

## Update Rules
- Do not present planned features as implemented.
- Mark assumptions clearly when evidence is missing.
- Keep terminology consistent with runtime modules (`scan`, `analyze`, `autotype`, `embed`, `index`, `search`).
- Avoid embedding machine-local setup artifacts or secrets.

## Cross-Checks Before Finalizing Doc Changes
- Confirm command examples against `src/cli.py`.
- Confirm data/schema statements against `src/db.py`.
- Confirm config behavior against `src/config_loader.py` and `config/profiles.example.yaml`.
