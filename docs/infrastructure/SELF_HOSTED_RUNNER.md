# Sample-Brain Self-Hosted Runner — Architecture & Rationale

## Zielbild

Sample-Brain erhält einen vollständig eigenständigen, Docker-basierten,
repo-level self-hosted GitHub Actions Runner. Dieser Runner ist die primäre
CI/CD-Ausführungsumgebung für Sample-Brain und umgeht den GitHub-Billing-Lock,
der alle `ubuntu-latest`-Jobs blockiert.

## Warum ein eigener Runner (keine CDB-Abhängigkeit)

### 1. Klare Trennung der Verantwortlichkeiten

CDB (`jannekbuengener/Claire_de_Binare`) und Sample-Brain (`jannekbuengener/sample-brain`)
sind zwei unabhängige Projekte mit unterschiedlichen:

- **Release-Zyklen**: CDB folgt einem strukturierten Merge-Gate-Prozess mit
  `policy-gate` und `merge-gate`-Labels. Sample-Brain hat einfachere CI-Anforderungen.
- **CI-Anforderungen**: CDB benötigt Docker-Zugriff, Policy-Prüfungen und
  Merge-Queue-Orchestrierung. Sample-Brain benötigt Python 3.12 Smoke-Tests.
- **Sicherheitsprofil**: CDB verarbeitet SurrealDB-Daten und verlangt
  Docker-Isolation. Sample-Brain arbeitet mit Audio-Samples und Metadaten.

### 2. Unabhängige Wartbarkeit

- **Updates**: Der Sample-Brain-Runner kann unabhängig von CDB aktualisiert,
  neugestartet oder zurückgesetzt werden.
- **Ausfälle**: Ein CDB-Runner-Problem (z. B. Docker-Engine, Netzwerk, Token-Ablauf)
  blockiert nicht die Sample-Brain-CI.
- **Labels**: Eigene Labels (`sample-brain`, `linux`, `x64`) ohne Kollision
  mit CDB-Labels (`cdb`, `docker`, `merge-gate`).
- **Volumes**: Eigene Docker-Volumes (`sample-brain-runner-state`,
  `sample-brain-runner-work`) ohne Überschneidung.

### 3. Verbesserte Sicherheit

- **Kein Shared Context**: CDB-Secrets, CDB-Konfiguration und CDB-Workdir
  sind für Sample-Brain-Jobs nicht zugänglich.
- **Begrenzte Exposition**: Der Sample-Brain-Runner hat `contents: read`-
  Berechtigung und keine Deployment-Zugriffe.
- **Isolierte Ausführung**: Fork-PRs können den Workflow nicht automatisch
  triggern (nur `workflow_dispatch`).
- **Keine CDB-Labels**: Vermeidet versehentliches Routing von CDB-Jobs auf
  den Sample-Brain-Runner und umgekehrt.

### 4. Zukunftssicherheit & Skalierung

- **Mehrere Runner möglich**: Bei Bedarf können weitere Sample-Brain-Runner
  hinzugefügt werden (z. B. für parallele Jobs, verschiedene Betriebssysteme).
- **Eigene Image-Strategie**: Das Docker-Image kann um Sample-Brain-spezifische
  Abhängigkeiten erweitert werden (librosa, soundfile, ffmpeg), ohne CDB zu
  beeinflussen.
- **Eigener Update-Rhythmus**: Runner-Updates folgen Sample-Brain-Release-Zyklen.

## Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                   Host-System (Docker-Host)                  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Container: sample-brain-runner                       │   │
│  │  Image:   infrastructure/actions-runner/Dockerfile    │   │
│  │  Base:    mcr.microsoft.com/devcontainers/python:3.12 │   │
│  │                                                       │   │
│  │  entrypoint.sh                                        │   │
│  │    ├── restore_state() ← sample-brain-runner-state    │   │
│  │    ├── register_runner() ← RUNNER_TOKEN               │   │
│  │    └── run.sh                                         │   │
│  │                                                       │   │
│  │  Volumes:                                             │   │
│  │    /home/runner/state  → sb-runner-state              │   │
│  │    /home/runner/_work  → sb-runner-work               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Keine Verbindung zu CDB-Containern/-Netzwerken      │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Komponenten

| Komponente | Pfad | Zweck |
|-----------|------|-------|
| Dockerfile | `infrastructure/actions-runner/Dockerfile` | Runner-Image mit Python 3.12 |
| entrypoint.sh | `infrastructure/actions-runner/entrypoint.sh` | Registration & Startup |
| docker-compose.yml | `infrastructure/actions-runner/docker-compose.yml` | Service-Definition |
| .env.example | `infrastructure/actions-runner/.env.example` | Konfigurationsvorlage |
| Workflow | `.github/workflows/ci-smoke-self-hosted.yml` | Smoke-Test-Workflow |

## Betriebskonzept

### Start
```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml up -d --build
```

### Neustart (nach Host-Reboot)
Automatisch via `restart: unless-stopped` in `docker-compose.yml`.

### Update (neues Runner-Release)
```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml down
docker compose -f infrastructure/actions-runner/docker-compose.yml up -d --build
```
Kein neues Token nötig — die State-Volume persistiert die Credentials.

### Update (neues Python-Paket)
```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml down
docker compose -f infrastructure/actions-runner/docker-compose.yml up -d --build
```

### Rollback (fehlerhaftes Update)
```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml down
git revert HEAD~1  # falls Dockerfile geändert wurde
docker compose -f infrastructure/actions-runner/docker-compose.yml up -d --build
```

### Vollständige Deinstallation
```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml down -v
# Runner im GitHub UI entfernen: Settings > Actions > Runners > Remove
```

## Entscheidungen (Architecture Decision Records)

### ADR-001: Docker-basiert statt systemd-Service

**Status:** Akzeptiert  
**Kontext:** Der Runner könnte direkt auf dem Host als systemd-Service
installiert werden (wie in der ersten Version des Runbooks beschrieben).  
**Entscheidung:** Docker-basiert.  
**Begründung:**
- Isolierte Umgebung (Python-Version, Abhängigkeiten kollidieren nicht mit Host).
- Einfacheres Update: Image neu bauen statt Binärdateien tauschen.
- State-Persistence über Volumes statt manuellem Credential-Management.
- Gleiche Architektur wie CDB-Runner (bewährtes Pattern).
- Schnelleres Onboarding: `docker compose up` statt manueller Shell-Skripte.

### ADR-002: eigener Container statt CDB-Runner-Sharing

**Status:** Akzeptiert  
**Kontext:** Der CDB-Runner läuft auf dem Host und könnte theoretisch
Sample-Brain-Jobs annehmen.  
**Entscheidung:** Separater Container, keine CDB-Runner-Sharing.  
**Begründung:** Siehe Abschnitt "Warum ein eigener Runner".

### ADR-003: workflow_dispatch-only

**Status:** Akzeptiert  
**Kontext:** PR #101 definiert den Workflow zunächst mit `workflow_dispatch`.  
**Entscheidung:** Es bleibt bei `workflow_dispatch` — kein `pull_request`- oder
`push`-Trigger.  
**Begründung:**
- Sicherheit: Fork-PRs könnten Code auf dem Runner ausführen.
- Kontrolle: bewusste Dispatch-Entscheidung statt automatischer Trigger.
- Vorsicht: Der Runner läuft zunächst im Validierungsmodus.

## Verwandte Dokumente

- `docs/CI_DEGRADED_MODE.md` — Policy für CI-Ausfall und Runner-Fallback.
- `docs/runbooks/SELF_HOSTED_RUNNER_INSTALL.md` — Operator-Installationsanleitung.
- `docs/runbooks/SAMPLE_BRAIN_SELF_HOSTED_RUNNER.md` — Ursprüngliches Runbook
  (non-Docker-Ansatz, historisch).
- `.github/workflows/ci-smoke-self-hosted.yml` — Zugehöriger Smoke-Workflow.
- `infrastructure/actions-runner/README.md` — Kurzreferenz für den Betrieb.
