# Sample-Brain Self-Hosted Runner — Installationsanleitung (Docker)

## Übersicht

Diese Anleitung beschreibt die Erstinstallation des Docker-basierten
self-hosted GitHub Actions Runners für Sample-Brain.

**Voraussetzungen:**
- Docker Engine 24+ und Docker Compose v2 auf dem Zielhost
- Python 3.12 wird im Container mitgeliefert (kein Host-Python nötig)
- Internetzugriff für GitHub API (api.github.com, github.com)

## Schritt 1: Vorbereitung auf dem Host

```bash
# Docker-Installation prüfen
docker --version && docker compose version

# Repository klonen
git clone https://github.com/jannekbuengener/sample-brain.git
cd sample-brain
```

## Schritt 2: Registrationstoken generieren

Variante A — GitHub UI:
1. repository > Settings > Actions > Runners > New runner
2. Code kopieren (den Token)

Variante B — GitHub CLI:
```bash
gh api \
  -X POST \
  -H "Accept: application/vnd.github+json" \
  /repos/jannekbuengener/sample-brain/actions/runners/registration-token \
  --jq '.token'
```

## Schritt 3: Umgebung konfigurieren

```bash
cp infrastructure/actions-runner/.env.example infrastructure/actions-runner/.env.runner
```

`.env.runner` öffnen und `RUNNER_TOKEN` eintragen:
```ini
RUNNER_TOKEN=<TOKEN_HIER>
```

Optional: `RUNNER_NAME` für einen aussagekräftigen Namen anpassen.

## Schritt 4: Runner starten

```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml up -d --build
```

## Schritt 5: Status prüfen

```bash
# Logs anzeigen
docker compose -f infrastructure/actions-runner/docker-compose.yml logs -f
# Erwartet: "Listening for Jobs"

# Container läuft?
docker ps --filter name=sample-brain-runner

# GitHub-API: Runner sichtbar?
gh api repos/jannekbuengener/sample-brain/actions/runners --jq '.runners[] | select(.name=="sample-brain-runner")'
```

Erwarteter Status: `"status": "online"` und `"busy": false`.

## Schritt 6: Smoke-Validierung

```bash
# Workflow dispatchen (GitHub CLI)
gh workflow run ci-smoke-self-hosted.yml --ref main

# Workflow-Status abfragen
gh run list --workflow ci-smoke-self-hosted.yml --limit 1 --json conclusion,databaseId

# Auf Abschluss warten
gh run watch $(gh run list --workflow ci-smoke-self-hosted.yml --limit 1 --json databaseId --jq '.[0].databaseId')
```

Erwartetes Ergebnis: `conclusion: "success"`.

## Schritt 7: Automatischen Start konfigurieren

Der Container startet automatisch via `restart: unless-stopped` in
`docker-compose.yml`. Zusätzlich kann der Docker-Daemon selbst auf
autostart konfiguriert werden:

```bash
sudo systemctl enable docker
```

## Lifecycle

### Runner pausieren (offline, bleibt registriert)
```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml down
```

### Runner fortsetzen
```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml up -d
```

### Runner aktualisieren (neues Image)
```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml down
docker compose -f infrastructure/actions-runner/docker-compose.yml up -d --build
```
Kein neuer Token nötig (State-Volume).

### Registration erneuern (nach Token-Verlust oder State-Corruption)
```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml down
docker volume rm sample-brain-runner-state
# .env.runner mit neuem Token aktualisieren
docker compose -f infrastructure/actions-runner/docker-compose.yml up -d --build
```

### Runner deinstallieren (dauerhaft)
```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml down -v
# GitHub UI: Settings > Actions > Runners > Remove
```

## Troubleshooting

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| `RUNNER_TOKEN is required` | Token fehlt oder State fehlt | `RUNNER_TOKEN` in `.env.runner` setzen |
| Container startet nicht | Port-Konflikt oder fehlende Rechte | `docker logs sample-brain-runner` prüfen |
| Runner offline nach Neustart | Docker-Daemon nicht aktiv | `sudo systemctl enable docker` |
| `Listening for Jobs` erscheint nicht | Registration fehlgeschlagen | Token-Ablauf prüfen (1h), neuen Token generieren |
| Job bleibt ewig queued | Label-Konflikt oder Workflow falsch | Workflow `runs-on: [self-hosted, sample-brain]` prüfen |
| Runner zeigt `offline` im UI | Container läuft nicht | `docker compose ps` und `logs` prüfen |
| State-Volume korrupt | Dateisystemfehler | State löschen, neu registrieren (siehe oben) |

## Sicherheitshinweise

1. **Token-Geheimhaltung**: `RUNNER_TOKEN` hat Schreibzugriff auf das Repository.
   Niemals in Workflows, Logs oder Commits preisgeben.
2. **Kein pull_request-Trigger**: Der Workflow ist auf `workflow_dispatch`
   beschränkt. Fork-PRs können keinen Code auf dem Runner ausführen.
3. **Minimale Berechtigungen**: `contents: read` im Workflow ist ausreichend.
4. **Isolation**: Der Container hat keine Netzwerkverbindung zu CDB-Containern.
5. **Updates**: Regelmässige Updates des Runner-Images und der Dependencies.
6. **Monitoring**: Runner-Status regelmässig via GitHub API oder UI prüfen.
