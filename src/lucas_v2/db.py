from __future__ import annotations

import os
from typing import Any

import libsql_experimental as libsql  # pyright: ignore[reportMissingModuleSource]

from lucas_v2.chunking import Chunk


def connect() -> Any:
    url: str = os.environ["TURSO_DATABASE_URL"]
    token: str | None = os.environ.get("TURSO_AUTH_TOKEN")
    return libsql.connect(url, auth_token=token)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]


def search_chunks(conn: Any, query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Recherche plein-texte (FTS5) sur transcript_chunk.text.

    query : syntaxe FTS5 ('mots', '\"expression exacte\"', 'prefix*', 'colonne:terme').
    Diacritiques ignores (ex. 'deja' matche 'déjà'). Retourne les chunks
    ordonnes par pertinence (bm25) avec extrait + metadonnees video.
    """
    rows = conn.execute(
        "SELECT tc.id, tc.fk_video_id, tc.seq_no, tc.start_s, tc.end_s, tc.text, "
        "v.youtube_str_id AS youtube_id, "
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


def upsert_channel(conn: Any, channel_url: str, channel_id: str | None,
                   title: str | None, orientation: str | None,
                   owner: str | None) -> int:
    """Upsert channel, retourne l'id local (channel.id) pour la FK video."""
    conn.execute(
        "INSERT INTO channel (channel_url, channel_id, title, orientation, owner) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(channel_url) DO UPDATE SET "
        "channel_id=excluded.channel_id, title=excluded.title, orientation=excluded.orientation, "
        "owner=COALESCE(excluded.owner, channel.owner)",
        (channel_url, channel_id, title, orientation, owner),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM channel WHERE channel_url=?", (channel_url,)
    ).fetchone()
    return int(row[0])


def upsert_video(conn: Any, fk_channel_id: int | None,
                 youtube_str_id: str, title: str | None, upload_date: str | None,
                 duration_s: int | None, sub_lang: str | None, sub_kind: str | None,
                 status: str, error: str | None) -> int:
    """Upsert video par youtube_str_id, retourne l'id local (video.id) pour la FK transcript_chunk.

    Ne commit PAS : l'appelant doit appeler conn.commit() après avoir inséré les chunks.
    """
    cur = conn.execute(
        "INSERT INTO video (fk_channel_id, youtube_str_id, title, "
        "upload_date, duration_s, sub_lang, sub_kind, status, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(youtube_str_id) DO UPDATE SET "
        "fk_channel_id=excluded.fk_channel_id, title=excluded.title, upload_date=excluded.upload_date, "
        "duration_s=excluded.duration_s, sub_lang=excluded.sub_lang, sub_kind=excluded.sub_kind, "
        "status=excluded.status, error=excluded.error, scraped_at=datetime('now') "
        "RETURNING id",
        (fk_channel_id, youtube_str_id, title, upload_date,
         duration_s, sub_lang, sub_kind, status, error),
    )
    return int(cur.fetchone()[0])


_CHUNK_BATCH = 500  # rows per INSERT statement (sécurité, pas de limite SQLite stricte ici)


def replace_chunks(conn: Any, fk_video_id: int, chunks: list[Chunk], *, delete_existing: bool = True) -> None:
    """Insère les chunks en bulk multi-VALUES (1 seul SQL par batch) pour minimiser
    les writes Turso et les round-trips HTTP.

    delete_existing=True : DELETE ancien chunks + réinsert (re-srape).
    delete_existing=False : insert direct (vidéo nouvelle, pas de DELETE inutile).
    """
    if delete_existing:
        conn.execute("DELETE FROM transcript_chunk WHERE fk_video_id=?", (fk_video_id,))
    n = len(chunks)
    if n == 0:
        return
    cols = "fk_video_id, seq_no, start_s, end_s, text, tokens"
    placeholder = "(?, ?, ?, ?, ?, ?)"
    for start in range(0, n, _CHUNK_BATCH):
        batch = chunks[start : start + _CHUNK_BATCH]
        placeholders = ",".join([placeholder] * len(batch))
        flat = tuple(
            v
            for ch in batch
            for v in (fk_video_id, ch.seq_no, ch.start_s, ch.end_s, ch.text, ch.tokens)
        )
        conn.execute(f"INSERT INTO transcript_chunk ({cols}) VALUES {placeholders}", flat)


def video_exists(conn: Any, youtube_str_id: str) -> bool:
    """True si la vidéo a déjà été scrapée, quel que soit son statut."""
    row = conn.execute(
        "SELECT 1 FROM video WHERE youtube_str_id=?", (youtube_str_id,)
    ).fetchone()
    return row is not None


def find_video_channel(conn: Any, youtube_str_id: str) -> tuple[int, str] | None:
    """Return (channel_row_id, channel_yt_id) for a video, or None if not found."""
    row = conn.execute(
        "SELECT v.fk_channel_id, c.channel_id "
        "FROM video v JOIN channel c ON v.fk_channel_id = c.id "
        "WHERE v.youtube_str_id=?",
        (youtube_str_id,),
    ).fetchone()
    if row is None:
        return None
    return int(row[0]), str(row[1])


def get_channel_url(conn: Any, channel_row_id: int) -> str | None:
    """Return the channel_url for a given channel row ID."""
    row = conn.execute(
        "SELECT channel_url FROM channel WHERE id=?", (channel_row_id,)
    ).fetchone()
    return str(row[0]) if row else None
