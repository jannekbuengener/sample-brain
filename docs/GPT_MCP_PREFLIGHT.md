# GPT / ChatGPT MCP preflight for Sample Brain

Related: #353, #354, #355

## Zweck

Dieser Vertrag verhindert Fake-Green beim lokalen GPT/ChatGPT-MCP.
Ein Agent darf lokalen Repo-Zugriff, lokale Tests oder private Audio-Evidence erst behaupten, wenn der MCP in der aktuellen Session wirklich nutzbar ist.

## Statusfelder

Jeder Preflight soll mindestens diese Felder ausgeben oder äquivalente Evidence liefern:

```text
local_mcp_available=true|false
mcp_server_reachable=true|false|unknown
mcp_server_version=<version-or-unknown>
mcp_server_build=<build-or-unknown>
sample_brain_root_registered=true|false|unknown
sample_brain_read_smoke=pass|fail|not_run
fallback=none|github_connector
blocker=<none-or-short-reason>
```

`local_mcp_available=true` ist nur zulässig, wenn ein echter Tool-Aufruf in der aktuellen Session erfolgreich war.

## Empfohlener Preflight

1. `mcp_preflight` ausführen.
2. Version/Build-ID und registrierte Roots prüfen.
3. `sample_brain` als Root auswählen.
4. Root-Verzeichnis lesen, zum Beispiel mit `repo_list_dir(repo="sample_brain")`.
5. PASS nur, wenn mindestens diese Einträge sichtbar sind:
   - `SB.BOOTLOADER.md`
   - `src`
   - `tests`

Wenn der verwendete MCP andere Toolnamen besitzt, gilt dieselbe fachliche Prüfung.

## Fehlerklassen

### Session / Host verbietet Developer-MCP

Beispiel:

```text
FORBIDDEN: This conversation does not support developer MCPs
```

Bedeutung:
- kein Sample-Brain-Repo-Fehler belegt
- kein Server-404 belegt
- die aktuelle ChatGPT-Session darf den Developer-MCP nicht ausführen

Status:

```text
local_mcp_available=false
mcp_server_reachable=unknown
sample_brain_root_registered=unknown
sample_brain_read_smoke=not_run
fallback=github_connector
blocker=session_capability_forbidden
```

### Server / Endpoint nicht erreichbar

Beispiel: HTTP 404, Connection refused, Transportfehler.

Bedeutung:
- Session versucht den MCP zu erreichen
- Server/Route/Deployment ist nicht verwendbar

Status: `local_mcp_available=false`, Blocker passend benennen.

### Root nicht registriert

Wenn der MCP läuft, aber `sample_brain` fehlt oder auf den falschen Repo-Root zeigt:

```text
local_mcp_available=false
mcp_server_reachable=true
sample_brain_root_registered=false
sample_brain_read_smoke=fail
```

Nicht auf einen ähnlich benannten Workspace ausweichen.

## GitHub-Fallback

Der GitHub-Connector darf als begrenzter Ersatz verwendet werden für:
- Issues und PRs lesen/kommentieren
- Repo-Dateien auf GitHub lesen
- Branches, Commits und PRs erstellen, wenn der Connector Schreibrechte hat
- GitHub Actions und Remote-CI prüfen

Er ersetzt NICHT:
- lokale Testausführung
- lokale Worktrees oder nicht gepushte Änderungen
- private Audio-Dateien
- Windows-Geräte-/WASAPI-Validierung
- lokale Sample-Library-Evaluation

Wenn eine Definition of Done lokale Evidence verlangt, bleibt das Issue offen oder partial.

## Handoff in eine neue Session

Copy/Paste-Smoke:

```text
Führe zuerst den GPT-MCP-Preflight für jannekbuengener/sample-brain aus.
Prüfe Server-Version/Build, ob der Root `sample_brain` registriert ist, und lies das Root-Verzeichnis.
PASS nur, wenn `SB.BOOTLOADER.md`, `src` und `tests` über den MCP sichtbar sind.
Melde anschließend exakt: local_mcp_available, mcp_server_version, sample_brain_root_registered, sample_brain_read_smoke und blocker.
Wenn die Session Developer-MCP verbietet, nicht behaupten, dass der Server kaputt ist.
```

## Datenschutz

- keine private Sample-Library indexieren
- keine privaten Audio-Pfade in GitHub-Issues oder Reports kopieren
- keine Secrets oder Tokens in Repo-Evidence
- lokale Device-Namen nur dort dokumentieren, wo ein Validation-Issue sie ausdrücklich verlangt
