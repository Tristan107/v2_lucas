# Plan: Remove delay for already-scraped videos

## Problem
In `src/lucas_v2/__init__.py`, the 3-second `INTER_VIDEO_DELAY_S` sleep at line 76-77 fires **before** the `video_exists()` check at line 79. This means every already-scraped video still causes a 3-second pause before being skipped — wasted time.

## Fix
Move the `time.sleep(INTER_VIDEO_DELAY_S)` call from line 76-77 (before `video_exists`) to after the `video_exists` check, just before the actual download (before line 88).

### Before (lines 76-87):
```python
if i > 0 and not dry_run:
    time.sleep(INTER_VIDEO_DELAY_S)

is_new = not video_exists(conn, vid_yt_id)
if not force and not is_new:
    click.echo("     Déjà scrapée, skip (utiliser --force pour re-scraper).")
    continue

if dry_run:
    click.echo(f"     [dry-run] Upload: {vid.get('upload_date')}, Durée: {vid.get('duration_s')}s")
    continue
```

### After:
```python
is_new = not video_exists(conn, vid_yt_id)
if not force and not is_new:
    click.echo("     Déjà scrapée, skip (utiliser --force pour re-scraper).")
    continue

if dry_run:
    click.echo(f"     [dry-run] Upload: {vid.get('upload_date')}, Durée: {vid.get('duration_s')}s")
    continue

if i > 0 and not dry_run:
    time.sleep(INTER_VIDEO_DELAY_S)
```

## File to edit
- `src/lucas_v2/__init__.py` — move the 2-line sleep block from lines 76-77 to after line 86 (after the dry-run check, before the download)

## Result
Already-scraped videos will be skipped instantly with zero delay. The politeness delay only applies to videos that are actually being downloaded.
