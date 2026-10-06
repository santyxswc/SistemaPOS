from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(database: str) -> sqlite3.Connection:
    """Conexión en modo manual de transacciones (BEGIN/COMMIT explícitos)."""
    if database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
