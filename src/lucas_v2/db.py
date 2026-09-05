import os

import libsql_experimental as libsql


_SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_url TEXT NOT NULL UNIQUE,
  channel_id TEXT,
  title TEXT,
  added_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS videos (
  video_id TEXT PRIMARY KEY,
  channel_id INTEGER REFERENCES channels(id),
  channel_url TEXT NOT NULL,
  video_url TEXT NOT NULL,
  title TEXT,
  upload_date TEXT,
  duration_s INTEGER,
  sub_lang TEXT,
  sub_kind TEXT,
  status TEXT DEFAULT 'ok',
  error TEXT,
  scraped_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transcript_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
  seq_no INTEGER NOT NULL,
  start_s INTEGER NOT NULL,
  end_s INTEGER NOT NULL,
  text TEXT NOT NULL,
  tokens INTEGER NOT NULL,
  UNIQUE(video_id, seq_no)
);

CREATE INDEX IF NOT EXISTS idx_chunks_video ON transcript_chunks(video_id, seq_no);
"""


def connect():
    url = os.environ["TURSO_DATABASE_URL"]
    token = os.environ.get("TURSO_AUTH_TOKEN")
    return libsql.connect(url, auth_token=token)


def init_schema(conn):
    for stmt in _SCHEMA.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt + ";")


def upsert_channel(conn, channel_url: str, channel_id: str | None, title: str | None) -> int:
    """Upsert channel, retourne l'id local (channels.id) pour la FK videos."""
    conn.execute(
        "INSERT INTO channels (channel_url, channel_id, title) VALUES (?, ?, ?) "
        "ON CONFLICT(channel_url) DO UPDATE SET channel_id=excluded.channel_id, title=excluded.title",
        (channel_url, channel_id, title),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM channels WHERE channel_url=?", (channel_url,)
    ).fetchone()
    return row[0]


def upsert_video(conn, video_id: str, channel_id: int | None, channel_url: str,
                 video_url: str, title: str | None, upload_date: str | None,
                 duration_s: int | None, sub_lang: str | None, sub_kind: str | None,
                 status: str, error: str | None):
    conn.execute(
        "INSERT INTO videos (video_id, channel_id, channel_url, video_url, title, "
        "upload_date, duration_s, sub_lang, sub_kind, status, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(video_id) DO UPDATE SET "
        "channel_id=excluded.channel_id, title=excluded.title, upload_date=excluded.upload_date, "
        "duration_s=excluded.duration_s, sub_lang=excluded.sub_lang, sub_kind=excluded.sub_kind, "
        "status=excluded.status, error=excluded.error, scraped_at=datetime('now')",
        (video_id, channel_id, channel_url, video_url, title, upload_date,
         duration_s, sub_lang, sub_kind, status, error),
    )
    conn.commit()


def replace_chunks(conn, video_id: str, chunks):
    conn.execute("DELETE FROM transcript_chunks WHERE video_id=?", (video_id,))
    for ch in chunks:
        conn.execute(
            "INSERT INTO transcript_chunks (video_id, seq_no, start_s, end_s, text, tokens) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (video_id, ch.seq_no, ch.start_s, ch.end_s, ch.text, ch.tokens),
        )
    conn.commit()


def video_exists_ok(conn, video_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM videos WHERE video_id=? AND status='ok'", (video_id,)
    ).fetchone()
    return row is not None


def video_exists(conn, video_id: str) -> bool:
    """True si la vidéo a déjà été scrapée, quel que soit son statut."""
    row = conn.execute(
        "SELECT 1 FROM videos WHERE video_id=?", (video_id,)
    ).fetchone()
    return row is not None
