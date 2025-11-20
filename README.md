**AI-powered sample management - DAW-neutral**
Scan → Analyze → Tag. Stay in your flow.  

---

## 🎨 UI Mockup

![sample-brain UI](./ui_mockup.png)

---

## 🚀 Features (MVP)

- **Scan**: build a database from your sample library
- **Analyze**: extract audio features (BPM, key, loudness, brightness, MFCCs, chroma …)
- **Autotype**: automatic categorization (Kick, Snare, Pad, Drone, Impact …)
- **Metadata**: DAW-neutral tag generation for universal sample management  

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
