# Plan: Directory Restructure — `db/` and `ingest/`

## Goal

Reorganize `src/lucas_v2/` into logical subpackages:
- `db/` — database connection, schema, and operations
- `ingest/` — data ingestion pipeline (YouTube → SRT → chunks)
- `ui/` — Streamlit UI (already exists, no changes)
- `logging_config.py` — stays at root (shared utility)

---

## Target Structure

```
src/lucas_v2/
├── __init__.py              ← orchestration (update imports)
├── logging_config.py        ← stays (shared utility)
├── db/
│   ├── __init__.py          ← re-exports + Chunk dataclass
│   ├── connection.py        ← DbConn, connect(), _raw_connect()
│   ├── operations.py        ← upsert_*, replace_*, fetch_*, search_chunks
│   ├── schema.py            ← load_schema(), init_schema()
│   └── schema.sql           ← DDL (unchanged)
├── ingest/
│   ├── __init__.py          ← re-exports for convenience
│   ├── config.py            ← ChannelSpec, load_channels()
│   ├── youtube_api.py       ← YouTube Data API v3
│   ├── subs.py              ← yt-dlp SRT download
│   ├── srt.py               ← SRT parsing → Cue
│   └── chunking.py          ← sentence grouping, token counting
└── ui/                      ← unchanged
    ├── __init__.py
    ├── app.py               ← update import: lucas_v2.db → lucas_v2.db.connection
    ├── db_search.py
    ├── query.py
    └── img/
```

---

## Key Design Decision: Chunk Dataclass

**Problem**: `db.py` imports `Chunk` from `chunking.py`. After refactor, `db/` would depend on `ingest/` — a cross-package dependency.

**Solution**: Move `Chunk` dataclass to `db/__init__.py`. It's a data model (schema-adjacent), not business logic.

```python
# db/__init__.py
@dataclass
class Chunk:
    seq_no: int
    start_s: int
    end_s: int
    text: str
    tokens: int
```

- `db/connection.py` imports `Chunk` from `db/__init__` (same package)
- `ingest/chunking.py` imports `Chunk` from `lucas_v2.db` (cross-package, acceptable for data model)

---

## Step 1: Create `db/` Package

### 1a. `db/__init__.py`
- Define `Chunk` dataclass (moved from `chunking.py`)
- Re-export key symbols: `Chunk`, `connect`, `DbConn`

### 1b. `db/connection.py`
- Move from `db.py`: `DbConn`, `_raw_connect()`, `connect()`
- Remove: `search_chunks`, `upsert_*`, `replace_chunks`, `fetch_*`, `find_video_channel`, `get_channel_url`
- Remove import: `from lucas_v2.chunking import Chunk` (no longer needed here)

### 1c. `db/operations.py`
- Move from `db.py`: `upsert_channel`, `upsert_video`, `replace_chunks`, `video_exists`, `fetch_existing_ids`, `find_video_channel`, `get_channel_url`, `search_chunks`
- Add import: `from lucas_v2.db import Chunk` (for `replace_chunks` signature)
- Add import: `from lucas_v2.db.connection import _raw_connect` (only if needed — check)

### 1d. `db/schema.py`
- Copy from `schema.py` (no changes needed — `Path(__file__).with_name("schema.sql")` still works since `schema.sql` is in the same directory)

### 1e. `db/schema.sql`
- Copy from `schema.sql` (unchanged)

---

## Step 2: Create `ingest/` Package

### 2a. `ingest/__init__.py`
- Re-export key symbols for convenience: `ChannelSpec`, `load_channels`

### 2b. Move files (no content changes needed)
- `config.py` → `ingest/config.py`
- `youtube_api.py` → `ingest/youtube_api.py`
- `subs.py` → `ingest/subs.py`
- `srt.py` → `ingest/srt.py`

### 2c. `ingest/chunking.py`
- Move from `chunking.py`
- Update import: `from lucas_v2.chunking import Cue` → `from lucas_v2.ingest.srt import Cue`
- Update import: `from lucas_v2.chunking import Chunk` → `from lucas_v2.db import Chunk`
- Remove `Chunk` dataclass definition (now in `db/__init__.py`)

---

## Step 3: Update `__init__.py` (Orchestration)

All lazy imports need path updates:

| Old Import | New Import |
|---|---|
| `from lucas_v2.config import ChannelSpec` | `from lucas_v2.ingest.config import ChannelSpec` |
| `from lucas_v2.subs import AbortIngestion, RateLimitState` | `from lucas_v2.ingest.subs import AbortIngestion, RateLimitState` |
| `from lucas_v2.db import upsert_channel` | `from lucas_v2.db.operations import upsert_channel` |
| `from lucas_v2.youtube_api import resolve_channel_id` | `from lucas_v2.ingest.youtube_api import resolve_channel_id` |
| `from lucas_v2.youtube_api import list_videos` | `from lucas_v2.ingest.youtube_api import list_videos` |
| `from lucas_v2.db import upsert_video, replace_chunks` | `from lucas_v2.db.operations import upsert_video, replace_chunks` |
| `from lucas_v2.subs import download_srt, RateLimitedError` | `from lucas_v2.ingest.subs import download_srt, RateLimitedError` |
| `from lucas_v2.srt import parse_srt` | `from lucas_v2.ingest.srt import parse_srt` |
| `from lucas_v2.chunking import chunk_cues` | `from lucas_v2.ingest.chunking import chunk_cues` |
| `from lucas_v2.db import fetch_existing_ids` | `from lucas_v2.db.operations import fetch_existing_ids` |
| `from lucas_v2.config import load_channels` | `from lucas_v2.ingest.config import load_channels` |
| `from lucas_v2.db import connect` | `from lucas_v2.db.connection import connect` |
| `from lucas_v2.schema import init_schema` | `from lucas_v2.db.schema import init_schema` |
| `from lucas_v2.chunking import get_tokenizer, MAX_CONTENT_TOKENS` | `from lucas_v2.ingest.chunking import get_tokenizer, MAX_CONTENT_TOKENS` |
| `from lucas_v2.youtube_api import get_client` | `from lucas_v2.ingest.youtube_api import get_client` |
| `from lucas_v2.db import find_video_channel, get_channel_url` | `from lucas_v2.db.operations import find_video_channel, get_channel_url` |

---

## Step 4: Update `ui/app.py`

| Old Import | New Import |
|---|---|
| `from lucas_v2.db import connect` | `from lucas_v2.db.connection import connect` |

---

## Step 5: Update Test Files

### `tests/test_cli.py`
| Old Import | New Import |
|---|---|
| `from lucas_v2.config import ChannelSpec` | `from lucas_v2.ingest.config import ChannelSpec` |
| `from lucas_v2.subs import AbortIngestion, RateLimitState` | `from lucas_v2.ingest.subs import AbortIngestion, RateLimitState` |
| Patch paths: `lucas_v2.db.upsert_channel` | `lucas_v2.db.operations.upsert_channel` |
| Patch paths: `lucas_v2.youtube_api.resolve_channel_id` | `lucas_v2.ingest.youtube_api.resolve_channel_id` |
| Patch paths: `lucas_v2.youtube_api.list_videos` | `lucas_v2.ingest.youtube_api.list_videos` |
| Patch paths: `lucas_v2.youtube_api.get_client` | `lucas_v2.ingest.youtube_api.get_client` |
| Patch paths: `lucas_v2.subs.download_srt` | `lucas_v2.ingest.subs.download_srt` |
| Patch paths: `lucas_v2.chunking.get_tokenizer` | `lucas_v2.ingest.chunking.get_tokenizer` |
| Patch paths: `lucas_v2.schema.init_schema` | `lucas_v2.db.schema.init_schema` |
| Patch paths: `lucas_v2.db.connect` | `lucas_v2.db.connection.connect` |
| Patch paths: `lucas_v2.logging_config.setup_logging` | `lucas_v2.logging_config.setup_logging` (unchanged) |
| Patch paths: `lucas_v2.db.fetch_existing_ids` | `lucas_v2.db.operations.fetch_existing_ids` |
| Patch paths: `lucas_v2.db.upsert_video` | `lucas_v2.db.operations.upsert_video` |
| Patch paths: `lucas_v2.chunking.chunk_cues` | `lucas_v2.ingest.chunking.chunk_cues` |
| Patch paths: `lucas_v2.srt.parse_srt` | `lucas_v2.ingest.srt.parse_srt` |
| Patch paths: `lucas_v2.db.replace_chunks` | `lucas_v2.db.operations.replace_chunks` |
| Patch paths: `lucas_v2.time.sleep` | `lucas_v2.time.sleep` (unchanged — it's in `__init__.py`) |
| Patch paths: `lucas_v2.random.uniform` | `lucas_v2.random.uniform` (unchanged) |

### `tests/test_config.py`
| Old Import | New Import |
|---|---|
| `from lucas_v2.config import ChannelSpec, load_channels` | `from lucas_v2.ingest.config import ChannelSpec, load_channels` |

### `tests/test_db.py`
| Old Import | New Import |
|---|---|
| `from lucas_v2.chunking import Chunk` | `from lucas_v2.db import Chunk` |
| `from lucas_v2.db import (DbConn, ...)` | `from lucas_v2.db.connection import DbConn` + `from lucas_v2.db.operations import (...)` |
| `from lucas_v2.schema import init_schema` | `from lucas_v2.db.schema import init_schema` |
| Patch paths: `lucas_v2.db._raw_connect` | `lucas_v2.db.connection._raw_connect` |

### `tests/test_search_db.py`
| Old Import | New Import |
|---|---|
| `from lucas_v2.chunking import Chunk` | `from lucas_v2.db import Chunk` |
| `from lucas_v2.db import replace_chunks, upsert_channel, upsert_video` | `from lucas_v2.db.operations import replace_chunks, upsert_channel, upsert_video` |
| `from lucas_v2.schema import init_schema` | `from lucas_v2.db.schema import init_schema` |

### `tests/test_search_query.py`
- No changes (imports from `lucas_v2.ui.query`)

### `tests/test_srt_chunk.py`
| Old Import | New Import |
|---|---|
| `from lucas_v2.srt import parse_srt` | `from lucas_v2.ingest.srt import parse_srt` |
| `from lucas_v2.chunking import chunk_cues, count_tokens, MAX_CONTENT_TOKENS, SOFT_MIN` | `from lucas_v2.ingest.chunking import chunk_cues, count_tokens, MAX_CONTENT_TOKENS, SOFT_MIN` |
| `from lucas_v2.srt import Cue` | `from lucas_v2.ingest.srt import Cue` |
| `from lucas_v2.chunking import get_tokenizer` | `from lucas_v2.ingest.chunking import get_tokenizer` |

### `tests/test_subs.py`
| Old Import | New Import |
|---|---|
| `from lucas_v2.subs import ...` | `from lucas_v2.ingest.subs import ...` |

### `tests/test_youtube_api.py`
| Old Import | New Import |
|---|---|
| `from lucas_v2.youtube_api import ...` | `from lucas_v2.ingest.youtube_api import ...` |

### `tests/test_schema.py`
| Old Import | New Import |
|---|---|
| `from lucas_v2.schema import init_schema` | `from lucas_v2.db.schema import init_schema` |
| `from lucas_v2.schema import load_schema` | `from lucas_v2.db.schema import load_schema` |

### `tests/test_logging_config.py`
- No changes (imports from `lucas_v2.logging_config`)

---

## Step 6: Delete Old Files

After all moves are complete and tests pass:
- Delete `src/lucas_v2/db.py`
- Delete `src/lucas_v2/schema.py`
- Delete `src/lucas_v2/schema.sql`
- Delete `src/lucas_v2/config.py`
- Delete `src/lucas_v2/youtube_api.py`
- Delete `src/lucas_v2/subs.py`
- Delete `src/lucas_v2/srt.py`
- Delete `src/lucas_v2/chunking.py`

---

## Step 7: Update AGENTS.md

Update file reference table and architecture section to reflect new paths:

| Old Path | New Path |
|---|---|
| `src/lucas_v2/db.py` | `src/lucas_v2/db/connection.py` + `src/lucas_v2/db/operations.py` |
| `src/lucas_v2/schema.py` | `src/lucas_v2/db/schema.py` |
| `src/lucas_v2/schema.sql` | `src/lucas_v2/db/schema.sql` |
| `src/lucas_v2/config.py` | `src/lucas_v2/ingest/config.py` |
| `src/lucas_v2/youtube_api.py` | `src/lucas_v2/ingest/youtube_api.py` |
| `src/lucas_v2/subs.py` | `src/lucas_v2/ingest/subs.py` |
| `src/lucas_v2/srt.py` | `src/lucas_v2/ingest/srt.py` |
| `src/lucas_v2/chunking.py` | `src/lucas_v2/ingest/chunking.py` |

Update architecture diagram and data flow section.

---

## Step 8: Verify

```bash
uv run pytest tests/ -v
uv run pyright
```

---

## Risk Assessment

- **Circular imports**: None — `db/` does not import from `ingest/` (Chunk is a data model in `db/__init__`)
- **Relative path in schema.py**: `Path(__file__).with_name("schema.sql")` — works since both files move together
- **pyproject.toml entry point**: `lucas_v2:main` — unchanged (still in `__init__.py`)
- **Patch paths in tests**: Many mock paths change — must be thorough

---

## Execution Order

1. Create `db/` directory and all files
2. Create `ingest/` directory and all files
3. Update `__init__.py` imports
4. Update `ui/app.py` imports
5. Update all test files
6. Run tests + pyright
7. Delete old files
8. Update AGENTS.md
9. Final verification
