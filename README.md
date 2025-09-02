<<<<<<< HEAD
# sample-brain
AI-gestütztes Sample-Management-System für Musikproduktion. Scannt große Sample-Libraries, analysiert Audioinhalte (BPM, Key, Timbre), klassifiziert automatisch Kategorien und exportiert Tags für den FL-Studio-Browser. Ziel: schnelleres Finden, kreativeres Arbeiten, weniger manuelles Sortieren.
=======
# 🎶 sample-brain [english]

**AI-powered sample management for FL Studio**  
Your custom-made alternative to Sononym.  
Scan → Analyze → Tag → Export. All in your flow.

---

## 🚀 Features (MVP)

- **Scan**: crawls your entire sample library and stores metadata in a SQLite database.  
- **Analyze**: extracts audio features with [librosa](https://librosa.org/)  
  (BPM, key, loudness, brightness, MFCCs, chroma, oneshot vs. loop).  
- **Autotype**: automatic categorization via rules & optional kNN/Seeds  
  (Kick, Snare, HiHat, Drone, Impact, Loop …).  
- **Export**: writes tags directly into the **FL Studio Browser** (`Browser/Tags`).  
- **Embeddings & Search (optional)**: OpenL3 + FAISS for similarity search.  
  → *“Find the sound that sounds like …”*  

---

## 🛠️ Setup

```bash
# Virtual environment
python -m venv .venv
.\.venv\Scripts\activate   # Windows
source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt


🏃 Quickstart

Init DB

python -m src.cli init


➝ creates ./data/catalog.db

Scan samples

python -m src.cli scan "D:\PRODUCING"


Analyze features

python -m src.cli analyze


Autotype

python -m src.cli autotype --no-knn


Export FL Studio tags

python -m src.cli export_fl "C:\Users\YOURNAME\Documents\Image-Line"

🔮 Roadmap

Phase 1 (now): Core engine (scan, analyze, tagging, export).

Phase 2: Duplicate detection, improved search (synonyms, filters).

Phase 3: GUI (Web/Desktop) with waveform preview & filter panels.

Phase 4: AI-powered training data generation.

Phase 5: Live integration / VST connection.

📂 Project Structure
sample-brain/
│── src/
│   ├── cli.py          # CLI with argparse
│   ├── scan.py         # File scanning, hashing & metadata
│   ├── analyze.py      # Feature extraction with librosa
│   ├── classify.py     # Rule-based & kNN classification
│   ├── export_fl.py    # Tag export for FL Studio Browser
│   ├── db.py           # SQLite setup
│   └── config.py       # Paths & settings
│── data/               # SQLite DB, seeds, logs
│── requirements.txt
│── README.md
│── LICENSE
│── THIRD_PARTY_LICENSES.md

⚖️ License

Project: MIT License → full freedom.

Dependencies: MIT / BSD / ISC → see THIRD_PARTY_LICENSES.md
.

🎧 With sample-brain you’ll never have to click through endless sample folders again.
Your sound. Your structure. Your flow.



---------



# 🎶 sample-brain [deutsch]

**KI-gestütztes Sample-Management für FL Studio**  
Deine eigene, maßgeschneiderte Alternative zu Sononym.  
Scannen → Analysieren → Taggen → Exportieren. Alles in deinem Flow.

---

## 🚀 Features (MVP)

- **Scan**: durchsucht deine komplette Sample-Library und legt eine SQLite-DB an.
- **Analyze**: berechnet Audio-Features mit [librosa](https://librosa.org/)  
  (BPM, Key, Loudness, Brightness, MFCCs, Chromas, Oneshot vs. Loop).
- **Autotype**: automatische Kategorisierung per Regeln & optional kNN/Seeds  
  (Kick, Snare, HiHat, Drone, Impact, Loop …).
- **Export**: schreibt Tags direkt in den **FL Studio Browser** (`Browser/Tags`).
- **Embeddings & Search (optional)**: OpenL3 + FAISS für Ähnlichkeitssuche.  
  → „Finde den Sound, der klingt wie …“.

---

## 🛠️ Setup

```bash
# Virtuelle Umgebung
python -m venv .venv
.\.venv\Scripts\activate   # Windows
source .venv/bin/activate  # macOS/Linux

# Dependencies installieren
pip install -r requirements.txt

🏃 Quickstart

Init DB

python -m src.cli init


➝ legt ./data/catalog.db an.

Samples scannen

python -m src.cli scan "D:\PRODUCING"


Features analysieren

python -m src.cli analyze


Autotypisierung

python -m src.cli autotype --no-knn


FL Studio Tags exportieren

python -m src.cli export_fl "C:\Users\DEINNAME\Documents\Image-Line"

🔮 Roadmap

Phase 1 (jetzt): Core-Engine (Scan, Analyze, Tagging, Export).

Phase 2: Duplicate Detection, verbesserte Suche (Synonyme, Filter).

Phase 3: GUI (Web/Desktop) mit Waveform-Preview & Filterpanels.

Phase 4: KI-gestützte Trainingsdaten-Generierung.

Phase 5: Live-Integration / VST-Anbindung.

📂 Projektstruktur
sample-brain/
│── src/
│   ├── cli.py          # CLI mit Typer
│   ├── scan.py         # Files einlesen, Hashes & Basis-Metadaten
│   ├── analyze.py      # Feature Extraction mit librosa
│   ├── classify.py     # Regelbasierte & kNN-Klassifikation
│   ├── export_fl.py    # Tags für FL Studio Browser
│   ├── db.py           # SQLite-Setup
│   └── config.py       # Pfade & Settings
│── data/               # SQLite DB, Seeds, Logs
│── requirements.txt
│── README.md
│── LICENSE
│── THIRD_PARTY_LICENSES.md

⚖️ License

Eigenes Projekt: MIT License → maximale Freiheit.

Dependencies: MIT / BSD / ISC → siehe THIRD_PARTY_LICENSES.md
.

🎧 Mit sample-brain musst du nie wieder durch unendliche Sample-Ordner klicken.
Dein Sound. Deine Struktur. Dein Flow.
>>>>>>> a0734a6 (Initial commit with full project)
