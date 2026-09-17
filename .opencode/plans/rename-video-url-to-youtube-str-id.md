# Plan: Rename `video.video_url` → `video.youtube_str_id`

## Context

The `video_url` column stores the full YouTube URL (`https://www.youtube.com/watch?v=abc123`), but the prefix is redundant since it's always the same. The column should store only the YouTube video ID (`abc123`) and be renamed to `youtube_str_id`.

## Step 0: SQL migration script (run manually)

Provide a standalone SQL script the user runs against their Turso database:

```sql
ALTER TABLE video RENAME COLUMN video_url TO youtube_str_id;
UPDATE video SET youtube_str_id = REPLACE(youtube_str_id, 'https://www.youtube.com/watch?v=', '');
```

## Step 1: `src/lucas_v2/schema.py` (line 13)

Change column definition from `video_url TEXT NOT NULL UNIQUE` → `youtube_str_id TEXT NOT NULL UNIQUE`.

## Step 2: `src/lucas_v2/db.py`

### `search_chunks()` (line 21)
Replace the substr/instr extraction:
```
substr(v.video_url, instr(v.video_url, 'v=') + 2) AS youtube_id
```
with:
```
v.youtube_str_id AS youtube_id
```

### `upsert_video()` (lines 51-71)
- Rename parameter `video_url` → `youtube_str_id`
- Update all SQL: column name, INSERT, ON CONFLICT, VALUES

### `video_exists_ok()` (lines 102-106)
- Rename parameter `video_url` → `youtube_str_id`
- Update SQL: `WHERE youtube_str_id=?`

### `video_exists()` (lines 109-113)
- Rename parameter `video_url` → `youtube_str_id`
- Update SQL: `WHERE youtube_str_id=?`

## Step 3: `src/lucas_v2/youtube_api.py` (line 168)

Change the return dict key from `"video_url": f"https://www.youtube.com/watch?v={vid_id}"` → `"youtube_str_id": vid_id`.

## Step 4: `src/lucas_v2/subs.py` (line 19)

Change `download_srt(video_url)` parameter name to `download_srt(youtube_str_id)` and construct the full URL inside the function for `yt-dlp`:
```python
def download_srt(youtube_str_id: str) -> ...:
    video_url = f"https://www.youtube.com/watch?v={youtube_str_id}"
    ...
```

## Step 5: `src/lucas_v2/__init__.py` (lines 73-114)

- Line 73: `vid_url = vid["video_url"]` → `vid_yt_id = vid["youtube_str_id"]`
- Line 79: `video_exists(conn, vid_url)` → `video_exists(conn, vid_yt_id)`
- Line 89: `download_srt(vid_url)` → `download_srt(vid_yt_id)`
- Lines 96, 103, 112: all `upsert_video(conn, ..., vid_url, ...)` → `upsert_video(conn, ..., vid_yt_id, ...)`

## Step 6: `README.md` (lines 92, 101-102)

Update the sample query to concatenate the base URL with the ID:
```sql
'https://www.youtube.com/watch?v=' || v.youtube_str_id || '&t=' || tc.start_s AS video_link
```
Update the explanation text accordingly.

## Files changed (6 total)

| File | Change |
|------|--------|
| `src/lucas_v2/schema.py` | Column rename in CREATE TABLE |
| `src/lucas_v2/db.py` | Parameter + SQL column renames |
| `src/lucas_v2/youtube_api.py` | Return `youtube_str_id` instead of `video_url` |
| `src/lucas_v2/subs.py` | Accept `youtube_str_id`, build URL internally |
| `src/lucas_v2/__init__.py` | Pass `youtube_str_id` through pipeline |
| `README.md` | Sample query update |

## Verification

1. Run `uv run pytest tests/ -v` to ensure existing tests pass
2. Run `uv run lucas-v2 ingest -c channels.yaml --dry-run` to verify ingest still works
3. Verify SQL migration against a test database before running on production
