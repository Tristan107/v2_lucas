from __future__ import annotations

import libsql_experimental as libsql  # pyright: ignore[reportMissingModuleSource]

from lucas_v2.db.schema import init_schema


def test_load_schema_returns_sql() -> None:
    from lucas_v2.db.schema import load_schema

    sql = load_schema()
    assert "CREATE TABLE" in sql
    assert "channel" in sql


def test_init_schema_creates_tables() -> None:
    conn = libsql.connect(":memory:")  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
    init_schema(conn)
    rows = conn.execute(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    names: set[str] = {r[0] for r in rows}  # pyright: ignore[reportUnknownVariableType]
    assert "channel" in names
    assert "video" in names
    assert "transcript_chunk" in names


def test_init_schema_idempotent() -> None:
    conn = libsql.connect(":memory:")  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
    init_schema(conn)
    init_schema(conn)
    rows = conn.execute(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        "SELECT name FROM sqlite_master WHERE type='table' AND name='channel'"
    ).fetchall()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert len(rows) == 1  # pyright: ignore[reportUnknownArgumentType]
