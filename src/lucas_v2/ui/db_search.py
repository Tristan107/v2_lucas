from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

SNIPPET_TOKENS: Final[int] = 15


@dataclass(frozen=True, slots=True)
class VideoHit:
    youtube_str_id: str
    title: str | None
    upload_date: str | None
    owner: str | None
    orientation: str | None
    mentions: int


@dataclass(frozen=True, slots=True)
class ChunkHit:
    seq_no: int
    start_s: int
    end_s: int
    snippet: str
    youtube_str_id: str


def search_videos(conn: Any, match_query: str, limit: int = 10, offset: int = 0) -> list[VideoHit]:
    """Return distinct videos whose chunks match *match_query*.

    Ordered by upload date descending, then mention count descending,
    then video id descending as a stable tiebreaker.
    """
    rows = conn.execute(
        "SELECT v.youtube_str_id, v.title, v.upload_date, c.owner, c.orientation, "
        "COUNT(*) AS mentions "
        "FROM transcript_chunk_fts f "
        "JOIN transcript_chunk tc ON tc.id = f.rowid "
        "JOIN video v ON v.id = tc.fk_video_id "
        "LEFT JOIN channel c ON c.id = v.fk_channel_id "
        "WHERE transcript_chunk_fts MATCH ? "
        "GROUP BY v.id "
        "ORDER BY v.upload_date DESC, COUNT(*) DESC, v.id DESC "
        "LIMIT ? OFFSET ?",
        (match_query, limit, offset),
    ).fetchall()
    return [
        VideoHit(
            youtube_str_id=str(r[0]),
            title=r[1],
            upload_date=r[2],
            owner=r[3],
            orientation=r[4],
            mentions=int(r[5]),
        )
        for r in rows
    ]


def search_video_chunks(
    conn: Any,
    match_query: str,
    youtube_str_id: str,
    limit: int = 10,
    offset: int = 0,
) -> list[ChunkHit]:
    """Return matching chunks for a single video, in chronological order with pagination."""
    rows = conn.execute(
        "SELECT tc.seq_no, tc.start_s, tc.end_s, "
        f"snippet(transcript_chunk_fts, 0, '**', '**', '…', {SNIPPET_TOKENS}) AS snippet, "
        "v.youtube_str_id "
        "FROM transcript_chunk_fts f "
        "JOIN transcript_chunk tc ON tc.id = f.rowid "
        "JOIN video v ON v.id = tc.fk_video_id "
        "WHERE transcript_chunk_fts MATCH ? AND v.youtube_str_id = ? "
        "ORDER BY tc.seq_no ASC "
        "LIMIT ? OFFSET ?",
        (match_query, youtube_str_id, limit, offset),
    ).fetchall()
    return [
        ChunkHit(
            seq_no=int(r[0]),
            start_s=int(r[1]),
            end_s=int(r[2]),
            snippet=str(r[3]),
            youtube_str_id=str(r[4]),
        )
        for r in rows
    ]


def count_videos(conn: Any, match_query: str) -> int:
    """Count distinct videos whose chunks match *match_query*."""
    row = conn.execute(
        "SELECT COUNT(*) FROM ("
        "SELECT v.id "
        "FROM transcript_chunk_fts f "
        "JOIN transcript_chunk tc ON tc.id = f.rowid "
        "JOIN video v ON v.id = tc.fk_video_id "
        "WHERE transcript_chunk_fts MATCH ? "
        "GROUP BY v.id)",
        (match_query,),
    ).fetchone()
    return int(row[0]) if row else 0


def get_video(conn: Any, youtube_str_id: str) -> VideoHit | None:
    """Return metadata + total mention count for one video, or None."""
    row = conn.execute(
        "SELECT v.youtube_str_id, v.title, v.upload_date, c.owner, c.orientation, "
        "COUNT(tc.id) AS mentions "
        "FROM video v "
        "LEFT JOIN channel c ON c.id = v.fk_channel_id "
        "LEFT JOIN transcript_chunk tc ON tc.fk_video_id = v.id "
        "WHERE v.youtube_str_id = ? "
        "GROUP BY v.id",
        (youtube_str_id,),
    ).fetchone()
    if row is None:
        return None
    return VideoHit(
        youtube_str_id=str(row[0]),
        title=row[1],
        upload_date=row[2],
        owner=row[3],
        orientation=row[4],
        mentions=int(row[5]),
    )


def count_video_chunks(conn: Any, match_query: str, youtube_str_id: str) -> int:
    """Count total matching chunks for a single video."""
    row = conn.execute(
        "SELECT COUNT(*) "
        "FROM transcript_chunk_fts f "
        "JOIN transcript_chunk tc ON tc.id = f.rowid "
        "JOIN video v ON v.id = tc.fk_video_id "
        "WHERE transcript_chunk_fts MATCH ? AND v.youtube_str_id = ?",
        (match_query, youtube_str_id),
    ).fetchone()
    return int(row[0]) if row else 0
