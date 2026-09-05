_TABLES = """
CREATE TABLE IF NOT EXISTS channel (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_url TEXT NOT NULL UNIQUE,
  channel_id TEXT,
  title TEXT,
  added_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS video (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fk_channel_id INTEGER,
  video_url TEXT NOT NULL UNIQUE,
  title TEXT,
  upload_date TEXT,
  duration_s INTEGER,
  sub_lang TEXT,
  sub_kind TEXT,
  status TEXT DEFAULT 'ok',
  error TEXT,
  scraped_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (fk_channel_id) REFERENCES channel(id)
);

CREATE TABLE IF NOT EXISTS transcript_chunk (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fk_video_id INTEGER NOT NULL REFERENCES video(id) ON DELETE CASCADE,
  seq_no INTEGER NOT NULL,
  start_s INTEGER NOT NULL,
  end_s INTEGER NOT NULL,
  text TEXT NOT NULL,
  tokens INTEGER NOT NULL,
  UNIQUE(fk_video_id, seq_no)
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_video_fk_channel ON video(fk_channel_id);
CREATE INDEX IF NOT EXISTS idx_channel_ytid ON channel(channel_id);
"""

_FTS_STMTS = [
    """CREATE VIRTUAL TABLE IF NOT EXISTS transcript_chunk_fts USING fts5(
      text,
      content='transcript_chunk',
      content_rowid='id',
      tokenize="unicode61 remove_diacritics 2"
    )""",
    """CREATE TRIGGER IF NOT EXISTS trg_chunk_fts_ai AFTER INSERT ON transcript_chunk BEGIN
      INSERT INTO transcript_chunk_fts(rowid, text) VALUES (new.id, new.text);
    END""",
    """CREATE TRIGGER IF NOT EXISTS trg_chunk_fts_ad AFTER DELETE ON transcript_chunk BEGIN
      INSERT INTO transcript_chunk_fts(transcript_chunk_fts, rowid, text) VALUES ('delete', old.id, old.text);
    END""",
    """CREATE TRIGGER IF NOT EXISTS trg_chunk_fts_au AFTER UPDATE ON transcript_chunk BEGIN
      INSERT INTO transcript_chunk_fts(transcript_chunk_fts, rowid, text) VALUES ('delete', old.id, old.text);
      INSERT INTO transcript_chunk_fts(rowid, text) VALUES (new.id, new.text);
    END""",
]

_SCHEMA = _TABLES + _INDEXES


def init_schema(conn):
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
    except Exception:
        pass
    for stmt in _TABLES.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt + ";")
    for stmt in _INDEXES.strip().split(";"):
        stmt = stmt.strip()
        if stmt and not stmt.startswith("--"):
            conn.execute(stmt + ";")
    for stmt in _FTS_STMTS:
        conn.execute(stmt + ";")
    conn.commit()
