from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final

logger = logging.getLogger("lucas_v2")

SNIPPET_TOKENS: Final[int] = 15


def _log_fts_error(match_query: str, e: ValueError) -> None:
    """Classe et logge les erreurs ValueError des requêtes FTS5."""
    err_msg = str(e).lower()
    if "fts5" in err_msg or "syntax" in err_msg:
        logger.warning("Requête FTS5 invalide : %s", match_query)
    else:
        logger.error(
            "Erreur de connexion lors de la recherche FTS5 (query=%s) : %s",
            match_query,
            e,
        )


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


@dataclass(frozen=True, slots=True)
class OrientationStats:
    orientation: str | None
    matched: int
    total: int


@dataclass(frozen=True, slots=True)
class ChannelStats:
    owner: str | None
    orientation: str | None
    matched: int
    total: int


def search_videos(
    conn: Any,
    match_query: str,
    limit: int = 10,
    offset: int = 0,
    owner_filter: str | None = None,
) -> list[VideoHit]:
    """Return distinct videos whose chunks match *match_query*.

    Ordered by mention count descending, then upload date descending,
    then video id descending as a stable tiebreaker.
    """
    where_clauses = ["transcript_chunk_fts MATCH ?"]
    params: list[Any] = [match_query]
    if owner_filter is not None:
        where_clauses.append("c.owner = ?")
        params.append(owner_filter)
    where_sql = " AND ".join(where_clauses)
    params.extend([limit, offset])

    try:
        rows = conn.execute(
            "SELECT v.youtube_str_id, v.title, v.upload_date, c.owner, c.orientation, "
            "COUNT(*) AS mentions "
            "FROM transcript_chunk_fts f "
            "JOIN transcript_chunk tc ON tc.id = f.rowid "
            "JOIN video v ON v.id = tc.fk_video_id "
            "LEFT JOIN channel c ON c.id = v.fk_channel_id "
            f"WHERE {where_sql} "
            "GROUP BY v.id "
            "ORDER BY COUNT(*) DESC, v.upload_date DESC, v.id DESC "
            "LIMIT ? OFFSET ?",
            tuple(params),
        ).fetchall()
    except ValueError as e:
        _log_fts_error(match_query, e)
        return []
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
    try:
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
    except ValueError as e:
        _log_fts_error(match_query, e)
        return []
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


def count_videos(
    conn: Any,
    match_query: str,
    owner_filter: str | None = None,
) -> int:
    """Count distinct videos whose chunks match *match_query*."""
    where_clauses = ["transcript_chunk_fts MATCH ?"]
    params: list[Any] = [match_query]
    if owner_filter is not None:
        where_clauses.append("c.owner = ?")
        params.append(owner_filter)
    where_sql = " AND ".join(where_clauses)

    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT v.id "
            "FROM transcript_chunk_fts f "
            "JOIN transcript_chunk tc ON tc.id = f.rowid "
            "JOIN video v ON v.id = tc.fk_video_id "
            "LEFT JOIN channel c ON c.id = v.fk_channel_id "
            f"WHERE {where_sql} "
            "GROUP BY v.id)",
            tuple(params),
        ).fetchone()
    except ValueError as e:
        _log_fts_error(match_query, e)
        return 0
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
    try:
        row = conn.execute(
            "SELECT COUNT(*) "
            "FROM transcript_chunk_fts f "
            "JOIN transcript_chunk tc ON tc.id = f.rowid "
            "JOIN video v ON v.id = tc.fk_video_id "
            "WHERE transcript_chunk_fts MATCH ? AND v.youtube_str_id = ?",
            (match_query, youtube_str_id),
        ).fetchone()
    except ValueError as e:
        _log_fts_error(match_query, e)
        return 0
    return int(row[0]) if row else 0


def search_chunks_by_orientation(conn: Any, match_query: str) -> list[OrientationStats]:
    """Return per-orientation chunk counts: matched (FTS) vs total (all chunks in DB).

    Results are sorted by ratio descending (highest proportion first).
    Orientations with total == 0 are excluded.
    """
    try:
        matched_rows = conn.execute(
            "SELECT c.orientation, COUNT(*) AS matched "
            "FROM transcript_chunk_fts f "
            "JOIN transcript_chunk tc ON tc.id = f.rowid "
            "JOIN video v ON v.id = tc.fk_video_id "
            "LEFT JOIN channel c ON c.id = v.fk_channel_id "
            "WHERE transcript_chunk_fts MATCH ? "
            "GROUP BY c.orientation",
            (match_query,),
        ).fetchall()
    except ValueError as e:
        _log_fts_error(match_query, e)
        return []

    total_rows = conn.execute(
        "SELECT c.orientation, COUNT(tc.id) AS total "
        "FROM transcript_chunk tc "
        "JOIN video v ON v.id = tc.fk_video_id "
        "LEFT JOIN channel c ON c.id = v.fk_channel_id "
        "GROUP BY c.orientation",
    ).fetchall()

    totals: dict[str | None, int] = {r[0]: int(r[1]) for r in total_rows}

    stats: list[OrientationStats] = []
    for r in matched_rows:
        orient = r[0]
        matched = int(r[1])
        total = totals.get(orient, 0)
        if total > 0:
            stats.append(OrientationStats(orientation=orient, matched=matched, total=total))

    stats.sort(key=lambda s: s.matched / s.total, reverse=True)
    return stats


def search_chunks_by_channel(conn: Any, match_query: str) -> list[ChannelStats]:
    """Return per-channel chunk counts: matched (FTS) vs total (all chunks in DB).

    Results are sorted by ratio descending (highest proportion first).
    Channels with total == 0 are excluded. NULL titles are grouped under "non classé".
    """
    try:
        matched_rows = conn.execute(
            "SELECT v.fk_channel_id, c.owner, c.orientation, COUNT(*) AS matched "
            "FROM transcript_chunk_fts f "
            "JOIN transcript_chunk tc ON tc.id = f.rowid "
            "JOIN video v ON v.id = tc.fk_video_id "
            "LEFT JOIN channel c ON c.id = v.fk_channel_id "
            "WHERE transcript_chunk_fts MATCH ? "
            "GROUP BY v.fk_channel_id",
            (match_query,),
        ).fetchall()
    except ValueError as e:
        _log_fts_error(match_query, e)
        return []

    total_rows = conn.execute(
        "SELECT v.fk_channel_id, COUNT(tc.id) AS total "
        "FROM transcript_chunk tc "
        "JOIN video v ON v.id = tc.fk_video_id "
        "GROUP BY v.fk_channel_id",
    ).fetchall()

    totals: dict[int | None, int] = {r[0]: int(r[1]) for r in total_rows}

    stats: list[ChannelStats] = []
    for r in matched_rows:
        ch_id = r[0]
        owner = r[1]
        orient = r[2]
        matched = int(r[3])
        total = totals.get(ch_id, 0)
        if total > 0:
            stats.append(
                ChannelStats(
                    owner=owner,
                    orientation=orient,
                    matched=matched,
                    total=total,
                )
            )

    stats.sort(key=lambda s: s.matched / s.total, reverse=True)
    return stats
