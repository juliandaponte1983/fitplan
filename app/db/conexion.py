"""Conexión SQLite con migraciones por PRAGMA user_version."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app import config

MIGRACIONES = [Path(__file__).with_name("esquema.sql")]  # índice = versión - 1


def conectar(ruta: Path | str | None = None) -> sqlite3.Connection:
    ruta = Path(ruta or config.DB_PATH)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    migrar(conn)
    try:
        ruta.chmod(0o600)
    except OSError:
        pass
    return conn


def migrar(conn: sqlite3.Connection) -> int:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, sql in enumerate(MIGRACIONES[version:], start=version + 1):
        with conn:
            conn.executescript(sql.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {i}")
    return conn.execute("PRAGMA user_version").fetchone()[0]
