import os

import libsql_experimental as libsql


def connect():
    url = os.environ["TURSO_DATABASE_URL"]
    token = os.environ.get("TURSO_AUTH_TOKEN")
    return libsql.connect(url, auth_token=token)


def search_chunks(conn, query: str, limit: int = 20):
    """Recherche plein-texte (FTS5) sur transcript_chunk.text.

    query : syntaxe FTS5 ('mots', '\"expression exacte\"', 'prefix*', 'colonne:terme').
    Diacritiques ignores (ex. 'deja' matche 'déjà'). Retourne les chunks
    ordonnes par pertinence (bm25) avec extrait + metadonnees video.
    """
    rows = conn.execute(
        "SELECT tc.id, tc.fk_video_id, tc.seq_no, tc.start_s, tc.end_s, tc.text, "
        "substr(v.video_url, instr(v.video_url, 'v=') + 2) AS youtube_id, "
        "v.title AS video_title, "
        "snippet(transcript_chunk_fts, 0, '<b>', '</b>', '…', 12) AS snippet, "
        "bm25(transcript_chunk_fts) AS rank "
        "FROM transcript_chunk_fts f "
        "JOIN transcript_chunk tc ON tc.id = f.rowid "
        "JOIN video v ON v.id = tc.fk_video_id "
        "WHERE transcript_chunk_fts MATCH ? "
        "ORDER BY rank LIMIT ?",
        (query, limit),
    ).fetchall()
    cols = ("id", "fk_video_id", "seq_no", "start_s", "end_s", "text",
            "youtube_id", "video_title", "snippet", "rank")
    return [dict(zip(cols, r)) for r in rows]


def upsert_channel(conn, channel_url: str, channel_id: str | None, title: str | None) -> int:
    """Upsert channel, retourne l'id local (channel.id) pour la FK video."""
    conn.execute(
        "INSERT INTO channel (channel_url, channel_id, title) VALUES (?, ?, ?) "
        "ON CONFLICT(channel_url) DO UPDATE SET channel_id=excluded.channel_id, title=excluded.title",
        (channel_url, channel_id, title),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM channel WHERE channel_url=?", (channel_url,)
    ).fetchone()
    return row[0]


def upsert_video(conn, fk_channel_id: int | None,
                 video_url: str, title: str | None, upload_date: str | None,
                 duration_s: int | None, sub_lang: str | None, sub_kind: str | None,
                 status: str, error: str | None) -> int:
    """Upsert video par video_url, retourne l'id local (video.id) pour la FK transcript_chunk."""
    conn.execute(
        "INSERT INTO video (fk_channel_id, video_url, title, "
        "upload_date, duration_s, sub_lang, sub_kind, status, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(video_url) DO UPDATE SET "
        "fk_channel_id=excluded.fk_channel_id, title=excluded.title, upload_date=excluded.upload_date, "
        "duration_s=excluded.duration_s, sub_lang=excluded.sub_lang, sub_kind=excluded.sub_kind, "
        "status=excluded.status, error=excluded.error, scraped_at=datetime('now')",
        (fk_channel_id, video_url, title, upload_date,
         duration_s, sub_lang, sub_kind, status, error),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM video WHERE video_url=?", (video_url,)
    ).fetchone()
    return row[0]


def replace_chunks(conn, fk_video_id: int, chunks):
    conn.execute("DELETE FROM transcript_chunk WHERE fk_video_id=?", (fk_video_id,))
    for ch in chunks:
        conn.execute(
            "INSERT INTO transcript_chunk (fk_video_id, seq_no, start_s, end_s, text, tokens) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fk_video_id, ch.seq_no, ch.start_s, ch.end_s, ch.text, ch.tokens),
        )
    conn.commit()


def video_exists_ok(conn, video_url: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM video WHERE video_url=? AND status='ok'", (video_url,)
    ).fetchone()
    return row is not None


def video_exists(conn, video_url: str) -> bool:
    """True si la vidéo a déjà été scrapée, quel que soit son statut."""
    row = conn.execute(
        "SELECT 1 FROM video WHERE video_url=?", (video_url,)
    ).fetchone()
    return row is not None
