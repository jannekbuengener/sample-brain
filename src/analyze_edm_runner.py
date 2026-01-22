# src/analyze_edm_runner.py
"""
Runner for EDM-optimized analysis.
Integrates EDM features into database.
"""
from pathlib import Path
from sqlalchemy import text
from tqdm import tqdm
from .db import init_db
from .analyze_edm import analyze_edm_features
from .db_edm import add_edm_columns


def run_analyze_edm():
    """
    Run EDM-optimized analysis on all samples.
    """
    # Ensure EDM columns exist
    add_edm_columns()

    engine = init_db()

    # Get all samples
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT id, path FROM samples ORDER BY id
        """)).fetchall()

    print(f"[EDM] Analyzing {len(rows)} samples with enhanced precision...")

    for sample_id, path in tqdm(rows, desc="EDM Analysis"):
        try:
            # Run EDM analysis
            features = analyze_edm_features(Path(path))

            if "error" in features:
                continue

            # Update database with EDM features
            with engine.begin() as conn:
                # Check if feature row exists
                existing = conn.execute(
                    text("SELECT sample_id FROM features WHERE sample_id = :sid"),
                    dict(sid=sample_id)
                ).fetchone()

                if existing:
                    # Update existing row
                    conn.execute(text("""
                        UPDATE features SET
                            bpm = :bpm,
                            bpm_confidence = :bpm_conf,
                            key = :key,
                            key_conf = :key_conf,
                            camelot = :camelot,
                            sub_bass_energy = :sub_bass,
                            bass_energy = :bass,
                            mid_energy = :mid,
                            high_energy = :high,
                            energy_score = :energy_score,
                            transient_density = :trans_density,
                            dynamic_range = :dyn_range,
                            loudness = :loudness
                        WHERE sample_id = :sid
                    """), dict(
                        sid=sample_id,
                        bpm=features.get("bpm"),
                        bpm_conf=features.get("bpm_confidence"),
                        key=features.get("key"),
                        key_conf=features.get("key_confidence"),
                        camelot=features.get("camelot"),
                        sub_bass=features.get("frequency_bands", {}).get("sub_bass"),
                        bass=features.get("frequency_bands", {}).get("bass"),
                        mid=features.get("frequency_bands", {}).get("mid"),
                        high=features.get("frequency_bands", {}).get("high"),
                        energy_score=features.get("energy", {}).get("energy_score"),
                        trans_density=features.get("transients", {}).get("transient_density"),
                        dyn_range=features.get("energy", {}).get("dynamic_range"),
                        loudness=features.get("energy", {}).get("rms_mean")
                    ))
                else:
                    # Insert new row
                    conn.execute(text("""
                        INSERT INTO features (
                            sample_id, bpm, bpm_confidence, key, key_conf, camelot,
                            sub_bass_energy, bass_energy, mid_energy, high_energy,
                            energy_score, transient_density, dynamic_range, loudness
                        ) VALUES (
                            :sid, :bpm, :bpm_conf, :key, :key_conf, :camelot,
                            :sub_bass, :bass, :mid, :high,
                            :energy_score, :trans_density, :dyn_range, :loudness
                        )
                    """), dict(
                        sid=sample_id,
                        bpm=features.get("bpm"),
                        bpm_conf=features.get("bpm_confidence"),
                        key=features.get("key"),
                        key_conf=features.get("key_confidence"),
                        camelot=features.get("camelot"),
                        sub_bass=features.get("frequency_bands", {}).get("sub_bass"),
                        bass=features.get("frequency_bands", {}).get("bass"),
                        mid=features.get("frequency_bands", {}).get("mid"),
                        high=features.get("frequency_bands", {}).get("high"),
                        energy_score=features.get("energy", {}).get("energy_score"),
                        trans_density=features.get("transients", {}).get("transient_density"),
                        dyn_range=features.get("energy", {}).get("dynamic_range"),
                        loudness=features.get("energy", {}).get("rms_mean")
                    ))

        except Exception as e:
            print(f"\n[ERROR] Failed to analyze {path}: {e}")
            continue

    print(f"\n[EDM] Analysis complete. Enhanced features saved to database.")
    print(f"[EDM] Camelot keys, energy scores, and frequency bands available.")
