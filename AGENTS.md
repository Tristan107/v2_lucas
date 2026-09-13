# AGENTS.md — Lucas v2

## 1. Project Overview

**Lucas v2** is a political monitoring tool that ingests YouTube video transcripts and makes them searchable. Built ahead of the 2027 French presidential election to track political discourse across YouTube channels.

### Purpose
- Automate collection of French-language transcripts from political YouTube channels
- Store them in a searchable database (Turso/libSQL with FTS5)
- Provide a web UI (Streamlit) to search and explore transcripts with timestamps

### Target User
- Personal tool for Tristan (veille politique)
- Single-user deployment, not a multi-tenant SaaS

### What's Next
- **Sondages page**: Placeholder in UI (render_sondages_page) — polling data aggregation planned
- Potentially more data sources beyond YouTube transcripts

### Success Criteria
- Ingestion pipeline reliably downloads and stores transcripts
- FTS5 search returns relevant results with correct timestamps
- Streamlit UI renders correctly with pagination and YouTube links

---

## 2. Architecture Overview

```
CLI (click)                           Streamlit UI
    │                                       │
    ▼                                       ▼
ingest/config.py → ingest/youtube_api.py  ui/query.py (helpers)
                → ingest/subs.py (yt-dlp) ui/db_search.py (FTS queries)
                → ingest/srt.py (parsing) ui/app.py (rendering)
                → ingest/chunking.py
                → db/operations.py (Turso)
```

### Package Structure
- **`db/`** — Database layer (connection, schema, operations)
- **`ingest/`** — Data ingestion pipeline (YouTube → SRT → chunks)
- **`ui/`** — Streamlit web interface

### Data Flow (Ingestion)
1. `channels.yaml` → list of YouTube channels to scrape
2. `ingest/youtube_api.py` → resolve @handle → channelId, fetch video metadata
3. `ingest/subs.py` → download SRT via yt-dlp (French subtitles)
4. `ingest/srt.py` → parse SRT cues into (start_s, end_s, text)
5. `ingest/chunking.py` → group cues into chunks (sentence-boundary, max 128 tokens)
6. `db/operations.py` → upsert into Turso (channel, video, transcript_chunk tables)

### Search Flow
1. Streamlit UI → user enters query
2. `ui/query.py` → build_match_query() converts to FTS5 syntax (AND, wildcards)
3. `ui/db_search.py` → search_videos() / search_video_chunks() → BM25 ranking
4. Results displayed with timestamps linking to YouTube

---

## 3. Key Technical Decisions

| Decision | Implementation | Rationale |
|----------|---------------|-----------|
| Database | Turso (libSQL) + FTS5 | Serverless, SQLite-compatible, native FTS |
| Chunking | Sentence-boundary + 128 tokens max | Balance context vs search precision |
| Rate limiting | 10s inter-video + jitter + 429 backoff | YouTube API quotas, avoid 429 |
| Idempotency | Upserts everywhere | Safe re-runs, no duplicates |
| Tokenizer | MiniLM (sentence-transformers) | Quality chunking; fallback to whitespace |
| FTS tokenizer | unicode61 remove_diacritics 2 | French accent handling (déjà matches deja) |

---

## 4. Development Workflow

```bash
# Setup
uv sync

# Ingestion
uv run lucas-v2 ingest -c channels.yaml              # normal run
uv run lucas-v2 ingest -c channels.yaml --dry-run    # preview only
uv run lucas-v2 ingest -c channels.yaml --force-all  # re-scrape all
uv run lucas-v2 ingest -c channels.yaml --url "..."  # re-scrape single video

# Streamlit UI
uv run streamlit run streamlit_app.py

# Tests
uv run pytest tests/ -v

# Type checking
uv run pyright
```

---

## 5. Constraints & Rules

1. **Package manager**: Always `uv`, never pip
2. **Type checking**: pyright strict — zero warnings/errors allowed
3. **Cognitive complexity**: ≤ 15 per function (Sonarqube compliance)
4. **DB changes**: Propose one-shot SQL script manually; no Python migration code
5. **Python version**: ≥ 3.11 (target 3.12 for mypy)
6. **Testing**: New features require tests; maintain coverage

---

## 6. Code Conventions

- **Language**: French for all user-facing strings, log messages, comments
- **Type annotations**: Mandatory on all function signatures and key variables
- **Imports**: `from __future__ import annotations` at top of every file
- **Logging**: Use `logging.getLogger("lucas_v2")`, never print()
- **Errors**: Custom exceptions (RateLimitedError, AbortIngestion)
- **Config**: `.env` for secrets (never committed), `channels.yaml` for channel list
- **DB pattern**: DbConn wrapper handles Turso stream expiry with auto-reconnect

---

## 7. Database Schema

```sql
channel (id, channel_url UNIQUE, channel_id, title, orientation, owner, added_at)
video (id, fk_channel_id FK, youtube_str_id UNIQUE, title, upload_date, duration_s,
       sub_lang, sub_kind, status ['ok'|'no_subs'|'error'], error, scraped_at)
transcript_chunk (id, fk_video_id FK CASCADE, seq_no, start_s, end_s, text, tokens,
                  UNIQUE(fk_video_id, seq_no))
transcript_chunk_fts (text)  -- FTS5 virtual table, auto-synced via triggers
```

### Status Values
- `ok` — transcript downloaded and stored
- `no_subs` — no French subtitles available
- `error` — download failed (error message in `error` column)

### Exemple de requête FTS5

```sql
SELECT tc.seq_no, tc.start_s, tc.end_s,
       snippet(transcript_chunk_fts, 0, '<b>', '</b>', '…', 12) AS extrait,
       tc."text",
       bm25(transcript_chunk_fts) AS rank,
       'https://www.youtube.com/watch?v=' || v.youtube_str_id || '&t=' || tc.start_s AS video_link,
       v.title
FROM transcript_chunk_fts
JOIN transcript_chunk tc ON tc.id = transcript_chunk_fts.rowid
JOIN video v ON v.id = tc.fk_video_id
WHERE transcript_chunk_fts MATCH 'boulot*'
ORDER BY rank
LIMIT 20;
```

Le lien `video_link` produit une URL directe vers le début du chunk
(ex. `https://www.youtube.com/watch?v=abc123&t=95`).

---

## 8. File Reference

| File | Purpose |
|------|---------|
| `src/lucas_v2/__init__.py` | CLI entry point, ingest command orchestration |
| `src/lucas_v2/db/__init__.py` | Chunk dataclass definition |
| `src/lucas_v2/db/connection.py` | Turso connection, DbConn wrapper (auto-reconnect) |
| `src/lucas_v2/db/operations.py` | Upserts, FTS search, batch queries |
| `src/lucas_v2/db/schema.py` | Schema initialization (runs schema.sql) |
| `src/lucas_v2/db/schema.sql` | DDL: tables, FTS5, triggers |
| `src/lucas_v2/ingest/config.py` | YAML parsing, ChannelSpec dataclass |
| `src/lucas_v2/ingest/youtube_api.py` | YouTube Data API v3 (resolve channel, list videos) |
| `src/lucas_v2/ingest/subs.py` | yt-dlp SRT download, rate limit handling |
| `src/lucas_v2/ingest/srt.py` | SRT parsing → Cue objects |
| `src/lucas_v2/ingest/chunking.py` | Sentence grouping, token counting (MiniLM) |
| `src/lucas_v2/logging_config.py` | Logging setup |
| `src/lucas_v2/ui/query.py` | FTS query builder, date/URL formatting |
| `src/lucas_v2/ui/db_search.py` | Video/chunk search queries |
| `src/lucas_v2/ui/app.py` | Streamlit page rendering |
| `streamlit_app.py` | Streamlit entry point, routing |

---

## 9. Environment & Configuration

### `.env` (secrets, never committed)
```
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...
YOUTUBE_API_KEY=...
```

### `channels.yaml` (channel list)
```yaml
defaults:
  max_videos: 1
  since_days: null
  lang: fr
channels:
  - url: https://www.youtube.com/@ChannelName
  - url: https://www.youtube.com/@OtherChannel
    max_videos: 3
    since_days: 30
```

---

## 10. Turso Limits (Free Tier)

- Total Transcript Time: ~138,500,000 seconds (~38,470 hours)
- Total Videos: ~125,000 videos
- Largest channel (Mélenchon): ~2007 videos, ~1110h content → well within limits
