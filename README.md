**AI-powered sample management for FL Studio**  
Scan → Analyze → Tag → Export. Stay in your flow.  

---

## 🎨 UI Mockup

![sample-brain UI](./ui_mockup.png)

---

## 🚀 Features (MVP)

- **Scan**: build a database from your sample library  
- **Analyze**: extract audio features (BPM, key, loudness, brightness, MFCCs, chroma …)  
- **Autotype**: automatic categorization (Kick, Snare, Pad, Drone, Impact …)  
- **Export**: write smart tags into the **FL Studio Browser**  

---

## 🛠️ Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
. .venv\Scripts\activate
# Activate (macOS/Linux)
# source .venv/bin/activate

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

# Export tags to FL Studio
python -m src.cli export_fl "C:\Users\DEINNAME\Documents\Image-Line"   # Windows
python -m src.cli export_fl "~/Documents/Image-Line"               # macOS/Linux
```

---

## 📚 Documentation

### Architecture & Requirements

- [Product Requirements](./docs/PRODUCT_REQUIREMENTS.md) — vision, audience, problem, MVP scope
- [System Requirements](./docs/SYSTEM_REQUIREMENTS.md) — functional and non-functional requirements, constraints
- [Target Architecture](./docs/TARGET_ARCHITECTURE.md) — current and target pipeline, component boundaries, data flow
- [Data and Artifact Policy](./docs/DATA_AND_ARTIFACT_POLICY.md) — what is committed vs untracked

### EPIC Specs

- [EPIC 2: Semantic Search Foundation](./docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md) — embedding, indexing, search contracts and milestones
- [DAW Integration](./docs/DAW_INTEGRATION_SPEC.md) — FL Studio export, Ableton/Reaper research

### Project

- [Issue Backlog](./docs/ISSUE_BACKLOG.md) — planned work across all epics
- [Project Structure](./STRUCTURE.md)  
- [Docs folder](./docs/README.md) (setup, roadmap, details)

---

## ⚖️ License

MIT License – free to use, hack and share.  
Dependencies: see [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md).  

---

🎧 **Your sound. Your flow.**
