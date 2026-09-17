# Plan: Add `--url` option for single-video re-scrape

## Goal
Add a `--url <youtube_url>` option to the `ingest` command that re-downloads a specific video by its YouTube URL. Extracts the video ID from the URL, finds the video (in DB or by searching configured channels), and re-downloads it.

## Files to modify

1. **`src/lucas_v2/__init__.py`** — Add `--url` option, URL parsing helper, DB lookup, single-video flow
2. **`src/lucas_v2/db.py`** — Add `find_video_channel()` function
3. **`README.md`** — Document the new option

## Changes

### 1. `src/lucas_v2/__init__.py`

**Add regex for YouTube video URL parsing** (after imports, ~line 13):
```python
_VIDEO_URL_RE: re.Pattern[str] = re.compile(
    r"(?:youtube\.com/watch\?.*?v=|youtu\.be/)([\w-]{11})"
)
```

**Add helper to extract video ID from URL** (new function):
```python
def _extract_video_id(url: str) -> str | None:
    """Extract 11-char video ID from a YouTube URL. Returns None if no match."""
    m = _VIDEO_URL_RE.search(url)
    return m.group(1) if m else None
```

**Modify `_process_videos`** — add `force_id` parameter to force only one specific video:
- Lines 109-111: Add `force_id: str | None` parameter
- Line 120: Change condition to also check `force_id`:
  ```python
  if not force and not is_new and vid_yt_id != force_id:
  ```

**Modify `ingest` command** — lines 134-172:
- Add `import re` at top of file (line 4)
- Add new Click option after `--dry-run`:
  ```python
  @click.option("--url", "video_url", default=None,
                help="URL YouTube d'une vidéo à re-télécharger.")
  ```
- Update `ingest` signature: add `video_url: str | None` parameter
- Add single-video flow **before** the normal channel loop:
  ```python
  if video_url is not None:
      vid_id: str | None = _extract_video_id(video_url)
      if vid_id is None:
          click.echo(f"URL invalide, impossible d'extraire l'ID : {video_url}", err=True)
          sys.exit(1)

      # 1. Check if video exists in DB → get channel info
      from lucas_v2.db import find_video_channel
      ch_info: tuple[int, str] | None = find_video_channel(conn, vid_id)

      if ch_info is not None:
          channel_row_id_db: int
          channel_row_id_db, yt_channel_id_db = ch_info
          click.echo(f"Vidée {vid_id} trouvée en base, re-téléchargement...")
          # Fetch video details from YouTube API
          from lucas_v2.youtube_api import _get_client
          youtube: Any = _get_client()
          vid_resp: Any = youtube.videos().list(
              part="contentDetails,snippet", id=vid_id
          ).execute()
          items_v: list[dict[str, Any]] = vid_resp.get("items", [])
          if not items_v:
              click.echo(f"Vidéo introuvable sur YouTube : {vid_id}", err=True)
              sys.exit(1)
          v_item: dict[str, Any] = items_v[0]
          vid_data: dict[str, Any] = {
              "video_id": vid_id,
              "title": v_item.get("snippet", {}).get("title", ""),
              "upload_date": None,
              "duration_s": None,
              "youtube_str_id": vid_id,
          }
          if dry_run:
              click.echo(f"     [dry-run] Re-téléchargement de {vid_id}")
          else:
              _download_and_store(vid_data, channel_row_id_db, spec_placeholder, conn, False, tok)
          click.echo("Terminé.")
          return

      # 2. Not in DB → search channels in config
      click.echo(f"Vidéo {vid_id} absente de la base, recherche dans les chaînes configurées...")
      found: bool = False
      for spec in channels:
          click.echo(f"\n--- {spec.url} ---")
          result: tuple[int, str] | None = _resolve_channel(spec, conn)
          if result is None:
              continue
          channel_row_id_c: int
          yt_channel_id_c: str
          channel_row_id_c, yt_channel_id_c = result

          videos_c: list[dict[str, Any]] = _fetch_videos(yt_channel_id_c, spec)
          match: dict[str, Any] | None = next(
              (v for v in videos_c if str(v["youtube_str_id"]) == vid_id), None
          )
          if match is not None:
              click.echo(f"  Trouvée dans {spec.url} !")
              if dry_run:
                  click.echo(f"     [dry-run] Re-téléchargement de {vid_id}")
              else:
                  _download_and_store(match, channel_row_id_c, spec, conn, False, tok)
              found = True
              break

      if not found:
          click.echo(f"Vidéo {vid_id} introuvable dans les chaînes configurées.", err=True)
          sys.exit(1)

      click.echo("\nTerminé.")
      return
  ```

**Note on `spec_placeholder`**: In the "video in DB" branch, we need a `ChannelSpec` to pass to `_download_and_store`. We can create a minimal one from the DB channel info, or refactor `_download_and_store` to accept an optional spec. The cleanest approach: query the channel URL from DB and build a `ChannelSpec` with defaults. Add a DB helper for this (see db.py below).

### 2. `src/lucas_v2/db.py`

**Add `find_video_channel()`** (after `video_exists`, ~line 112):
```python
def find_video_channel(conn: Any, youtube_str_id: str) -> tuple[int, str] | None:
    """Return (channel_row_id, channel_yt_id) for a video, or None."""
    row = conn.execute(
        "SELECT v.fk_channel_id, c.channel_id "
        "FROM video v JOIN channel c ON v.fk_channel_id = c.id "
        "WHERE v.youtube_str_id=?",
        (youtube_str_id,),
    ).fetchone()
    if row is None:
        return None
    return row[0], row[1]
```

**Add `get_channel_url()`** (new helper):
```python
def get_channel_url(conn: Any, channel_row_id: int) -> str | None:
    """Return the channel_url for a given channel row ID."""
    row = conn.execute(
        "SELECT channel_url FROM channel WHERE id=?", (channel_row_id,)
    ).fetchone()
    return row[0] if row else None
```

### 3. `README.md`

**After line 78**, add a new example:
```bash
# Re-télécharger une vidéo spécifique par URL
uv run lucas-v2 ingest -c channels.yaml --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

## Interaction with other flags

| `--url` | `--force-all` | `--dry-run` | Behavior |
|---------|--------------|-------------|----------|
| ✓ | — | — | Re-download the specific video |
| ✓ | — | ✓ | Show what would be done for that video |
| ✓ | ✓ | — | `--force-all` ignored, only the specific video is processed |
| — | ✓ | — | Re-download ALL videos (with confirmation) |
| — | — | ✓ | List videos without downloading |

## Verification

```bash
uv run lucas-v2 ingest --help              # shows --url option
uv run lucas-v2 ingest --url "https://www.youtube.com/watch?v=oixGs6UFZoA" --dry-run
uv run lucas-v2 ingest --url "https://youtu.be/oixGs6UFZoA" --dry-run
uv run lucas-v2 ingest --url "bad-url"     # should error
uv run lucas-v2 ingest --url "https://www.youtube.com/watch?v=nonexistent123"  # searches channels
uv run pytest tests/ -v                    # existing tests pass
```
