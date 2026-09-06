from __future__ import annotations

from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _load_schema() -> str:
    return _SCHEMA_PATH.read_text(encoding="utf-8")


def init_schema(conn: Any) -> None:
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
    except Exception:
        pass
    conn.executescript(_load_schema())
    conn.commit()
