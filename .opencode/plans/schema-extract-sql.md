# Plan: Extract SQL from schema.py into dedicated SQL file

## Goal
Move the SQL schema definition from `src/lucas_v2/schema.py` into a separate `.sql` file, and update `schema.py` to load the SQL from the file at runtime.

## Files to Modify

1. **Create** `src/lucas_v2/schema.sql` — the extracted SQL schema
2. **Modify** `src/lucas_v2/schema.py` — replace inline SQL with file read

## Step 1: Create `src/lucas_v2/schema.sql`

Extract the content of `_SCHEMA_SCRIPT` (lines 5–63) into a standalone file. This includes the `orientation` column that was recently added:

```sql
CREATE TABLE IF NOT EXISTS channel (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_url TEXT NOT NULL UNIQUE,
  channel_id TEXT,
  title TEXT,
  orientation TEXT,
  added_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS video (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fk_channel_id INTEGER,
  youtube_str_id TEXT NOT NULL UNIQUE,
  title TEXT,
  upload_date TEXT,
  duration_s INTEGER,
  sub_lang TEXT,
  sub_kind TEXT,
  owner TEXT,
  status TEXT DEFAULT 'ok',
  error TEXT,
  scraped_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (fk_channel_id) REFERENCES channel(id)
);

CREATE TABLE IF NOT EXISTS transcript_chunk (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fk_video_id INTEGER NOT NULL REFERENCES video(id) ON DELETE CASCADE,
  seq_no INTEGER NOT NULL,
  start_s INTEGER NOT NULL,
  end_s INTEGER NOT NULL,
  text TEXT NOT NULL,
  tokens INTEGER NOT NULL,
  UNIQUE(fk_video_id, seq_no)
);

CREATE INDEX IF NOT EXISTS idx_video_fk_channel ON video(fk_channel_id);
CREATE INDEX IF NOT EXISTS idx_channel_ytid ON channel(channel_id);

CREATE VIRTUAL TABLE IF NOT EXISTS transcript_chunk_fts USING fts5(
  text,
  content='transcript_chunk',
  content_rowid='id',
  tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER IF NOT EXISTS trg_chunk_fts_ai AFTER INSERT ON transcript_chunk BEGIN
  INSERT INTO transcript_chunk_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS trg_chunk_fts_ad AFTER DELETE ON transcript_chunk BEGIN
  INSERT INTO transcript_chunk_fts(transcript_chunk_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS trg_chunk_fts_au AFTER UPDATE ON transcript_chunk BEGIN
  INSERT INTO transcript_chunk_fts(transcript_chunk_fts, rowid, text) VALUES ('delete', old.id, old.text);
  INSERT INTO transcript_chunk_fts(rowid, text) VALUES (new.id, new.text);
END;
```

## Step 2: Update `src/lucas_v2/schema.py`

Replace the inline `_SCHEMA_SCRIPT` string with a `Path`-based file read. Keep the ALTER TABLE migration in Python (it handles existing DBs that lack the `orientation` column):

```python
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
    try:
        conn.execute("ALTER TABLE channel ADD COLUMN orientation TEXT")
        conn.commit()
    except Exception:
        pass
    conn.commit()
```

Key changes:
- Removed `_SCHEMA_SCRIPT` constant
- Added `_SCHEMA_PATH` using `Path(__file__).with_name("schema.sql")` for robust path resolution
- Added `_load_schema()` helper to read the file at call time
- `init_schema` calls `_load_schema()` instead of using the old constant
- The `ALTER TABLE` migration stays in Python (needs try/except for idempotency)

## Considerations

- **No import side-effect on module load**: Reading the file in `_load_schema()` defers I/O to `init_schema()` call time, not at import.
- **Packaging**: `uv_build` uses `src` layout. The `.sql` file sits alongside `schema.py` in the package directory, so it will be included automatically (no `pyproject.toml` changes needed since `uv_build` includes all files in the package by default).
- **Migration logic stays in Python**: The `ALTER TABLE` wrapped in try/except is migration code, not schema definition — it belongs in Python for maintainability.
- **Strong typing / pyright**: `_SCHEMA_PATH` is `Path`, `_load_schema()` returns `str`. No type issues. Run `pyright` after changes.

## Verification

1. Run `pyright src/lucas_v2/schema.py` — no type errors
2. Run any existing tests: `pytest`
3. Smoke-test: `python -c "from lucas_v2.schema import init_schema; print('OK')"` to verify the module loads correctly
