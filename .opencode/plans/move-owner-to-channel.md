# Plan: Move `owner` from `video` to `channel`, refresh from YAML every ingest

## Goal
- `owner` is a channel-level attribute: remove it from `video`, add it to `channel`.
- Every `ingest` run updates `channel.owner` from `channels.yaml` (same pattern as `orientation` today).
- Manual one-shot SQL for the existing DB (per AGENTS.md: no Python migration code).

## Context / key observation
`orientation` already implements exactly this pattern: `ChannelSpec.orientation` → `_resolve_channel(spec, ...)` → `upsert_channel(..., spec.orientation)` → `ON CONFLICT DO UPDATE`. `owner` should mirror it. Files: `src/lucas_v2/schema.sql`, `src/lucas_v2/db.py`, `src/lucas_v2/__init__.py`, `tests/test_db.py`. `config.py` already parses `owner` — no change needed there. `search_chunks` never references `owner` — no query change needed.

## Manual one-shot SQL (user runs, not generated code)
```sql
ALTER TABLE channel ADD COLUMN owner TEXT;
ALTER TABLE video DROP COLUMN owner;
-- Backfill channel.owner from YAML values (one line per channel, 13 total):
UPDATE channel SET owner = 'Nathalie Arthaud' WHERE channel_url = 'https://www.youtube.com/@lutteouvriere';
-- ... repeat for each channel in channels.yaml ...
```
Note: `DROP COLUMN` requires SQLite ≥ 3.35 (Turso/libsql OK). Run backfill only for `video` rows already migrated — actually no video backfill needed since column moves to `channel`.

## Step 1 — `src/lucas_v2/schema.sql`
- `channel` table: add `owner TEXT,` (next to `orientation TEXT,`).
- `video` table: delete the `owner TEXT,` line.
- Single `_SCHEMA_SCRIPT` variable untouched (still one script, still `executescript()`).

## Step 2 — `src/lucas_v2/db.py`
- `upsert_channel`: add `owner: str | None` param; add `owner` to INSERT cols/values; add `owner=excluded.owner` to `ON CONFLICT DO UPDATE SET`.
  - Open point: use `owner=COALESCE(excluded.owner, channel.owner)` instead, so a YAML entry *without* `owner` (or the `--url` path that builds a bare `ChannelSpec`) never nulls out an existing value. YAML *with* `owner` still overwrites every run. Recommend COALESCE.
- `upsert_video`: remove `owner` param, remove `owner` from INSERT cols/values, remove `owner=excluded.owner` from conflict clause. Signature shrinks by one arg.

## Step 3 — `src/lucas_v2/__init__.py`
- `_resolve_channel` (line 50): pass `spec.owner` to `upsert_channel` — this is what makes owner refresh on every ingest run, for every channel in YAML, before any video work.
- `_download_and_store` (3 call sites, lines 90-116): drop the `spec.owner` argument from each `upsert_video()` call.
- `_fetch_and_download_single` (line 329): builds `ChannelSpec(url=channel_url, ...)` with `owner=None`. With COALESCE in `upsert_channel` this is safe (preserves DB value). Without COALESCE it would wipe owner on `--url` re-ingests of unknown videos. Either keep COALESCE or look up the matching spec from `channels` by URL — recommend COALESCE (simpler, complexity-neutral).

## Step 4 — `tests/test_db.py`
- `upsert_channel` calls gain an `owner` arg; add assertion that conflict-update refreshes `owner` (mirrors existing orientation test).
- All `upsert_video` calls drop the `owner`/`None` positional arg (8+ call sites).

## Verification
1. `pyright` (per AGENTS.md strong typing) — signatures changed in `db.py` + call sites in `__init__.py` + tests.
2. `pytest` — update tests first (TDD skill available), then run full suite.
3. Fresh-DB check: `init_schema` on `:memory:` → `PRAGMA table_info(channel)` contains `owner`, `video` does not.
4. Grep `owner` — expect hits only in: `schema.sql` (channel), `config.py`, `db.upsert_channel`, `__init__._resolve_channel`, tests, YAML. Zero hits in `upsert_video`.
5. Cognitive complexity ≤ 15: changes are signature/plumbing only, no new branches except possibly one `COALESCE` (SQL, not Python).

## Risks / decisions for user
- COALESCE vs plain overwrite (recommend COALESCE, see Step 2).
- `DROP COLUMN` on existing Turso DB: fine on modern SQLite, but user runs it manually — verify `SELECT sqlite_version()` if unsure.
