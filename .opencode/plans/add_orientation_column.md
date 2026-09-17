# Plan: Add `orientation` column to `channel` table

## Goal
Add a `TEXT` column `orientation` to the `channel` table and populate it from the `orientation` field in `channels.yaml`.

## Files to modify (4 files)

### 1. `src/lucas_v2/schema.py` (lines 6-12, 66-72)

**Schema** — add `orientation TEXT` after `title` in CREATE TABLE (line 10):

```sql
CREATE TABLE IF NOT EXISTS channel (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_url TEXT NOT NULL UNIQUE,
  channel_id TEXT,
  title TEXT,
  orientation TEXT,          -- NEW
  added_at TEXT DEFAULT (datetime('now'))
);
```

**Migration** — in `init_schema` after `conn.executescript(...)` (line 71), add:

```python
try:
    conn.execute("ALTER TABLE channel ADD COLUMN orientation TEXT")
    conn.commit()
except Exception:
    pass  # column already exists
```

### 2. `src/lucas_v2/config.py` (lines 9-39)

- Add `orientation: str | None = None` to `ChannelSpec` after `owner` (line 15).
- Add `d_orientation: str | None = defaults.get("orientation")` after line 26.
- Pass `orientation=ch.get("orientation", d_orientation)` in ChannelSpec constructor (line 33-39).

### 3. `src/lucas_v2/db.py` (lines 42-53)

Update `upsert_channel` — add `orientation` parameter and SQL column:

```python
def upsert_channel(conn: Any, channel_url: str, channel_id: str | None,
                   title: str | None, orientation: str | None) -> int:
    """Upsert channel, retourne l'id local (channel.id) pour la FK video."""
    conn.execute(
        "INSERT INTO channel (channel_url, channel_id, title, orientation) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(channel_url) DO UPDATE SET "
        "channel_id=excluded.channel_id, title=excluded.title, orientation=excluded.orientation",
        (channel_url, channel_id, title, orientation),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM channel WHERE channel_url=?", (channel_url,)
    ).fetchone()
    return int(row[0])
```

### 4. `src/lucas_v2/__init__.py` (line 49)

Update `_resolve_channel` — pass `spec.orientation` to `upsert_channel`:

```python
row_id: int = upsert_channel(conn, spec.url, yt_channel_id, channel_title, spec.orientation)
```

**Note:** `_fetch_and_download_single` (line 327) creates a local `ChannelSpec` without orientation — defaults to `None`, correct behavior (no YAML context for single-video re-download).

## Migration strategy
SQLite `ALTER TABLE ADD COLUMN` is idempotent via try/except — works for both fresh and existing databases.

## Verification
- Run `pyright` for type-checking
- Run `pytest` if tests exist
