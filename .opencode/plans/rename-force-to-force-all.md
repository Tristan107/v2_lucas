# Plan: Rename `--force` to `--force-all` with confirmation prompt

## Goal
Rename the `--force` CLI flag to `--force-all` and add an interactive confirmation prompt before re-downloading all videos.

## Files to modify

1. **`src/lucas_v2/__init__.py`** — CLI option, parameter name, help text, confirmation logic, skip message
2. **`README.md`** — documentation example

## Changes

### 1. `src/lucas_v2/__init__.py`

**Line 138** — Rename the Click option:
```python
# Before
@click.option("--force", is_flag=True, help="Re-scrape même si déjà en base avec status=ok.")

# After
@click.option("--force-all", is_flag=True, help="Re-scrape toutes les vidéos déjà en base (avec confirmation).")
```

**Line 139** — Rename the parameter:
```python
# Before
def ingest(config_path: str, dry_run: bool, force: bool) -> None:

# After
def ingest(config_path: str, dry_run: bool, force_all: bool) -> None:
```

**Line 171** — Pass `force_all` instead of `force`:
```python
# Before
_process_videos(videos, channel_row_id, spec, conn, force, dry_run, tok)

# After
_process_videos(videos, channel_row_id, spec, conn, force_all, dry_run, tok)
```

**After line 152 (after loading channels, before the loop)** — Add confirmation prompt when `force_all` is True:
```python
if force_all and not dry_run:
    click.echo(f"\n⚠ Cette option re-téléchargera TOUTES les vidéos de {len(channels)} chaîne(s) déjà en base.")
    if not click.confirm("Voulez-vous vraiment re-télécharger toutes les vidéos listées dans channels.yaml ?"):
        click.echo("Annulé.")
        sys.exit(0)
```

**Line 111** — Rename parameter in `_process_videos` signature:
```python
# Before
spec: ChannelSpec, conn: Any, force: bool, dry_run: bool, tok: Any,

# After
spec: ChannelSpec, conn: Any, force_all: bool, dry_run: bool, tok: Any,
```

**Lines 120-121** — Update variable name and skip message:
```python
# Before
if not force and not is_new:
    click.echo("     Déjà scrapée, skip (utiliser --force pour re-scraper).")

# After
if not force_all and not is_new:
    click.echo("     Déjà scrapée, skip (utiliser --force-all pour re-scraper).")
```

### 2. `README.md`

**Line 78** — Update the example:
```bash
# Before
uv run lucas-v2 ingest -c channels.yaml --force

# After
uv run lucas-v2 ingest -c channels.yaml --force-all
```

## Verification

```bash
uv run lucas-v2 ingest --help          # should show --force-all
uv run lucas-v2 ingest -c channels.yaml --force-all --dry-run   # should trigger confirmation
uv run pytest tests/ -v                # existing tests still pass
```
