# Plan — Sample FTS Query with Timestamped YouTube Link in README.md

## 1. Goal
Add the user-provided FTS5 sample query to `README.md`, with one change:
replace bare `v.video_url` by a SQLite concatenation that produces a
copy-paste-ready deep link jumping straight to the chunk start
(`<video_url>&t=<start_s>`).

Requested base query:
```sql
SELECT tc.seq_no, tc.start_s, tc.end_s,
       snippet(transcript_chunk_fts, 0, '<b>', '</b>', '…', 12) AS extrait,
       tc."text",
       bm25(transcript_chunk_fts) AS rank,
       v.video_url , v.title
FROM transcript_chunk_fts
JOIN transcript_chunk tc ON tc.id = transcript_chunk_fts.rowid
JOIN video v ON v.id = tc.fk_video_id
WHERE transcript_chunk_fts MATCH 'boulot*'
ORDER BY rank
LIMIT 20;
```

## 2. Findings (codebase analysis)
- `README.md` (105 lines) currently has **no** sample-query / FTS section.
  Sections: Fonctionnement, Prérequis, Installation, Configuration,
  Lancement, Tests, Structure. Best insertion point: new section after
  `Lancement` (or after `Tests`), e.g. `## Exemple de recherche plein-texte`.
- Schema (`src/lucas_v2/schema.py`):
  - `video(video_url TEXT NOT NULL UNIQUE, title TEXT, ...)`
  - `transcript_chunk(fk_video_id, seq_no, start_s INTEGER NOT NULL, end_s INTEGER NOT NULL, text, ...)`
  - FTS5 table `transcript_chunk_fts(text, content='transcript_chunk', content_rowid='id')` + triggers — matches the query's `JOIN ... ON tc.id = transcript_chunk_fts.rowid` and `snippet(...)/bm25(...)` usage.
- URL format (`src/lucas_v2/youtube_api.py:168`):
  `video_url = f"https://www.youtube.com/watch?v={vid_id}"` — always contains
  `?v=`, so appending `&t=<seconds>` is safe (no need for `?t=` case).
- `start_s` is `INTEGER` seconds (see `srt.py` parsing, `chunking.py`).
  SQLite implicitly casts INTEGER → TEXT in `||` concatenation, so no explicit
  `CAST` is strictly required.
- Critical SQLite pitfall: string concatenation is `||`, **not** `+`
  (`+` is arithmetic in SQLite). The user's pseudo-code
  `v.video_url + "&t=" + tc.start_s` must be translated to
  `v.video_url || '&t=' || tc.start_s`.

## 3. Proposed change (README.md only)
Add a new section, e.g.:

```markdown
## Exemple de recherche plein-texte

```sql
SELECT tc.seq_no, tc.start_s, tc.end_s,
       snippet(transcript_chunk_fts, 0, '<b>', '</b>', '…', 12) AS extrait,
       tc."text",
       bm25(transcript_chunk_fts) AS rank,
       v.video_url || '&t=' || tc.start_s AS video_link, v.title
FROM transcript_chunk_fts
JOIN transcript_chunk tc ON tc.id = transcript_chunk_fts.rowid
JOIN video v ON v.id = tc.fk_video_id
WHERE transcript_chunk_fts MATCH 'boulot*'
ORDER BY rank
LIMIT 20;
```
```

Result example: `https://www.youtube.com/watch?v=abc123&t=95` — pasting in a
browser starts playback at 95 s.

### Variant to consider (optional, to confirm with user)
YouTube also accepts `&t=95s` (explicit seconds suffix, canonical form).
Variant: `v.video_url || '&t=' || tc.start_s || 's' AS video_link`.
Recommendation: keep the simple form from the request (`'&t=' || start_s`,
no `s`) for fidelity; mention the `s`-suffix only if the user wants it.
No `CAST(tc.start_s AS TEXT)` needed, but harmless if added for clarity.

## 4. Implementation steps (build mode)
1. Read `README.md` tail (lines ~68–105) to pick exact anchor (after
   `Lancement`, before `Tests`).
2. Insert new `## Exemple de recherche plein-texte` section with the `sql`
   fenced block above (single edit, no other files touched).
3. Validate SQL syntax offline without touching Turso:
   `sqlite3 :memory:` → create minimal `video` + `transcript_chunk` tables
   (or run `init_schema` from `schema.py`) → run the `SELECT` with a dummy
   `MATCH` or at least `EXPLAIN QUERY PLAN` to confirm `||` expression parses.
   Full FTS execution requires FTS5 + data; parse-check is sufficient.
4. Verify rendered Markdown (fence balance, `sql` tag).
5. `git status` / `git diff` — confirm only `README.md` changed.

## 5. Acceptance criteria
- `README.md` contains the exact user query with `v.video_url` replaced by
  `v.video_url || '&t=' || tc.start_s AS video_link`.
- Query uses `||`, single-quoted `'&t='`, no `+`.
- Table/column names unchanged and consistent with `schema.py`.
- No code, schema, or config files modified.

## 6. Out of scope
- Changing `db.py:search_chunks()` to also return a timestamped link.
- Backfilling data, `CAST` migration, or `youtu.be` short-URL handling.
- Adding `s` suffix unless user confirms.

## 7. Risks / notes
- None functionally — docs-only change. Only risk is copy-paste SQL typo;
  mitigated by step 3 parse-check.
