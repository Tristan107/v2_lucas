# Refactor: table + column naming conventions

## 1. Changes

### Table renames (remove plural)
| Current | New |
|---|---|
| `channels` | `channel` |
| `videos` | `video` |
| `transcript_chunks` | `transcript_chunk` |

### Foreign key renames (`fk_` prefix + `_id` suffix)
| Table | Current column | New column | Target |
|---|---|---|---|
| `video` | `channel_row_id` | `fk_channel_id` | `channel(id)` |
| `transcript_chunk` | `video_id` | `fk_video_id` | `video(video_id)` |

### Primary key renames (all surrogate `id`)
| Table | Current PK | New PK |
|---|---|---|
| `channel` | `id` | `id` (unchanged) |
| `video` | `video_id` TEXT (natural) | `id` INTEGER AUTOINCREMENT (surrogate) + `youtube_id` TEXT UNIQUE (ex-`video_id`) |
| `transcript_chunk` | `id` | `id` (unchanged) |

### Foreign key retarget (`video.id` surrogate)
| Table | Column | Type change | Target |
|---|---|---|---|
| `transcript_chunk` | `fk_video_id` | TEXT → INTEGER | `video(id)` (was `video(video_id)`) |

### Other column renames (preserve YouTube semantics)
- `channel.channel_id` (TEXT, YouTube `UC...`) — keep as-is (not an FK, just an attribute).

### Index renames
| Current | New |
|---|---|
| `idx_videos_channel` | `idx_video_fk_channel` |
| `idx_channels_ytid` | `idx_channel_ytid` |

## 2. Files to modify

- `src/lucas_v2/db.py` — schema DDL, `init_schema()` migration, all SQL queries + function signatures
- `src/lucas_v2/__init__.py` — `upsert_video()` calls (already passes `channel_row_id` positionally; no signature change needed, just DB column names)

## 3. Migration strategy

Same approach as previous `channel_id → channel_row_id`:
- `init_schema()` runs `CREATE TABLE IF NOT EXISTS` with new names first (works for fresh DBs).
- Then detect old table/column names via `PRAGMA table_info()` / `sqlite_master` and `ALTER TABLE RENAME` as needed.
- SQLite supports `ALTER TABLE RENAME COLUMN` (≥ 3.25) and `ALTER TABLE RENAME TO` — both work on Turso.

### Migration steps in `init_schema()`:
1. Rename tables if old names exist: `channels → channel`, `videos → video`, `transcript_chunks → transcript_chunk`.
2. Rename columns if old names exist: `video.channel_row_id → fk_channel_id`, `transcript_chunk.video_id → fk_video_id`.
3. Migration V2 (rebuild, SQLite can't alter a PK in place): if `video` has no `id` column, rebuild `video` (`video_id TEXT → youtube_id`, new `id` auto) and `transcript_chunk` (join on `youtube_id` to remap `fk_video_id` TEXT → INTEGER), with `PRAGMA foreign_keys=OFF` during rebuild.
4. Recreate indexes with new names.
5. Drop old redundant indexes.

## 4. SQL query updates

All hardcoded table/column references in `db.py` must be updated:
- `upsert_channel()`: `channels` → `channel`
- `upsert_video()`: `videos` → `video`, `channel_row_id` → `fk_channel_id`, `video_id` → `youtube_id` + `ON CONFLICT(youtube_id)`, returns `video.id`; new `get_video_id()` helper
- `replace_chunks()` / `video_exists*()`: keyed by surrogate `video.id` / `youtube_id` respectively
- `replace_chunks()`: `transcript_chunks` → `transcript_chunk`
- `video_exists_ok()`: `videos` → `video`
- `video_exists()`: `videos` → `video`

## 5. FTS5 plein-texte sur `transcript_chunk.text`

- Table externe `transcript_chunk_fts USING fts5(text, content='transcript_chunk', content_rowid='id', tokenize="unicode61 remove_diacritics 2")` (insensible aux accents : `deja` matche `déjà`).
- 3 triggers (`trg_chunk_fts_ai/ad/au`) : `replace_chunks()` (DELETE+INSERT) reste synchro sans changement de code.
- Backfill via flag `meta(k='fts_chunk_v1')` (pas de comparaison COUNT : sur table externe, COUNT lit le contenu même si l'index est vide). Rebuild V2 drop le FTS + le flag pour forcer le rebuild (les rowids changent).
- `search_chunks(conn, query, limit=20)` : syntaxe FTS5 (`mots`, `"phrase"`, `prefix*`), retourne chunks + `snippet` (`<b>`), `bm25` rank, `youtube_id`, `video_title`, triés par pertinence.
- Vérifié : basic/phrase/préfixe/sans-accents, resync après replace, backfill pre-FTS, rebuild V2+FTS, re-init idempotent, 8/8 pytest. Appliqué sur Turso (tables vides : index créé, flag posé).

## 6. Drop `video.channel_url` + `video.youtube_id`

Both denormalized/derived columns removed.

| Column | Reason removed |
|---|---|
| `channel_url` | Redundant with `channel.channel_url` via `fk_channel_id` FK. `ALTER TABLE DROP COLUMN` works (no UNIQUE constraint). |
| `youtube_id` | Redundant with `video_url` (`https://www.youtube.com/watch?v=<id>`). SQLite refuses `DROP COLUMN` on a UNIQUE column → V4 rebuild (copy without `youtube_id`). |

### Code changes
- `db.py` DDL: neither column in `CREATE TABLE video`. `ON CONFLICT(video_url)` replaces `ON CONFLICT(youtube_id)`.
- `upsert_video()`: `youtube_id` + `channel_url` params removed. Returns `video.id`.
- `get_video_id()`: removed (caller uses `upsert_video()` return value).
- `video_exists()` / `video_exists_ok()`: keyed on `video_url`.
- `search_chunks()`: YouTube ID extracted in SQL via `substr(video_url, instr(video_url, 'v=') + 2)`.
- `__init__.py`: `vid_id` only used for display now (`click.echo`); `video_exists()` and `upsert_video()` keyed on `vid_url`.
- Migration V3: `ALTER TABLE video DROP COLUMN channel_url` (no UNIQUE).
- Migration V4: rebuild table without `youtube_id` (SQLite can't drop UNIQUE column in place). FK `transcript_chunk.fk_video_id` not affected (same rowids).

## 7. Verification

1. `uv run pytest tests/ -v` — no behavioral change expected.
2. Fresh DB: `init_schema()` creates tables with new names, correct columns, correct indexes.
3. Old DB migration: tables renamed, columns renamed, data preserved, queries still work.
4. `SELECT sql FROM sqlite_master WHERE type='table'` confirms new names.
5. `PRAGMA foreign_key_list(video)` confirms FK references.
