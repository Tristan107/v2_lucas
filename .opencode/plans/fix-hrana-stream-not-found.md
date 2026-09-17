# Fix: Hrana "stream not found" during long ingestion

## Problem
During long ingestion sessions (many videos across multiple channels), the Turso/libSQL
Hrana stream expires server-side after ~60s of inactivity on the HTTP connection. The gap
between the last `conn.commit()` of video N and the first `conn.execute()` of video N+1
includes `paced_sleep(10-15s)` + `download_srt()` (yt-dlp network calls, 10-30s+), easily
exceeding the Turso timeout.

The error is an unhandled `ValueError` with message containing `"stream not found"`, which
crashes the entire ingestion.

## Solution: `DbConn` auto-reconnecting wrapper in `db.py`

### 1. Add `DbConn` class to `src/lucas_v2/db.py`

A thin wrapper class around the raw libsql connection that:
- Proxies `execute()`, `commit()`, `executescript()`, `rollback()`
- Catches `ValueError` with "stream not found" in the message
- On catch: logs a warning, calls `connect()` to get a fresh connection, retries the operation
- Passes through all other exceptions unchanged

```python
import logging

logger = logging.getLogger("lucas_v2")

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
            self._conn = connect()
            return self._conn.execute(query, params)

    def commit(self) -> None:
        try:
            self._conn.commit()
        except ValueError as e:
            if "stream not found" not in str(e):
                raise
            logger.warning("Turso stream expired during commit, reconnecting...")
            self._conn = connect()
            self._conn.commit()

    def rollback(self) -> None:
        try:
            self._conn.rollback()
        except ValueError as e:
            if "stream not found" not in str(e):
                raise
            logger.warning("Turso stream expired during rollback, reconnecting...")
            self._conn = connect()

    def executescript(self, script: str) -> Any:
        try:
            return self._conn.executescript(script)
        except ValueError as e:
            if "stream not found" not in str(e):
                raise
            logger.warning("Turso stream expired during executescript, reconnecting...")
            self._conn = connect()
            return self._conn.executescript(script)
```

### 2. Update `connect()` in `db.py` to return `DbConn`

Change the return type and wrap:

```python
def connect() -> DbConn:
    url: str = os.environ["TURSO_DATABASE_URL"]
    token: str | None = os.environ.get("TURSO_AUTH_TOKEN")
    conn = libsql.connect(url, auth_token=token)
    return DbConn(conn)
```

### 3. No changes needed in `__init__.py` or other callers

Since all functions in `db.py` receive `conn: Any` and call `conn.execute()` / `conn.commit()`,
and `DbConn` exposes the same methods, no caller changes are required. The `Any` type annotation
on all `conn` parameters means `DbConn` is accepted without type errors.

### 4. Update tests

- **`tests/test_db.py`**: No changes needed — tests use `libsql.connect(":memory:")` directly
  (in-memory, no Hrana), so they don't go through `connect()` or `DbConn`.
- **`tests/test_cli.py`**: The mock `lucas_v2.db.connect` returns a `MagicMock` which already
  has `execute`/`commit` attributes. No changes needed.

### 5. Add unit test for `DbConn` reconnection in `tests/test_db.py`

Add a focused test that:
- Creates a `DbConn` with a mock connection
- Makes the mock's `execute` raise `ValueError("stream not found")` on first call
- Verifies it reconnects and retries

```python
from unittest.mock import MagicMock, patch

def test_dbconn_reconnects_on_stream_not_found() -> None:
    from lucas_v2.db import DbConn

    mock_conn1 = MagicMock()
    mock_conn2 = MagicMock()
    mock_conn1.execute.side_effect = ValueError("stream not found: abc123")
    mock_conn2.execute.return_value = MagicMock(fetchone=lambda: (1,))

    wrapper = DbConn(mock_conn1)

    with patch("lucas_v2.db.connect", return_value=mock_conn2):
        result = wrapper.execute("SELECT 1")

    # Should have retried on the new connection
    mock_conn2.execute.assert_called_once_with("SELECT 1", ())
    assert result.fetchone() == (1,)

def test_dbconn_does_not_catch_other_valueerrors() -> None:
    from lucas_v2.db import DbConn

    mock_conn = MagicMock()
    mock_conn.execute.side_effect = ValueError("some other error")
    wrapper = DbConn(mock_conn)

    try:
        wrapper.execute("SELECT 1")
        assert False, "Should have raised"
    except ValueError as e:
        assert "some other error" in str(e)
```

## Files to modify
1. `src/lucas_v2/db.py` — Add `DbConn` class + update `connect()` return
2. `tests/test_db.py` — Add `DbConn` reconnection tests

## Verification
1. `pyright src/lucas_v2/db.py` — No type errors
2. `pytest tests/test_db.py -v` — All existing + new tests pass
3. `pytest tests/ -v` — Full suite passes (no regressions)
4. `pytest tests/ --cov=lucas_v2` — Coverage check

## Risks
- **Low risk**: `DbConn` is a transparent proxy; all existing callers use `conn: Any` so no type breakage
- **Edge case**: If reconnect itself fails (e.g. invalid credentials), the `connect()` call will
  raise its own exception, which is the correct behavior (no infinite retry loop)
- **In-memory test DBs**: Tests using `:memory:` bypass `connect()`, so unaffected
