from __future__ import annotations

from dataclasses import dataclass

from . import config
from .db import get_engine, text


@dataclass(frozen=True)
class DbDoctorReport:
    db_path: str
    quick_check_ok: bool
    foreign_keys_ok: bool
    journal_mode: str
    page_count: int
    sample_count: int
    embedding_count: int
    vec_state_count: int


def run_db_doctor() -> DbDoctorReport:
    engine = get_engine()
    with engine.begin() as conn:
        quick_check = conn.execute(text("PRAGMA quick_check")).fetchone()[0]
        fk_rows = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        journal_mode = conn.execute(text("PRAGMA journal_mode")).fetchone()[0]
        page_count = conn.execute(text("PRAGMA page_count")).fetchone()[0]
        sample_count = conn.execute(text("SELECT COUNT(*) FROM samples")).fetchone()[0]
        embedding_count = conn.execute(
            text("SELECT COUNT(*) FROM sample_embeddings")
        ).fetchone()[0]
        vec_state_count = conn.execute(
            text("SELECT COUNT(*) FROM vector_index_state")
        ).fetchone()[0]

    return DbDoctorReport(
        db_path=str(config.DB_PATH),
        quick_check_ok=quick_check == "ok",
        foreign_keys_ok=len(fk_rows) == 0,
        journal_mode=str(journal_mode),
        page_count=int(page_count),
        sample_count=int(sample_count),
        embedding_count=int(embedding_count),
        vec_state_count=int(vec_state_count),
    )


def print_db_doctor_report(report: DbDoctorReport) -> int:
    print(f"db_path={report.db_path}")
    print(f"quick_check={'ok' if report.quick_check_ok else 'FAIL'}")
    print(f"foreign_keys={'ok' if report.foreign_keys_ok else 'FAIL'}")
    print(f"journal_mode={report.journal_mode}")
    print(f"page_count={report.page_count}")
    print(f"samples={report.sample_count}")
    print(f"embeddings={report.embedding_count}")
    print(f"vector_index_state_rows={report.vec_state_count}")
    if report.quick_check_ok and report.foreign_keys_ok:
        return 0
    return 1
