# Fix: `_fetch_videos` receives URL instead of channel ID

## Bug

In `src/lucas_v2/__init__.py` line 161:

```python
videos = _fetch_videos(spec.url, spec)
```

`spec.url` is the raw URL (e.g., `https://www.youtube.com/@JLMelenchon`), but `_fetch_videos` passes it to `list_videos(channel_id, ...)` which uses it as the `id` parameter in a YouTube API call (`channels().list(id=...)`). The API expects a `UC...` channel ID, gets a URL string, returns no items, and the result is 0 videos.

The channel ID **is** correctly resolved on line 157 via `_resolve_channel()`, but only the database row ID is returned — the YouTube channel ID (`yt_channel_id`) is discarded after being printed on line 34.

## Root Cause

`_resolve_channel()` (line 28) resolves the URL to `(yt_channel_id, channel_title)` but returns only the database row ID (`int`). The `yt_channel_id` is lost, so line 161 falls back to passing `spec.url`.

## Fix

Two changes in `src/lucas_v2/__init__.py`:

### 1. Make `_resolve_channel` return the YouTube channel ID

Change return type from `int | None` to `tuple[int, str] | None`, returning both the DB row ID and the YouTube channel ID.

```python
def _resolve_channel(spec: ChannelSpec, conn: Any) -> tuple[int, str] | None:
    ...
    yt_channel_id, channel_title = resolve_channel_id(spec.url)
    click.echo(f"  channelId: {yt_channel_id} ({channel_title})")
    row_id = upsert_channel(conn, spec.url, yt_channel_id, channel_title)
    return row_id, yt_channel_id
```

### 2. Unpack and pass the YouTube channel ID to `_fetch_videos`

In the `ingest()` command, unpack the tuple and pass `yt_channel_id` instead of `spec.url`:

```python
result = _resolve_channel(spec, conn)
if result is None:
    continue
channel_row_id, yt_channel_id = result

videos = _fetch_videos(yt_channel_id, spec)
```

## Files to modify

- `src/lucas_v2/__init__.py` — lines 28-38 and 155-163

## Verification

```bash
uv run lucas-v2 ingest -c channels.yaml --dry-run
```

Should now show `11 vidéo(s) trouvée(s).` instead of `0 vidéo(s) trouvée(s).`.
