# Plan: Improve AGENTS.md

## Goal

Rewrite `AGENTS.md` to be a comprehensive, self-contained reference for AI agents working on this project. The document should allow an agent to understand the project's purpose, architecture, constraints, and conventions **without needing to explore the codebase** on every new session.

---

## Proposed Structure

### Chapter 1: Project Overview
**Owner: YOU (Tristan)** — Intentions not obvious from code

This chapter should cover:
- **What is this project?** (YouTube transcript ingestion for political monitoring)
- **Who is it for?** (Your own use case — veille politique 2027)
- **What problem does it solve?** (Automated collection + searchable archive)
- **What are the "Sondages" section and future plans?** (Appears in UI but not implemented)

> ⚠️ This is the main chapter only you can write. The code shows *how*, not *why*.

---

### Chapter 2: Architecture Overview
**Owner: ME (agent)** — Derivable from code

```
CLI (click)                    Streamlit UI
    │                               │
    ▼                               ▼
config.py → youtube_api.py      ui/query.py (helpers)
          → subs.py (yt-dlp)    ui/db_search.py (FTS queries)
          → srt.py (parsing)    ui/app.py (rendering)
          → chunking.py
          → db.py (Turso)
```

- Entry points: `lucas-v2` CLI and `streamlit_app.py`
- Data flow: channels.yaml → YouTube API → SRT download → parse → chunk → Turso
- Search flow: Streamlit → FTS5 query → display with timestamps

---

### Chapter 3: Key Technical Decisions
**Owner: ME (agent)** — Derivable from code

| Decision | Implementation | Why |
|----------|---------------|-----|
| Database | Turso (libSQL) + FTS5 | Serverless, SQLite-compatible, FTS support |
| Chunking | Sentence-boundary + 128 tokens max | Balance between context and search precision |
| Rate limiting | 10s inter-video + jitter + 429 backoff | YouTube API quotas |
| Idempotency | Upserts everywhere | Safe re-runs without duplicates |
| Tokenizer | MiniLM fallback to whitespace | Quality chunking without heavy deps |

---

### Chapter 4: Development Workflow
**Owner: ME (agent)** — Derivable from code + pyproject.toml

```bash
# Setup
uv sync

# Run ingestion
uv run lucas-v2 ingest -c channels.yaml
uv run lucas-v2 ingest -c channels.yaml --dry-run
uv run lucas-v2 ingest -c channels.yaml --force-all
uv run lucas-v2 ingest -c channels.yaml --url "https://..."

# Run Streamlit UI
uv run streamlit run streamlit_app.py

# Tests
uv run pytest tests/ -v

# Type checking
uv run pyright
```

---

### Chapter 5: Constraints & Rules
**Owner: ME (agent)** — From current AGENTS.md + pyproject.toml

1. **Package manager**: Always use `uv`, never pip
2. **Type checking**: pyright strict — zero warnings/errors allowed
3. **Cognitive complexity**: ≤ 15 per function (Sonarqube)
4. **DB changes**: Propose SQL script, don't generate Python migration code
5. **Python version**: ≥ 3.11 (target 3.12 for mypy)
6. **Testing**: New features require tests; check coverage

---

### Chapter 6: Code Conventions
**Owner: ME (agent)** — Derivable from codebase patterns

- **Language**: French for all user-facing strings, logs, comments
- **Type annotations**: Mandatory on all function signatures and key variables
- **Import style**: `from __future__ import annotations` at top of every file
- **Logging**: Use `logging.getLogger("lucas_v2")`, not print
- **Error handling**: Specific exceptions (RateLimitedError, AbortIngestion)
- **Config**: `.env` for secrets (never committed), `channels.yaml` for channel list

---

### Chapter 7: Database Schema Reference
**Owner: ME (agent)** — From schema.sql

```sql
-- Tables
channel (id, url, youtube_channel_id, title, orientation, owner)
video (id, fk_channel_id, youtube_str_id, title, upload_date, duration_s, sub_lang, sub_kind, status, error_msg)
transcript_chunk (id, fk_video_id, seq_no, start_s, end_s, text, tokens)

-- FTS
transcript_chunk_fts (text)  -- FTS5 virtual table

-- Status enum
'ok' | 'no_subs' | 'error'
```

---

### Chapter 8: File Reference
**Owner: ME (agent)** — From codebase exploration

| File | Purpose |
|------|---------|
| `src/lucas_v2/__init__.py` | CLI entry point, ingest command |
| `src/lucas_v2/config.py` | YAML parsing, ChannelSpec |
| `src/lucas_v2/youtube_api.py` | YouTube Data API v3 client |
| `src/lucas_v2/subs.py` | yt-dlp SRT download |
| `src/lucas_v2/srt.py` | SRT parsing → cues |
| `src/lucas_v2/chunking.py` | Sentence grouping, token counting |
| `src/lucas_v2/db.py` | Turso connection, upserts |
| `src/lucas_v2/schema.py` | Schema initialization |
| `src/lucas_v2/schema.sql` | DDL definitions |
| `src/lucas_v2/logging_config.py` | Logging setup |
| `src/lucas_v2/ui/query.py` | Search helpers (AND, URL, hhmmss) |
| `src/lucas_v2/ui/db_search.py` | FTS query builders |
| `src/lucas_v2/ui/app.py` | Streamlit page rendering |
| `streamlit_app.py` | Streamlit entry point |

---

### Chapter 9: Environment & Configuration
**Owner: ME (agent)** — From .env.example + channels.yaml.example

```bash
# .env (secrets, never committed)
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...
YOUTUBE_API_KEY=...

# channels.yaml (channel list)
defaults:
  max_videos: 1
  since_days: null
  lang: fr
channels:
  - url: https://www.youtube.com/@ChannelName
    max_videos: 3
    since_days: 30
```

---

## What YOU Must Write

Only **Chapter 1: Project Overview** requires your input. Specifically:

1. **Project purpose**: Why did you build this? What's the end goal?
2. **Target audience**: Is this just for you, or will others use it?
3. **Future plans**: What's next? (Sondages page, other data sources?)
4. **Context**: Why YouTube transcripts? Why political monitoring?
5. **Success criteria**: How do you know the project is working well?

Everything else can be derived from the codebase.

---

## Implementation Steps

1. **You write**: Chapter 1 (Project Overview) with your objectives/intentions
2. **I write**: Chapters 2-9 based on codebase analysis
3. **We review**: Together, ensure nothing is missing
4. **Replace**: Overwrite current AGENTS.md with new version

---

## Estimated Size

Current AGENTS.md: 5 lines
Proposed AGENTS.md: ~150-200 lines

This is a reasonable size — detailed enough to be useful, concise enough to not waste context window.
