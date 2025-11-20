# src/db_edm.py
"""
Database schema extensions for EDM features.
"""
from sqlalchemy import text
from .db import init_db


def add_edm_columns():
    """
    Add EDM-specific columns to features table.
    """
    engine = init_db()

    edm_columns = [
        ("bpm_confidence", "REAL"),
        ("camelot", "TEXT"),
        ("sub_bass_energy", "REAL"),
        ("bass_energy", "REAL"),
        ("mid_energy", "REAL"),
        ("high_energy", "REAL"),
        ("energy_score", "REAL"),
        ("transient_density", "REAL"),
        ("dynamic_range", "REAL"),
    ]

    with engine.begin() as conn:
        # Check existing columns
        cols = conn.execute(text("PRAGMA table_info(features)")).fetchall()
        existing_cols = {c[1] for c in cols}

        # Add missing EDM columns
        for col_name, col_type in edm_columns:
            if col_name not in existing_cols:
                try:
                    conn.execute(text(f"ALTER TABLE features ADD COLUMN {col_name} {col_type}"))
                    print(f"[DB] Added column: {col_name}")
                except Exception as e:
                    print(f"[DB] Could not add {col_name}: {e}")


def create_edm_views():
    """
    Create EDM-specific database views.
    """
    engine = init_db()

    # View: Tracks by Camelot key for harmonic mixing
    view_camelot = """
    CREATE VIEW IF NOT EXISTS v_edm_by_camelot AS
    SELECT
        f.camelot,
        COUNT(*) AS track_count,
        AVG(f.bpm) AS avg_bpm,
        AVG(f.energy_score) AS avg_energy
    FROM features f
    WHERE f.camelot IS NOT NULL
    GROUP BY f.camelot
    ORDER BY f.camelot
    """

    # View: High-energy tracks
    view_high_energy = """
    CREATE VIEW IF NOT EXISTS v_edm_high_energy AS
    SELECT
        s.id,
        s.path,
        f.bpm,
        f.camelot,
        f.energy_score,
        f.transient_density,
        f.pred_type
    FROM samples s
    JOIN features f ON f.sample_id = s.id
    WHERE f.energy_score > 70
    ORDER BY f.energy_score DESC
    """

    # View: Bass-heavy tracks
    view_bass_heavy = """
    CREATE VIEW IF NOT EXISTS v_edm_bass_heavy AS
    SELECT
        s.id,
        s.path,
        f.bpm,
        f.sub_bass_energy,
        f.bass_energy,
        (f.sub_bass_energy + f.bass_energy) AS total_bass_energy
    FROM samples s
    JOIN features f ON f.sample_id = s.id
    WHERE f.sub_bass_energy IS NOT NULL
    ORDER BY total_bass_energy DESC
    """

    # View: Harmonic mixing suggestions
    view_mixing = """
    CREATE VIEW IF NOT EXISTS v_edm_mixing_suggestions AS
    SELECT
        f1.sample_id AS track_id,
        s1.path AS track_path,
        f1.bpm AS track_bpm,
        f1.camelot AS track_key,
        f2.sample_id AS compatible_id,
        s2.path AS compatible_path,
        f2.bpm AS compatible_bpm,
        f2.camelot AS compatible_key,
        ABS(f1.bpm - f2.bpm) AS bpm_diff
    FROM features f1
    JOIN samples s1 ON s1.id = f1.sample_id
    JOIN features f2 ON f2.camelot = f1.camelot AND f2.sample_id != f1.sample_id
    JOIN samples s2 ON s2.id = f2.sample_id
    WHERE f1.camelot IS NOT NULL
    AND ABS(f1.bpm - f2.bpm) < 5
    """

    views = [
        ("v_edm_by_camelot", view_camelot),
        ("v_edm_high_energy", view_high_energy),
        ("v_edm_bass_heavy", view_bass_heavy),
        ("v_edm_mixing_suggestions", view_mixing)
    ]

    with engine.begin() as conn:
        for view_name, view_sql in views:
            try:
                conn.execute(text(view_sql))
                print(f"[DB] Created view: {view_name}")
            except Exception as e:
                print(f"[DB] Could not create {view_name}: {e}")
