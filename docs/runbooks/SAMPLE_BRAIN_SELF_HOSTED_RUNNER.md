# Sample-Brain Self-Hosted Runner – Operator Runbook

## Zielbild

Sample-Brain benötigt einen eigenständigen repo-level self-hosted GitHub Actions Runner als Fallback, weil GitHub-hosted Runner (`ubuntu-latest`) durch einen Billing-Lock blockiert sind.

Der Runner darf physisch auf demselben Host wie die CDB-Runner laufen, muss aber **logisch vollständig eigenständig** sein:
- separate Runner-Instanz (eigener Service)
- eigenes Workdir
- eigene Config
- eigene Labels
- kein Zugriff auf CDB-Secrets, CDB-Workdir oder CDB-Konfiguration

## Registration

| Feld | Wert |
|------|------|
| **Repo** | `jannekbuengener/sample-brain` |
| **Scope** | repo-level |
| **Labels** | `self-hosted`, `sample-brain` |
| **Nicht verwenden** | `cdb`, `docker`, `merge-gate` |
| **Ephemeral** | nein (persistent) |
| **Workdir** | eigenes Verzeichnis (z.B. `/home/runner/sample-brain/_work`) |

## Installationsschritte (auf dem Host)

```bash
# 1. Zum Runner-Host verbinden (z.B. SSH)
# 2. GitHub Token vorbereiten: Personal Access Token mit repo:write Scope
# 3. Registrationstoken für das Repo abrufen
#    (geht auch via UI unter: Settings > Actions > Runners > New runner)
# 4. Runner-Verzeichnis anlegen
mkdir -p /home/runner/sample-brain
cd /home/runner/sample-brain

# 5. GitHub Runner herunterladen (Version anpassen)
curl -o actions-runner-linux-x64-2.323.0.tar.gz \
  -L https://github.com/actions/runner/releases/download/v2.323.0/actions-runner-linux-x64-2.323.0.tar.gz
tar xzf actions-runner-linux-x64-2.323.0.tar.gz

# 6. Runner konfigurieren
#    Registrationstoken via UI oder API generieren
./config.sh \
  --url https://github.com/jannekbuengener/sample-brain \
  --token <REGISTRATION_TOKEN> \
  --labels self-hosted,sample-brain \
  --name sample-brain-runner \
  --work _work \
  --unattended

# 7. Als Service installieren
sudo ./svc.sh install
sudo ./svc.sh start

# 8. Status prüfen
sudo ./svc.sh status
```

## Labels – Übersicht

Selbst gesetzt (via `--labels`):

| Label | Zweck |
|-------|-------|
| `self-hosted` | Standard-GitHub-Label, markiert als eigener Runner |
| `sample-brain` | Eindeutige Identifikation für Sample-Brain-Jobs |

Von GitHub automatisch gesetzt (via `config.sh`):

| Label | Zweck |
|-------|-------|
| `Linux` | Betriebssystem |
| `X64` | Architektur |

**Ausdrücklich NICHT gesetzt:**
- `cdb` – gehört zur CDB-Runner-Gruppe
- `docker` – wird von Sample-Brain nicht benötigt
- `merge-gate` – gehört zur CDB-Runner-Gruppe

## Workflow-Konfiguration

Der zugehörige Workflow ist in `.github/workflows/ci-smoke-self-hosted.yml` definiert:

```yaml
runs-on: [self-hosted, sample-brain]
```

Der Workflow wird ausschliesslich per `workflow_dispatch` ausgelöst:
- GitHub UI: Actions > "Python smoke (self-hosted)" > "Run workflow"
- CLI: `gh workflow run ci-smoke-self-hosted.yml --ref main`

## Validierung

Nach der Runner-Registration:

```bash
# Prüfen, ob der Runner im Repo sichtbar ist
gh api repos/jannekbuengener/sample-brain/actions/runners

# Workflow manuell dispatchen (via GitHub UI oder CLI)
gh workflow run ci-smoke-self-hosted.yml --ref main

# Ergebnis prüfen
gh run list --workflow ci-smoke-self-hosted.yml --limit 1
```

Erwartetes Ergebnis bei Erfolg:
- Runner wird zugewiesen
- Checkout erfolgreich
- `python --version` zeigt installierte Version
- `pip install -r requirements.txt` erfolgreich
- `py_compile` erfolgreich
- `--help` erfolgreich

## Rollback

Falls der Runner entfernt werden muss:

```bash
# Service stoppen und deinstallieren
sudo ./svc.sh stop
sudo ./svc.sh uninstall

# Registration entfernen (via Service oder manuell)
./config.sh remove --token <REGISTRATION_TOKEN>
```

Zusätzlich im GitHub UI: Settings > Actions > Runners > Runner löschen.

## Sicherheitshinweise

- **Kein `pull_request`-Trigger** für self-hosted Workflows, solange Security-Äquivalenz nicht nachgewiesen ist
- **Keine Secrets** im Workflow – Sample-Brain braucht keine für `pip install` / `py_compile` / `--help`
- **`contents: read`** ist ausreichend
- Der Runner läuft auf einer **public repo** Umgebung – Fork-PRs könnten Code ausführen, wenn `pull_request` aktiviert würde
- **Kein gemeinsames Workdir** mit CDB-Runnern – zwei separate Verzeichnisse

## Fehlerbehebung

| Symptom | Mögliche Ursache | Lösung |
|---------|-----------------|--------|
| Runner nicht online | Service nicht gestartet | `sudo ./svc.sh status` und `start` |
| Job bleibt ewig queued | Labels passen nicht | Workflow YAML prüfen: `runs-on: [self-hosted, sample-brain]` |
| Runner offline nach Neustart | Service nicht enabled | `sudo systemctl enable actions.runner.*.service` |
| `pip install` schlägt fehl | Python nicht installiert | `apt install python3 python3-pip python3-venv` |
| `py_compile` Fehler | Python-Version ≠ 3.12 | `.python-version` prüfen |
