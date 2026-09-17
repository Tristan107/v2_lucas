# Plan: Improve Test Coverage from ~32% to 75%+

## Current State

| Module | Lines | Covered | Rate | Status |
|--------|-------|---------|------|--------|
| `srt.py` | 40 | 39 | 97.5% | ✅ Well tested |
| `chunking.py` | 106 | 99 | 93.6% | ✅ Well tested |
| `config.py` | 26 | 12 | 46.2% | ⚠️ `load_channels()` untested |
| `__init__.py` | 173 | 35 | 20.2% | ⚠️ Orchestration untested |
| `db.py` | 44 | 0 | 0% | ❌ No tests |
| `subs.py` | 67 | 0 | 0% | ❌ No tests |
| `youtube_api.py` | 173 | 0 | 0% | ❌ No tests |
| `schema.py` | 10 | 0 | 0% | ❌ No tests |
| `logging_config.py` | 36 | 0 | 0% | ❌ Not in coverage scope |
| **Total** | **547** | **174** | **31.8%** | |

**Target**: 75%+ line coverage (~410+ of 547 lines covered).

---

## Approach

Add 4 new test files, no `conftest.py` needed. Each module gets its own test file. External dependencies (YouTube API, yt-dlp) are mocked. Database tests use in-memory SQLite with the real `schema.sql`.

---

## Step 1: `tests/test_schema.py` (trivial, ~10 lines source)

Test `schema.py` — both functions, using in-memory SQLite.

- `test_init_schema_creates_tables`: call `init_schema(conn)` on in-memory conn, verify `channel`, `video`, `transcript_chunk` tables exist via `SELECT name FROM sqlite_master WHERE type='table'`
- `test_init_schema_idempotent`: call `init_schema` twice, verify no errors
- `test_load_schema_returns_sql`: verify `_load_schema()` returns a string containing "CREATE TABLE"

**Coverage gain**: `schema.py` 0% → 100% (+10 lines)

---

## Step 2: `tests/test_db.py` (44 lines source, most impactful)

Test all 8 functions in `db.py` using an in-memory libSQL/SQLite connection.

**Fixture**: a helper that creates an in-memory connection, runs `init_schema()`, and returns it. Each test function receives a fresh DB.

Tests:
- `test_upsert_channel_returns_id`: insert a channel, assert returned id is an int > 0
- `test_upsert_channel_on_conflict_updates`: insert same URL twice with different titles, verify title changed
- `test_upsert_video_returns_id`: insert a video, verify returned id
- `test_upsert_video_on_conflict_updates`: insert same youtube_str_id twice, verify status changed
- `test_replace_chunks_inserts`: insert 3 chunks, verify they exist in DB
- `test_replace_chunks_delete_existing`: insert chunks, call replace again with `delete_existing=True`, verify old ones gone
- `test_replace_chunks_empty_list`: call with empty list, no error
- `test_video_exists_true`: insert video, assert `video_exists()` returns True
- `test_video_exists_false`: assert returns False for unknown id
- `test_find_video_channel_found`: insert channel + video, assert tuple returned
- `test_find_video_channel_not_found`: assert None returned
- `test_get_channel_url_found`: insert channel, assert URL returned
- `test_get_channel_url_not_found`: assert None returned
- `test_search_chunks`: insert channel → video → chunks, run FTS search, verify results

**Coverage gain**: `db.py` 0% → 100% (+44 lines)

---

## Step 3: `tests/test_config.py` (26 lines source)

Test `load_channels()` with temporary YAML files.

Tests:
- `test_load_channels_basic`: write a YAML with defaults + 2 channels, verify correct ChannelSpec values
- `test_load_channels_no_url_skipped`: channel entry with no `url` key is skipped
- `test_load_channels_defaults_applied`: channel without `max_videos` gets the default
- `test_load_channels_owner_orientation`: verify optional fields pass through

**Coverage gain**: `config.py` 46.2% → 100% (+14 lines)

---

## Step 4: `tests/test_youtube_api.py` (173 lines source, pure functions first)

Test pure utility functions without mocking, then test API-calling functions with mocked `youtube` client.

**Pure function tests** (no mocks):
- `test_parse_iso_duration_pt1h2m3s`: "PT1H2M3S" → 3723
- `test_parse_iso_duration_pt5m`: "PT5M" → 300
- `test_parse_iso_duration_pt30s`: "PT30S" → 30
- `test_parse_iso_duration_empty`: "" → None
- `test_parse_iso_duration_not_pt`: "P1D" → None
- `test_parse_iso_duration_zero`: "PT0S" → None
- `test_iso_to_yyyymmdd_valid`: "2025-01-15T10:30:00Z" → "20250115"
- `test_iso_to_yyyymmdd_empty`: "" → None
- `test_iso_to_yyyymmdd_invalid`: "not-a-date" → None
- `test_extract_channel_ref_uc_id`: "/channel/UCxxxxx..." → ("id", "UCxxxxx...")
- `test_extract_channel_ref_handle`: "youtube.com/@HandleName" → ("handle", "@HandleName")
- `test_extract_channel_ref_bare_handle`: "@Someone" → ("handle", "@Someone")
- `test_extract_channel_ref_plain_name`: "SomeChannel" → ("handle", "@SomeChannel")
- `test_extract_channel_ref_search`: "youtube.com/c/something" → ("query", "something")
- `test_extract_channel_ref_strips_trailing_slash`: handle with trailing slash

**Mocked API tests** (mock `googleapiclient.discovery.build`):
- `test_resolve_channel_id_by_id`: mock `channels().list().execute()` returning items, verify `(id, title)` returned
- `test_resolve_channel_id_by_handle`: mock handle resolution path
- `test_resolve_channel_id_by_search`: mock search fallback
- `test_resolve_channel_id_not_found`: mock empty items, verify ValueError
- `test_list_videos`: mock channels + playlists + videos APIs, verify correct dict structure
- `test_list_videos_empty_channel`: mock empty channel response, verify `[]`
- `test_process_playlist_item`: pass a crafted item dict, verify it appends to video_ids/video_meta
- `test_process_playlist_item_cutoff_reached`: verify returns True when cutoff date exceeded
- `test_fetch_playlist_videos`: mock multi-page pagination, verify video_ids collected
- `test_fetch_video_details`: mock videos().list(), verify duration/title parsing

**Coverage gain**: `youtube_api.py` 0% → ~85-90% (~150+ lines)

---

## Step 5: `tests/test_subs.py` (67 lines source)

Test `_choose_track()` (pure logic) and `_extract_meta()` (pure function) directly. Mock yt-dlp for `_do_download` / `download_srt` integration paths.

**Pure function tests** (no mocks):
- `test_choose_track_fr_manual`: `{"fr", "en"}` → ("fr", "manual")
- `test_choose_track_fr_orig_manual`: `{"fr-orig"}` → ("fr-orig", "manual")
- `test_choose_track_fr_auto`: `{"fr"}` auto set → ("fr", "auto")
- `test_choose_track_fr_orig_auto`: `{"fr-orig"}` auto set → ("fr-orig", "auto")
- `test_choose_track_no_french`: `{"en"}` → (None, None)
- `test_choose_track_manual_preferred_over_auto`: fr in both sets → manual
- `test_extract_meta`: pass a dict with title/upload_date/etc., verify output dict keys

**Mocked yt-dlp tests**:
- `test_download_srt_no_subs`: mock `yt_dlp.YoutubeDL` to return info with no FR subtitles → returns (None, None, None, meta)
- `test_download_srt_success`: mock to return fr subtitles with a temp .srt file
- `test_download_srt_rate_limited`: mock `_run_with_retry` to raise DownloadError with "429", verify retry → RateLimitedError
- `test_base_opts`: verify `_base_opts()` returns correct dict structure

**Coverage gain**: `subs.py` 0% → ~80-90% (~55+ lines)

---

## Step 6: `tests/test_cli.py` (173 lines in `__init__.py`)

Test CLI commands and helper functions using Click's test runner.

**Unit tests** (no Click):
- `test_extract_video_id_valid`: "https://youtube.com/watch?v=abc12345678" → "abc12345678"
- `test_extract_video_id_short`: "https://youtu.be/abc12345678" → "abc12345678"
- `test_extract_video_id_invalid`: "https://example.com" → None
- `test_print_dry_run_summary`: mock logger, call function, verify output lines

**Click CLI tests** (using `click.testing.CliRunner`):
- `test_cli_ingest_missing_config`: run `ingest` with nonexistent config → exit code 1
- `test_cli_ingest_dry_run`: provide a temp config with a channel, mock `_resolve_channel` and `_fetch_videos` → dry-run output
- `test_cli_ingest_force_all_cancels`: test that force-all + user saying "no" → exit 0

**Mocked orchestration tests** (mock db, youtube_api, subs):
- `test_resolve_channel_success`: mock `resolve_channel_id` + `upsert_channel`, verify tuple returned
- `test_resolve_channel_failure`: mock `resolve_channel_id` to raise, verify None returned
- `test_fetch_videos_success`: mock `list_videos`, verify list returned
- `test_fetch_videos_error`: mock `list_videos` to raise, verify empty list returned
- `test_process_videos_dry_run_new`: verify new_count incremented for unseen video
- `test_process_videos_dry_run_existing`: verify existing_count incremented
- `test_download_and_store_no_subs`: mock `download_srt` returning None, verify upsert_video called with status="no_subs"
- `test_download_and_store_success`: mock full flow, verify chunks stored

**Coverage gain**: `__init__.py` 20.2% → ~65-75% (+75-90 lines)

---

## Step 7: `tests/test_logging_config.py` (36 lines source)

Simple test for `setup_logging()`:
- `test_setup_logging_creates_handlers`: call with a temp dir, verify logger has console + file handler
- `test_setup_logging_idempotent`: call twice, verify only 2 handlers (not duplicated)

**Coverage gain**: `logging_config.py` → 100% (+36 lines, if coverage includes it)

---

## Expected Coverage After Implementation

| Module | Before | After | Gain |
|--------|--------|-------|------|
| `srt.py` | 97.5% | 97.5% | — |
| `chunking.py` | 93.6% | 93.6% | — |
| `config.py` | 46.2% | 100% | +14 |
| `schema.py` | 0% | 100% | +10 |
| `db.py` | 0% | 100% | +44 |
| `youtube_api.py` | 0% | ~85% | +147 |
| `subs.py` | 0% | ~85% | +57 |
| `__init__.py` | 20.2% | ~70% | +86 |
| `logging_config.py` | 0% | 100% | +36 |
| **Total** | **174/547 (31.8%)** | **~450/547 (~82%)** | **+276 lines** |

---

## Execution Order

1. `test_schema.py` — quick win, validates DB infra
2. `test_db.py` — highest impact (44 lines, enables all integration tests)
3. `test_config.py` — quick pure-function tests
4. `test_youtube_api.py` — pure utils first, then mocked API
5. `test_subs.py` — pure logic + mocked yt-dlp
6. `test_cli.py` — orchestration + Click commands
7. `test_logging_config.py` — simple logging setup

## Conventions (from AGENTS.md)

- All test functions annotated with proper types
- Run `pyright` after implementation: `uv run pyright tests/`
- Cognitive complexity ≤ 15 per function
- No DB schema changes needed — tests use existing `schema.sql`
- Run full suite with: `uv run pytest --cov=lucas_v2 --cov-report=term-missing`
