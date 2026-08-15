# Track Analysis Cache v1 — Reusable Track Analysis Results

**Issue:** [#237](https://github.com/jannekbuengener/sample-brain/issues/237)
**Parent:** [#227](https://github.com/jannekbuengener/sample-brain/issues/227)
**Depends on:** [#232](https://github.com/jannekbuengener/sample-brain/issues/232) (Track Map v1 contract)
**Status on issue tracker:** `OPEN`
**Schema version:** `1.0.0`
**Document type:** `sample_brain.track_analysis_cache_entry`

This document defines a small, specialized, **local, regenerable** cache for
expensive Track-Analyse-Ergebnisse (BPM, Key, Loudness, Brightness). It is **not**
a global cache framework, **not** a SQLite cache, **not** a cloud cache, and
introduces **no new dependency**.

The cache makes the Track-Analyse wiederverwendbar: derselbe Track (identifiziert
über Audioinhalt, Analyseversion, Backend und relevante Konfiguration) wird nicht
erneut teuer analysiert, wenn das vorhandene Ergebnis nachweislich noch gültig ist.

---

## 1. Purpose & Scope Boundaries

| Aspect | Rule |
|--------|------|
| **Lokal** | Cache lebt user-lokal, per Default außerhalb des Repos. |
| **Regenerierbar** | Jeder Eintrag kann jederzeit neu berechnet werden. Kein Source-of-Truth. |
| **Kein fachlicher Source-of-Truth** | Originalaudio, Track-Map-Vertrag und tatsächlich verwendete Analysekonfiguration sind authoritative. Der Cache ist nur ein Optimierungs-Artefakt. |
| **Kein globales Framework** | Nur dieser eine spezialisierte Track-Analyse-Cache. |
| **Keine SQLite** | Reine Datei-basierte JSON-Cache-Einträge. |
| **Keine Cloud** | Kein Netzwerk-Zugriff. |
| **Keine neue Dependency** | Nur stdlib + bereits vorhandene Runtime. |

### 1.1 Abgrenzung zu #262 (Pack Resume / Cache)

#262 besitzt **pack-lokales** Resume für Deconstruction. #237 darf diesen
Mechanismus **nicht** nachbauen. Die Reihenfolge bei Deconstruction ist:

1. **#262 prüft zuerst**, ob der komplette Track-Map-Step im selben Pack
   wiederverwendbar ist (`execution: reused | computed`).
2. **Nur wenn der Track-Map-Step tatsächlich neu ausgeführt werden muss**
   (kein #262-Pack-Hit), darf #237 den allgemeinen Track-Analyse-Cache prüfen.
3. Cache-Hit → Analysewerte wiederverwenden.
4. Cache-Miss → normal analysieren und Cache schreiben.

Ein gültiger Zustand ist also z. B.:

```text
execution = computed          (aus #262: Step lief neu)
track_analysis_cache_status = hit   (aus #237: Analysewerte kamen aus dem Cache)
```

Die beiden Statusfelder sind bewusst getrennt: `execution` beschreibt, *ob der
Step lief*; `track_analysis_cache_status` beschreibt, *wie die Analysewerte
beschafft wurden*.

---

## 2. Cache Location

| Platform | Default (user-lokal, außerhalb Repo) |
|----------|---------------------------------------|
| Windows | `%LOCALAPPDATA%/sample-brain/track-analysis` |
| Unix | `${XDG_CACHE_HOME:-~/.cache}/sample-brain/track-analysis` |

| Override | Variable / Flag |
|----------|-----------------|
| Environment | `SAMPLE_BRAIN_TRACK_CACHE_DIR` |
| CLI (Context Analyze) | `--track-cache-dir <path>` |
| CLI (Deconstruct) | `--track-cache-dir <path>` |
| Disable (Context Analyze) | `--no-track-cache` |
| Disable (Deconstruct) | `--no-track-cache` |

**CLI-Override hat Vorrang vor Environment, welches Vorrang vor dem Platform-Default hat.**

**Hard Rule (Privacy):** Der lokale Cache-Pfad selbst darf niemals in Track Map,
Pack Manifest, `deconstruct_run.json` oder anderen portablen Artefakten
serialisiert werden. Nur der `track_analysis_cache_status` (`hit`/`miss`/`disabled`)
wird als Evidence geführt — niemals ein Pfad.

---

## 3. Cache Key

Der Cache-Key ist ein **SHA-256** über ein **kanonisches deterministisches JSON**.

### 3.1 Kanonisierung

| Regel | Wert |
|-------|------|
| `sort_keys` | `true` |
| Trenner | stabil (`separators=(",", ":")`) |
| Timestamps | keine |
| Absolute Pfade | keine |
| trailing whitespace / unicode escaping | `json.dumps(..., ensure_ascii=False, allow_nan=False)` |

### 3.2 Required Key Inputs

| Input | Beschreibung |
|-------|--------------|
| `source_content_hash` | Autoritative Content-Identity des Originalaudios (derzeit SHA-1, aus `canon_audio.content_hash`). |
| `component` | Konstant `"analyze"`. |
| `contract_version` | `TRACK_ANALYSIS_CACHE_CONTRACT_VERSION` (derzeit `2`). |
| `sample_brain_version` | Analyseversion von sample-brain (`metadata.version("sample-brain")`). |
| `backend.name` | `"librosa"` (der aktuelle Context Analyzer verwendet librosa). |
| `backend.version` | Installierte librosa-Version. |
| `config` | Relevante Analyzer-Konfiguration (siehe 3.3). |
| `model_identity` | Optional (siehe 3.4). `null` wenn kein ML-Modell verwendet wird. |

### 3.3 Relevante Analyzer-Konfiguration (`config`)

Nur Werte, die das Analyseergebnis fachlich bestimmen:

| Key | Quelle |
|-----|--------|
| `bpm_normalization` | Aufrufparameter (`none` / `heuristic`). |
| `canonical_sample_rate_hz` | `canon_audio.CANONICAL_SAMPLE_RATE` (44100). |
| `canonical_channels` | `canon_audio.CANONICAL_CHANNELS` (1). |
| `analyze_sr` | `config.ANALYZE_SR`. |
| `analyze_hop_length` | `config.ANALYZE_HOP_LENGTH`. |

**Nicht** pauschal gefingerprintet werden indirekte Dependencies wie `numpy` /
`scipy`. Diese werden nur ergänzt, wenn nachweislich eine davon die
Ergebnissemantik bestimmt.

### 3.4 Optionale Modellidentität

Der aktuelle Context Analyzer verwendet **kein** separates ML-Modell. Deshalb
wird **kein** erfundenes Modell eingetragen (`model_identity = null`).

Der Fingerprint-Code unterstützt jedoch eine optionale Modellidentität
(`{"name", "version", "revision", "hash"}`), damit ein späterer Analysebaustein
mit Modellname/Version/Revision/Hash korrekt invalidieren kann.

### 3.5 Contract-Version-Konstante

```python
TRACK_ANALYSIS_CACHE_CONTRACT_VERSION = 2
```

`contract_version` `1 → 2` was bumped for issue #212: the analysis fingerprint now
also includes `key_analysis_contract_version` (from `src.analyze
.KEY_ANALYSIS_CONTRACT_VERSION`, currently `1`), so a change in the Dur/Moll mode
analysis invalidates prior caches.

---

## 4. Cache Entry Schema

| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| `document_type` | string | ja | `"sample_brain.track_analysis_cache_entry"`. |
| `schema_version` | string | ja | `"1.0.0"`. |
| `cache_key` | string | ja | SHA-256-Key (Section 3). |
| `source_content_hash` | object | ja | `{"algorithm": "sha1", "value": "..."}`. |
| `analysis_fingerprint` | string | ja | SHA-256 der Analyse-Methoden-Identität (Section 5). |
| `track_map` | object | ja | Die wiederverwendbaren Analyseblöcke (Section 6). |
| `provenance_component` | object | ja | Der `analyze`-Provenance-Eintrag (Section 7). |
| `quality` | object | ja | Der `quality`-Block der Track Map. |

### 4.1 Dateiname

Der Cache-Eintrag wird als `<cache_dir>/<cache_key>.json` gespeichert. Der
`cache_key` ist also sowohl Inhalt als auch Dateiname (atomare Ablage, siehe 8).

### 4.2 MUST NOT store

| Verboten | Grund |
|----------|-------|
| absoluter Quellpfad | Privacy / Portabilität. |
| Cache-Root-Pfad | Privacy / Portabilität. |
| privater Library-Pfad | Privacy. |
| Model-Cache-Pfad | Privacy. |
| SQLite-IDs | Kein DB-Coupling. |
| temporäres canonical WAV | Nur Arbeitsartefakt. |

---

## 5. Analysis Fingerprint (Parameter Fingerprint)

`analysis_fingerprint` ist ein deterministischer **SHA-256** über die effektiven
Analyzer-Parameter und die Analyseidentität — **ohne** Quell-Content-Hash.

Er wird an zwei Stellen verwendet:

1. **Im Cache-Entry** (`analysis_fingerprint`) zur Validierung beim Lesen.
2. **In der Track Map Provenance** als
   `provenance.components["analyze"].configuration.parameter_fingerprint`
   (siehe `docs/TRACK_MAP_V1.md` Section 8).

Beide Werte MÜSSEN identisch sein für dieselbe Analyse-Konfiguration.

---

## 6. Wiederverwendbare Analyseblöcke (Identity Rule)

Die gecachte Analyse darf **NICHT** blind den alten Dateinamen übernehmen.
Derselbe Audioinhalt kann unter einem anderen Dateinamen vorliegen.

Bei einem **Cache-Hit**:

1. Aktuelle Quelldatei erneut billig identifizieren/proben (`file_name`,
   `size_bytes`, `audio_properties`, `context_source`-Block).
2. Die **teuren ANALYSEWERTE** (BPM, Key, Loudness, Brightness) aus dem Cache
   wiederverwenden.
3. Track Map zeigt den **aktuellen** Dateinamen und die aktuellen
   Datei-Eigenschaften.

So bleibt die Track Map für den aktuell analysierten Pfad korrekt, ohne private
Pfade im Cache zu speichern.

---

## 7. Provenance Component

Der Cache-Entry speichert den `analyze`-Provenance-Eintrag der ursprünglichen
Analyse (inklusive `parameter_fingerprint`). Bei einem Hit wird dieser
unverändert in die aktuelle Track Map übernommen; nur der `context_source`-
Block (Dateiname, Größe, Audio-Properties) wird frisch bestimmt.

---

## 8. Atomic Writes

Jeder Cache-Write ist atomar:

1. Temp-Datei im **selben** Cache-Verzeichnis erzeugen.
2. Inhalt schreiben + `flush()` + `os.fsync()` (best effort).
3. `os.replace(temp_path, final_path)` — atomarer Rename.

Ein halbgeschriebener Entry wird niemals als `hit` akzeptiert.

---

## 9. Cache Validation (on read)

Beim Lesen wird geprüft:

| Check | Bei Fehler |
|-------|------------|
| JSON parsbar | MISS |
| `document_type` korrekt | MISS |
| unterstützte `schema_version` major | MISS |
| `cache_key` stimmt mit neu berechnetem Key überein | MISS |
| `source_content_hash` stimmt mit aktuellem Audio überein | MISS |
| `analysis_fingerprint` stimmt mit aktueller Analyseidentität überein | MISS |
| erwartete Blöcke (`track_map`, `provenance_component`, `quality`) vorhanden | MISS |

**Corrupt Entry:** Cache-MISS + sichere Neuberechnung. Kein Crash, niemals
Fake-Hit. Der korrupte Eintrag wird überschrieben mit einem validen Resultat.

---

## 10. Invalidation Matrix

| Szenario | Erwartung |
|----------|-----------|
| Gleicher Audioinhalt, gleiche Analyse | **HIT** |
| Gleicher Audioinhalt, anderer Dateiname | **HIT** für Analysewerte; Track Map zeigt aktuellen Dateinamen |
| Audioinhalt geändert | **MISS** |
| `bpm_normalization` geändert | **MISS** |
| Backend-Version geändert | **MISS** |
| sample-brain Analyseversion geändert | **MISS** |
| Cache-Contract-Version geändert | **MISS** |
| Optionale Modellidentität geändert | **MISS** |
| Kaputter Cache-Eintrag | **MISS** + Überschreiben mit validem Resultat |
| Gelöschter Cache | **MISS** + normale Regeneration |

---

## 11. Deconstruct Integration

Der Track-Map-Step im Deconstruct-Orchestrator nutzt denselben globalen
User-Cache (nicht pack-lokal). Wenn der Step wegen #262 tatsächlich gerechnet
wird, führt seine Step-Evidence zusätzlich:

```text
track_analysis_cache_status: hit | miss | disabled
```

Dies ist **additive** Step-Evidence, getrennt von #262
`execution = reused | computed`.

---

## 12. API

### 12.1 Rückwärtskompatibilität

`analyze_context_file(path, *, bpm_normalization="none")` bleibt unverändert
rückwärtskompatibel (kein Cache-Zugriff).

### 12.2 Neue Funktion

```python
TrackAnalysisCacheResult = analyze_context_file_cached(
    path,
    *,
    bpm_normalization="none",
    cache_dir=None,        # explizit; sonst Platform-Default / Env
    enabled=True,          # --no-track-cache setzt dies auf False
)

# TrackAnalysisCacheResult enthält:
#   track_map: dict        # vollständige Track Map v1
#   cache_status: str      # "hit" | "miss" | "disabled"
#   cache_key: str | None  # None wenn disabled
```

### 12.3 Cache-Status-Evidence

`cache_status` ist **Ausführungsevidence**, nicht Musik-/Analyseinhalt. Er wird
**NICHT** in die portable Track Map geschrieben (sonst erzeugen identische
Analysen unterschiedliche fachliche Track Maps).

---

## 13. Related Documents

| Document | Rolle |
|----------|-------|
| [`docs/TRACK_MAP_V1.md`](TRACK_MAP_V1.md) | Track Map v1 Vertrag (Provenance, `parameter_fingerprint`). |
| [`docs/CONTEXT_ANALYZE.md`](CONTEXT_ANALYZE.md) | One-shot Context Analyze CLI. |
| [`docs/TRACK_DECONSTRUCTION_ORCHESTRATOR_V1.md`](TRACK_DECONSTRUCTION_ORCHESTRATOR_V1.md) | Deconstruct Step-Evidence, `#262`-Abgrenzung. |
| [Issue #227](https://github.com/jannekbuengener/sample-brain/issues/227) | Meta: Track Intelligence & Track Map. |
| [Issue #232](https://github.com/jannekbuengener/sample-brain/issues/232) | Track Map v1 Vertrag. |
| [Issue #237](https://github.com/jannekbuengener/sample-brain/issues/237) | Dieses Cache-Issue. |
| [Issue #262](https://github.com/jannekbuengener/sample-brain/issues/262) | Pack-lokales Resume (getrennt). |

---

## 14. Implementation Status

| Component | Status | Datei |
|-----------|--------|-------|
| Cache-Modul | Implementiert | `src/track_analysis_cache.py` |
| Context Analyze Integration | Implementiert | `src/context_analyze.py` (`analyze_context_file_cached`) |
| Deconstruct Step-Evidence | Implementiert | `src/deconstruct.py` |
| CLI-Steuerung | Implementiert | `src/cli.py` (`--track-cache-dir`, `--no-track-cache`) |
| Tests (synthetisch) | Implementiert | `tests/test_track_analysis_cache.py` |
