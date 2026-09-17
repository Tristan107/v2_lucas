from __future__ import annotations

import logging
import os
from typing import Any

import libsql as libsql  # pyright: ignore[reportMissingModuleSource]

logger: logging.Logger = logging.getLogger("lucas_v2")


class DbConn:
    """Wrapper around libsql connection that auto-reconnects on Turso stream expiry."""

    def __init__(self, conn: Any) -> None:
        self._conn: Any = conn

    def execute(self, query: str, params: Any = ()) -> Any:
        try:
            return self._conn.execute(query, params)
        except ValueError as e:
            if "stream not found" not in str(e):
                raise
            logger.warning("Turso stream expired, reconnecting...")
            self._conn = _raw_connect()
            return self._conn.execute(query, params)

    def commit(self) -> None:
        try:
            self._conn.commit()
        except ValueError as e:
            if "stream not found" not in str(e):
                raise
            logger.warning("Turso stream expired during commit, reconnecting...")
            self._conn = _raw_connect()
            self._conn.commit()

    def rollback(self) -> None:
        try:
            self._conn.rollback()
        except ValueError as e:
            if "stream not found" not in str(e):
                raise
            logger.warning("Turso stream expired during rollback, reconnecting...")
            self._conn = _raw_connect()

    def executescript(self, script: str) -> Any:
        try:
            return self._conn.executescript(script)
        except ValueError as e:
            if "stream not found" not in str(e):
                raise
            logger.warning("Turso stream expired during executescript, reconnecting...")
            self._conn = _raw_connect()
            return self._conn.executescript(script)


def _raw_connect() -> Any:
    url: str = os.environ["TURSO_DATABASE_URL"]
    token: str | None = os.environ.get("TURSO_AUTH_TOKEN")
    return libsql.connect(url, auth_token=token)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]


def connect() -> DbConn:
    return DbConn(_raw_connect())
