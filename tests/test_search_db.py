from __future__ import annotations

from typing import Any

import libsql_experimental as libsql  # pyright: ignore[reportMissingModuleSource]

from lucas_v2.chunking import Chunk
from lucas_v2.db import replace_chunks, upsert_channel, upsert_video
from lucas_v2.schema import init_schema
from lucas_v2.ui.db_search import count_video_chunks, count_videos, get_video, search_video_chunks, search_videos


def _conn() -> Any:
    conn = libsql.connect(":memory:")  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
    init_schema(conn)
    return conn  # pyright: ignore[reportUnknownVariableType]


def _seed(conn: Any) -> tuple[int, int, int]:
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC1", "Chaîne", "gauche", "Alice")
    vid1 = upsert_video(conn, ch_id, "vid1", "Vidéo ancienne", "20240101", 120, "fr", "manual", "ok", None)
    vid2 = upsert_video(conn, ch_id, "vid2", "Vidéo récente", "20250615", 300, "fr", "manual", "ok", None)

    replace_chunks(conn, vid1, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="le travail est important", tokens=4),
        Chunk(seq_no=1, start_s=6, end_s=10, text="immigration et travail", tokens=3),
    ])
    replace_chunks(conn, vid2, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="discours sur l'immigration", tokens=4),
        Chunk(seq_no=1, start_s=6, end_s=10, text="travail et citoyenneté", tokens=3),
        Chunk(seq_no=2, start_s=11, end_s=15, text="le travail Alien beneficial", tokens=4),
    ])
    conn.commit()
    return ch_id, vid1, vid2


def test_search_videos_order_desc() -> None:
    conn = _conn()
    _seed(conn)
    results = search_videos(conn, "travail")
    assert len(results) == 2
    assert results[0].youtube_str_id == "vid2"
    assert results[1].youtube_str_id == "vid1"


def test_search_videos_mentions() -> None:
    conn = _conn()
    _seed(conn)
    results = search_videos(conn, "travail")
    vid2 = next(r for r in results if r.youtube_str_id == "vid2")
    vid1 = next(r for r in results if r.youtube_str_id == "vid1")
    assert vid2.mentions == 2
    assert vid1.mentions == 2


def test_search_videos_metadata() -> None:
    conn = _conn()
    _seed(conn)
    results = search_videos(conn, "travail")
    v = results[0]
    assert v.owner == "Alice"
    assert v.orientation == "gauche"
    assert v.title == "Vidéo récente"
    assert v.upload_date == "20250615"


def test_search_video_chunks_order() -> None:
    conn = _conn()
    _seed(conn)
    chunks = search_video_chunks(conn, "travail", "vid1")
    assert len(chunks) == 2
    assert chunks[0].seq_no < chunks[1].seq_no


def test_search_video_chunks_snippet_bold() -> None:
    conn = _conn()
    _seed(conn)
    chunks = search_video_chunks(conn, "travail", "vid1")
    for ch in chunks:
        assert "**" in ch.snippet


def test_search_video_chunks_pagination() -> None:
    conn = _conn()
    _seed(conn)
    all_chunks = search_video_chunks(conn, "travail OR immigration", "vid2", limit=10, offset=0)
    first_page = search_video_chunks(conn, "travail OR immigration", "vid2", limit=2, offset=0)
    second_page = search_video_chunks(conn, "travail OR immigration", "vid2", limit=2, offset=2)
    assert len(first_page) == 2
    assert len(second_page) == 1
    assert [c.seq_no for c in first_page] + [c.seq_no for c in second_page] == [c.seq_no for c in all_chunks]


def test_count_video_chunks() -> None:
    conn = _conn()
    _seed(conn)
    assert count_video_chunks(conn, "travail", "vid1") == 2
    assert count_video_chunks(conn, "travail", "vid2") == 2
    assert count_video_chunks(conn, "travail OR immigration", "vid2") == 3


def test_search_videos_empty_result() -> None:
    conn = _conn()
    _seed(conn)
    assert search_videos(conn, "zzzznonexistent") == []


def test_search_video_chunks_wrong_video() -> None:
    conn = _conn()
    _seed(conn)
    chunks = search_video_chunks(conn, "travail", "nonexistent")
    assert chunks == []


def test_count_videos() -> None:
    conn = _conn()
    _seed(conn)
    assert count_videos(conn, "travail") == 2
    assert count_videos(conn, "zzzznonexistent") == 0


def test_search_videos_pagination() -> None:
    conn = _conn()
    _seed(conn)
    first = search_videos(conn, "travail", limit=1, offset=0)
    second = search_videos(conn, "travail", limit=1, offset=1)
    assert [v.youtube_str_id for v in first] == ["vid2"]
    assert [v.youtube_str_id for v in second] == ["vid1"]
    assert search_videos(conn, "travail", limit=1, offset=5) == []


def test_search_videos_same_date_order_by_mentions_desc() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC1", "Chaîne", "gauche", "Alice")
    vid_low = upsert_video(conn, ch_id, "vidLow", "Vidéo peu citée", "20260601", 120, "fr", "manual", "ok", None)
    vid_high = upsert_video(conn, ch_id, "vidHigh", "Vidéo très citée", "20260601", 300, "fr", "manual", "ok", None)
    replace_chunks(conn, vid_low, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="le travail est important", tokens=4),
    ])
    replace_chunks(conn, vid_high, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="le travail est important", tokens=4),
        Chunk(seq_no=1, start_s=6, end_s=10, text="encore du travail ici", tokens=4),
        Chunk(seq_no=2, start_s=11, end_s=15, text="toujours du travail partout", tokens=4),
    ])
    conn.commit()
    results = search_videos(conn, "travail")
    assert [r.youtube_str_id for r in results] == ["vidHigh", "vidLow"]


def test_get_video() -> None:
    conn = _conn()
    _seed(conn)
    v = get_video(conn, "vid1")
    assert v is not None
    assert v.title == "Vidéo ancienne"
    assert v.owner == "Alice"
    assert get_video(conn, "unknown") is None
