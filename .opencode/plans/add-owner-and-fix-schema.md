# Plan: Add `owner` field to video table + consolidate schema script

## Goal
1. Add `owner` field (from `channels.yaml`) to the `video` table
2. Consolidate `_TABLES`, `_INDEXES`, `_FTS_STMTS` into a single `_SCHEMA_SCRIPT` variable
3. Replace fragile `split(";")` execution with `conn.executescript()`
4. Add migration code for existing databases (separate block, marked for later cleanup)

---

## Files to modify

| File | Changes |
|---|---|
| `src/lucas_v2/schema.py` | Consolidate SQL, add `owner` column, use `executescript()`, add migration |
| `src/lucas_v2/config.py` | Add `owner` to `ChannelSpec`, parse it in `load_channels()` |
| `src/lucas_v2/db.py` | Add `owner` param to `upsert_video()` SQL |
| `src/lucas_v2/__init__.py` | Pass `spec.owner` through to `upsert_video()` calls |

---

## Step 1: `src/lucas_v2/schema.py` — Consolidate + fix execution

**Current state:** 3 separate variables (`_TABLES`, `_INDEXES`, `_FTS_STMTS`) + a list-based approach for FTS + manual `split(";")` parsing.

**New state:** Single `_SCHEMA_SCRIPT` string containing all CREATE statements (tables, indexes, FTS, triggers), executed via `conn.executescript()`.

```python
_SCHEMA_SCRIPT = """
CREATE TABLE IF NOT EXISTS channel (...);
CREATE TABLE IF NOT EXISTS video (
  ...,
  owner TEXT,          -- NEW
  ...
);
CREATE TABLE IF NOT EXISTS transcript_chunk (...);
CREATE INDEX IF NOT EXISTS idx_video_fk_channel ON video(fk_channel_id);
CREATE INDEX IF NOT EXISTS idx_channel_ytid ON channel(channel_id);
CREATE VIRTUAL TABLE IF NOT EXISTS transcript_chunk_fts USING fts5(...);
CREATE TRIGGER IF NOT EXISTS trg_chunk_fts_ai ...;
CREATE TRIGGER IF NOT EXISTS trg_chunk_fts_ad ...;
CREATE TRIGGER IF NOT EXISTS trg_chunk_fts_au ...;
"""

def init_schema(conn):
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
    except Exception:
        pass
    conn.executescript(_SCHEMA_SCRIPT)
    # TODO: remove migration block once all DBs are migrated
    _migrate_add_owner(conn)
    conn.commit()
```

**Migration function** (separate, for cleanup later):
```python
def _migrate_add_owner(conn):
    """Add owner column to video table if missing. Remove after full rollout."""
    try:
        conn.execute("ALTER TABLE video ADD COLUMN owner TEXT")
        conn.commit()
    except Exception:
        pass  # column already exists
```

---

## Step 2: `src/lucas_v2/config.py` — Add `owner` to ChannelSpec

- Add `owner: str | None = None` to the `ChannelSpec` dataclass
- Parse `owner` from channel YAML in `load_channels()`:
  ```python
  owner=ch.get("owner", defaults.get("owner")),
  ```

---

## Step 3: `src/lucas_v2/db.py` — Add `owner` to upsert_video

- Add `owner: str | None = None` parameter to `upsert_video()`
- Add `owner` to the INSERT column list and VALUES placeholders
- Add `owner=excluded.owner` to the ON CONFLICT DO UPDATE SET

---

## Step 4: `src/lucas_v2/__init__.py` — Pass `owner` through

Three call sites for `upsert_video()` (lines 96, 103, 112) — add `spec.owner` as argument in each.

---

## Verification

1. Check that `_SCHEMA_SCRIPT` is syntactically valid SQL (no split issues)
2. Verify `executescript()` works with libsql_experimental (it's a sqlite3 drop-in)
3. Confirm `ALTER TABLE` migration is idempotent (try/except on "duplicate column" error)
4. Grep for any remaining `split(";")` patterns
