from __future__ import annotations

import logging
from typing import Any

import libsql_experimental as libsql  # pyright: ignore[reportMissingModuleSource]

from lucas_v2.db import Chunk
from lucas_v2.db.operations import replace_chunks, upsert_channel, upsert_video
from lucas_v2.db.schema import init_schema
from lucas_v2.ui.db_search import (
    count_video_chunks,
    count_videos,
    get_video,
    search_chunks_by_channel,
    search_chunks_by_orientation,
    search_video_chunks,
    search_videos,
)


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


def test_search_videos_mentions_primary_order() -> None:
    """Les vidéos avec le plus de mentions passent en premier, même si plus anciennes."""
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC1", "Chaîne", "gauche", "Alice")
    vid_old_many = upsert_video(conn, ch_id, "vid_old_many", "Ancienne mais citée", "20240101", 300, "fr", "manual", "ok", None)
    vid_new_few = upsert_video(conn, ch_id, "vid_new_few", "Récente mais peu citée", "20250615", 120, "fr", "manual", "ok", None)
    replace_chunks(conn, vid_old_many, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="le travail est important", tokens=4),
        Chunk(seq_no=1, start_s=6, end_s=10, text="encore du travail ici", tokens=4),
        Chunk(seq_no=2, start_s=11, end_s=15, text="toujours du travail partout", tokens=4),
    ])
    replace_chunks(conn, vid_new_few, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="le travail c'est bien", tokens=4),
    ])
    conn.commit()
    results = search_videos(conn, "travail")
    assert len(results) == 2
    assert results[0].youtube_str_id == "vid_old_many"
    assert results[1].youtube_str_id == "vid_new_few"
    assert results[0].mentions == 3
    assert results[1].mentions == 1


def test_get_video() -> None:
    conn = _conn()
    _seed(conn)
    v = get_video(conn, "vid1")
    assert v is not None
    assert v.title == "Vidéo ancienne"
    assert v.owner == "Alice"
    assert get_video(conn, "unknown") is None


def test_search_chunks_by_orientation_single() -> None:
    conn = _conn()
    _seed(conn)
    stats = search_chunks_by_orientation(conn, "travail")
    assert len(stats) == 1
    s = stats[0]
    assert s.orientation == "gauche"
    assert s.matched == 4
    assert s.total == 5


def test_search_chunks_by_orientation_multi() -> None:
    conn = _conn()
    ch_gauche = upsert_channel(conn, "https://yt.com/ch1", "UC1", "Chaîne G", "gauche", "Alice")
    ch_droite = upsert_channel(conn, "https://yt.com/ch2", "UC2", "Chaîne D", "droite", "Bob")

    vid_g = upsert_video(conn, ch_gauche, "vidG", "Vid G", "20250101", 120, "fr", "manual", "ok", None)
    vid_d = upsert_video(conn, ch_droite, "vidD", "Vid D", "20250101", 120, "fr", "manual", "ok", None)

    replace_chunks(conn, vid_g, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="le travail est important", tokens=4),
        Chunk(seq_no=1, start_s=6, end_s=10, text="travail et société", tokens=3),
        Chunk(seq_no=2, start_s=11, end_s=15, text="autre sujet", tokens=2),
    ])
    replace_chunks(conn, vid_d, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="le travail des citoyens", tokens=4),
    ])
    conn.commit()

    stats = search_chunks_by_orientation(conn, "travail")
    assert len(stats) == 2
    by_orient = {s.orientation: s for s in stats}
    assert by_orient["gauche"].matched == 2
    assert by_orient["gauche"].total == 3
    assert by_orient["droite"].matched == 1
    assert by_orient["droite"].total == 1
    assert stats[0].matched / stats[0].total >= stats[1].matched / stats[1].total


def test_search_chunks_by_orientation_empty() -> None:
    conn = _conn()
    _seed(conn)
    stats = search_chunks_by_orientation(conn, "zzzznonexistent")
    assert stats == []


def test_error_fts_syntax_logs_warning(caplog: Any) -> None:
    conn = _conn()

    class _Conn:
        def __getattr__(self, name: str) -> Any:
            return getattr(conn, name)

        def execute(self, *args: Any, **kwargs: Any) -> Any:
            raise ValueError("fts5: syntax err")

    with caplog.at_level(logging.WARNING, logger="lucas_v2"):
        result = search_videos(_Conn(), "feu*")
    assert result == []
    assert "Requête FTS5 invalide" in caplog.text


def test_error_transitoire_logs_error(caplog: Any) -> None:
    conn = _conn()

    class _Conn:
        def __getattr__(self, name: str) -> Any:
            return getattr(conn, name)

        def execute(self, *args: Any, **kwargs: Any) -> Any:
            raise ValueError("network timeout")

    with caplog.at_level(logging.ERROR, logger="lucas_v2"):
        result = search_videos(_Conn(), "feu*")
    assert result == []
    assert "network timeout" in caplog.text


def test_valid_query_no_error_log(caplog: Any) -> None:
    conn = _conn()
    _seed(conn)
    with caplog.at_level(logging.WARNING, logger="lucas_v2"):
        result = search_videos(conn, "travail")
    assert len(result) == 2
    assert "Requête FTS5 invalide" not in caplog.text


def test_search_chunks_by_channel_single() -> None:
    conn = _conn()
    _seed(conn)
    stats = search_chunks_by_channel(conn, "travail")
    assert len(stats) == 1
    s = stats[0]
    assert s.owner == "Alice"
    assert s.orientation == "gauche"
    assert s.matched == 4
    assert s.total == 5


def test_search_chunks_by_channel_multi() -> None:
    conn = _conn()
    ch_gauche = upsert_channel(conn, "https://yt.com/ch1", "UC1", "Chaîne G", "gauche", "Alice")
    ch_droite = upsert_channel(conn, "https://yt.com/ch2", "UC2", "Chaîne D", "droite", "Bob")

    vid_g = upsert_video(conn, ch_gauche, "vidG", "Vid G", "20250101", 120, "fr", "manual", "ok", None)
    vid_d = upsert_video(conn, ch_droite, "vidD", "Vid D", "20250101", 120, "fr", "manual", "ok", None)

    replace_chunks(conn, vid_g, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="le travail est important", tokens=4),
        Chunk(seq_no=1, start_s=6, end_s=10, text="travail et société", tokens=3),
        Chunk(seq_no=2, start_s=11, end_s=15, text="autre sujet", tokens=2),
    ])
    replace_chunks(conn, vid_d, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="le travail des citoyens", tokens=4),
    ])
    conn.commit()

    stats = search_chunks_by_channel(conn, "travail")
    assert len(stats) == 2
    by_owner = {s.owner: s for s in stats}
    assert by_owner["Alice"].matched == 2
    assert by_owner["Alice"].total == 3
    assert by_owner["Bob"].matched == 1
    assert by_owner["Bob"].total == 1
    assert stats[0].matched / stats[0].total >= stats[1].matched / stats[1].total


def test_search_chunks_by_channel_empty() -> None:
    conn = _conn()
    _seed(conn)
    stats = search_chunks_by_channel(conn, "zzzznonexistent")
    assert stats == []


def test_search_chunks_by_channel_null_title() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch_null", "UC_NULL", None, "gauche", "Bob")
    vid = upsert_video(conn, ch_id, "vidNull", "Vid Null", "20250101", 120, "fr", "manual", "ok", None)
    replace_chunks(conn, vid, [
        Chunk(seq_no=0, start_s=0, end_s=5, text="le travail est important", tokens=4),
    ])
    conn.commit()
    stats = search_chunks_by_channel(conn, "travail")
    assert len(stats) == 1
    assert stats[0].owner == "Bob"


def test_search_videos_with_owner_filter() -> None:
    conn = _conn()
    ch_gauche = upsert_channel(conn, "https://yt.com/ch1", "UC1", "Chaîne G", "gauche", "Alice")
    ch_droite = upsert_channel(conn, "https://yt.com/ch2", "UC2", "Chaîne D", "droite", "Bob")
    vid_g = upsert_video(conn, ch_gauche, "vidG", "Vid G", "20250101", 120, "fr", "manual", "ok", None)
    vid_d = upsert_video(conn, ch_droite, "vidD", "Vid D", "20250101", 120, "fr", "manual", "ok", None)
    replace_chunks(conn, vid_g, [Chunk(seq_no=0, start_s=0, end_s=5, text="le travail est important", tokens=4)])
    replace_chunks(conn, vid_d, [Chunk(seq_no=0, start_s=0, end_s=5, text="le travail des citoyens", tokens=4)])
    conn.commit()

    all_results = search_videos(conn, "travail")
    assert len(all_results) == 2
    filtered = search_videos(conn, "travail", owner_filter="Alice")
    assert len(filtered) == 1
    assert filtered[0].youtube_str_id == "vidG"


def test_search_videos_with_both_filters() -> None:
    conn = _conn()
    ch1 = upsert_channel(conn, "https://yt.com/ch1", "UC1", "Chaîne G", "gauche", "Alice")
    ch2 = upsert_channel(conn, "https://yt.com/ch2", "UC2", "Chaîne D", "droite", "Bob")
    ch3 = upsert_channel(conn, "https://yt.com/ch3", "UC3", "Chaîne G2", "gauche", "Alice2")
    vid1 = upsert_video(conn, ch1, "v1", "V1", "20250101", 120, "fr", "manual", "ok", None)
    vid2 = upsert_video(conn, ch2, "v2", "V2", "20250101", 120, "fr", "manual", "ok", None)
    vid3 = upsert_video(conn, ch3, "v3", "V3", "20250101", 120, "fr", "manual", "ok", None)
    replace_chunks(conn, vid1, [Chunk(seq_no=0, start_s=0, end_s=5, text="le travail est important", tokens=4)])
    replace_chunks(conn, vid2, [Chunk(seq_no=0, start_s=0, end_s=5, text="le travail des citoyens", tokens=4)])
    replace_chunks(conn, vid3, [Chunk(seq_no=0, start_s=0, end_s=5, text="le travail pour tous", tokens=4)])
    conn.commit()

    assert len(search_videos(conn, "travail")) == 3
    assert len(search_videos(conn, "travail", owner_filter="Alice")) == 1
    assert len(search_videos(conn, "travail", owner_filter="Alice2")) == 1


def test_count_videos_with_filters() -> None:
    conn = _conn()
    ch_gauche = upsert_channel(conn, "https://yt.com/ch1", "UC1", "Chaîne G", "gauche", "Alice")
    ch_droite = upsert_channel(conn, "https://yt.com/ch2", "UC2", "Chaîne D", "droite", "Bob")
    vid_g = upsert_video(conn, ch_gauche, "vidG", "Vid G", "20250101", 120, "fr", "manual", "ok", None)
    vid_d = upsert_video(conn, ch_droite, "vidD", "Vid D", "20250101", 120, "fr", "manual", "ok", None)
    replace_chunks(conn, vid_g, [Chunk(seq_no=0, start_s=0, end_s=5, text="le travail est important", tokens=4)])
    replace_chunks(conn, vid_d, [Chunk(seq_no=0, start_s=0, end_s=5, text="le travail des citoyens", tokens=4)])
    conn.commit()

    assert count_videos(conn, "travail") == 2
    assert count_videos(conn, "travail", owner_filter="Alice") == 1
    assert count_videos(conn, "travail", owner_filter="Bob") == 1
