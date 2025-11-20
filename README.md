**AI-powered sample management - DAW-neutral**
Scan → Analyze → Tag. Stay in your flow.  

---

## 🎨 UI Mockup

![sample-brain UI](./ui_mockup.png)

---

## 🚀 Features

### Core Pipeline
- **Scan**: build a database from your sample library
- **Analyze**: extract audio features (BPM, key, loudness, brightness, MFCCs, chroma …)
- **Autotype**: automatic categorization (Kick, Snare, Pad, Drone, Impact …)
- **Metadata**: DAW-neutral tag generation for universal sample management

### Export & Integration
- **Multi-Format Export**: JSON, CSV, YAML, XML, Parquet
- **Streaming Export**: Memory-efficient processing for large libraries (10k+ samples)
- **DAW Adapters**: Ableton Live Collection, Bitwig Studio formats
- **SQLite Views**: Pre-built analytical views for quick queries  

---

## 🛠️ Setup

```bash
# Create virtual environment
python -m venv .venv
. .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 🏃 Quickstart

```bash
# Initialize DB
python -m src.cli init

# Scan sample folder (default in config.py)
python -m src.cli scan

# Analyze audio features
python -m src.cli analyze

# Autotype samples (rules only)
python -m src.cli autotype --no-knn

# Export metadata (DAW-neutral)
python -m src.cli export --format json  # json, csv, yaml, xml, parquet

# Export for specific DAWs
python -m src.cli export-daw ableton     # Ableton Live Collection
python -m src.cli export-daw bitwig      # Bitwig Studio

# Streaming export for large libraries
python -m src.cli export --format csv --streaming --chunk-size 1000

# Create SQLite analytical views
python -m src.cli create-views --export-schema
```

---

## 📚 Documentation

- [Project Structure](./STRUCTURE.md)  
- [Docs folder](./docs/README.md) (setup, roadmap, details)  

---

## ⚖️ License

MIT License – free to use, hack and share.  
Dependencies: see [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md).  

---

🎧 **Your sound. Your flow.**<Inhalt der README.md Datei hier einfügen>
