# Plan — Fix `since_days` crash when `max_videos: null`

## 1. Bug summary

Command:
`uv run lucas-v2 ingest -c channels.yaml` with:

```yaml
defaults:
  max_videos: null
  since_days: 30
  lang: "fr"
```

Result for every channel:
`ERREUR listing vidéos : '<' not supported between instances of 'int' and 'NoneType'`, 0 videos.

Expected: `max_videos: null` = no count limit, `since_days: 30` is the only filter.

## 2. Root cause (verified by code reading)

File: `src/lucas_v2/youtube_api.py`

- `list_videos(channel_id, max_videos: int = 1, ...)` line 192 types `max_videos` as `int`, but `config.py` passes `None` through.
- `_fetch_playlist_videos(youtube, uploads_id, max_videos: int, cutoff)` line 140-149:
  ```python
  batch_size = 50 if cutoff else min(max_videos, 50)  # line 147 → min(int, None) or min(None,50)
  while fetched < max_videos:                          # line 149 → int < None
  ```
  `min()` internally does `<` comparison → exact error message reported.
  Line 157 `if fetched >= max_videos` would also crash.
- Lines 218/220 `video_ids[:max_videos]` / `results[:max_videos]` happen to work with `None` (slice-to-end), so they mask the intent but are not the crash site.

File: `src/lucas_v2/config.py`

- Line 12 `ChannelSpec.max_videos: int` should be `int | None`.
- Line 24 `d_max_videos: int = defaults.get("max_videos", 1)` same typing error; value `None` flows to `ChannelSpec` line 37 unchanged.
- No validation: `max_videos: null + since_days: null` (unbounded) currently allowed; must still terminate on `nextPageToken is None`.

Secondary bug:
- Line 209 `if since_days:` treats `0` as disabled. Should be `if since_days is not None:`.

## 3. Scope / non-goals

- In scope: allow `max_videos: int | None` end-to-end (config → `list_videos` → `_fetch_playlist_videos` → slicing).
- Out of scope: DB changes (none needed), CLI flag changes, quota optimization, changing `channels.yaml` committed defaults.

## 4. Design decisions

1. **Semantics:** `max_videos=None` means unlimited count; filtering relies solely on `cutoff` (`since_days`) and/or playlist exhaustion (`nextPageToken is None`).
2. **Loop termination when both limits are `None`:** paginate until `nextPageToken is None`. No artificial cap (matches user expectation). Document quota risk in README note only if desired — do not add hidden cap.
3. **Keep complexity ≤15 (AGENTS.md / Sonar):** extract small helper `_reached_limit(fetched, max_videos)` instead of inline `None` checks in loop.
4. **Strong typing + pyright (AGENTS.md):** all touched signatures become `int | None`, run `pyright` after.

## 5. Implementation steps

### Step 1 — `src/lucas_v2/config.py`
- `ChannelSpec.max_videos: int` → `int | None`.
- `d_max_videos: int` → `int | None = defaults.get("max_videos", 1)`.
- No logic change; `ch.get("max_videos", d_max_videos)` already propagates `None` correctly.
- Verify explicit per-channel override still wins over defaults (existing behavior).

### Step 2 — `src/lucas_v2/youtube_api.py`
- Add helper (new, ~3 lines):
  ```python
  def _reached_limit(fetched: int, max_videos: int | None) -> bool:
      return max_videos is not None and fetched >= max_videos
  ```
- Change `_fetch_playlist_videos(... max_videos: int | None ...)`:
  - `batch_size = 50 if (cutoff is not None or max_videos is None) else min(max_videos, 50)`
  - `while True:` + break conditions, or `while max_videos is None or fetched < max_videos:` (prefer explicit helper to keep pyright strict happy).
  - Replace `if fetched >= max_videos: break` with `if _reached_limit(fetched, max_videos): break`.
- Change `list_videos(channel_id: str, max_videos: int | None = 1, since_days: int | None = None)`:
  - `if since_days is not None:` (instead of `if since_days:`) for cutoff computation.
  - Slicing: `ids = video_ids if max_videos is None else video_ids[:max_videos]` before `_fetch_video_details`; same for final `return results if max_videos is None else results[:max_videos]`.
- Keep `_fetch_next_page`, `_process_playlist_item`, `_fetch_video_details` untouched.

### Step 3 — Tests (TDD per `tdd-workflow` skill intent)
Add to `tests/test_youtube_api.py` (mocked `_get_client` pattern as existing `TestListVideos`):
1. `test_max_videos_none_with_cutoff`: 2 pages, old video triggers `cutoff_reached`; assert all recent videos returned, no exception, `playlistItems.list` called with `maxResults=50`.
2. `test_max_videos_none_no_cutoff_paginates_to_end`: 2 pages with `nextPageToken`, then `None`; assert all collected.
3. `test_max_videos_limit_still_respected`: regression, `max_videos=1` returns 1.
4. Optional: `test_since_days_zero` if `is not None` change is included.

Add to `tests/test_config.py`:
5. `test_load_channels_max_videos_null`: YAML `max_videos:` empty/`null`, `since_days: 30` → `spec.max_videos is None`, `spec.since_days == 30`.

### Step 4 — Verification
- `uv run pytest -q`
- `uv run pyright src/lucas_v2/youtube_api.py src/lucas_v2/config.py` (or `uvx pyright`; per AGENTS.md strong typing check). Must pass strict mode.
- Manual repro (requires `YOUTUBE_API_KEY`): temp YAML with `max_videos: null / since_days: 30`, `uv run lucas-v2 ingest -c <tmp> --dry-run` → no `ERREUR listing vidéos`, `Videos matching... > 0` for active channels.
- Check cognitive complexity ≤15 (new helper keeps `_fetch_playlist_videos` flat).

## 6. Risks / edge cases

- Both `max_videos: null` + `since_days: null` → full playlist scan; could be thousands of API calls on large channels. Acceptable per expected behavior; loop still ends on `nextPageToken is None`. Consider later: warning log or `--dry-run` first.
- `since_days: 0` now means “only videos from now onward” (empty) rather than disabled — correct with `is not None` check; document if needed.
- Negative `since_days` → future cutoff → zero results, no crash. No extra validation planned.

## 7. Files touched

- `src/lucas_v2/config.py` (2 type lines)
- `src/lucas_v2/youtube_api.py` (helper + 2 signatures + batch/loop/slice logic)
- `tests/test_youtube_api.py` (3–4 new tests)
- `tests/test_config.py` (1 new test)

No DB migration needed (no AGENTS.md one-shot SQL required).
