from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import libsql_experimental as libsql  # pyright: ignore[reportMissingModuleSource]

from lucas_v2.db import Chunk
from lucas_v2.db.connection import DbConn
from lucas_v2.db.operations import (
    fetch_existing_ids,
    find_video_channel,
    get_channel_url,
    replace_chunks,
    search_chunks,
    upsert_channel,
    upsert_video,
    video_exists,
)
from lucas_v2.db.schema import init_schema


def _conn() -> Any:
    conn = libsql.connect(":memory:")  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
    init_schema(conn)
    return conn  # pyright: ignore[reportUnknownVariableType]


def test_upsert_channel_returns_id() -> None:
    conn = _conn()
    row_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Chaîne 1", "gauche", None)
    assert isinstance(row_id, int)
    assert row_id > 0


def test_upsert_channel_on_conflict_updates() -> None:
    conn = _conn()
    id1 = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ancien titre", None, None)
    id2 = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Nouveau titre", "droite", None)
    assert id1 == id2
    row = conn.execute("SELECT title, orientation FROM channel WHERE id=?", (id1,)).fetchone()
    assert row[0] == "Nouveau titre"
    assert row[1] == "droite"


def test_upsert_video_returns_id() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    vid_id = upsert_video(
        conn, ch_id, "vid1", "Titre", "20250101", 120, "fr", "manual",
        "ok", None,
    )
    assert isinstance(vid_id, int)
    assert vid_id > 0


def test_upsert_video_on_conflict_updates() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    id1 = upsert_video(
        conn, ch_id, "vid1", "Titre 1", None, None, None, None, "ok", None,
    )
    id2 = upsert_video(
        conn, ch_id, "vid1", "Titre 2", None, None, None, None, "error", "oops",
    )
    assert id1 == id2
    row = conn.execute("SELECT title, status, error FROM video WHERE id=?", (id1,)).fetchone()
    assert row[0] == "Titre 2"
    assert row[1] == "error"
    assert row[2] == "oops"


def test_replace_chunks_inserts() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    vid_id = upsert_video(
        conn, ch_id, "vid1", "T", None, None, None, None, "ok", None,
    )
    chunks = [
        Chunk(seq_no=0, start_s=0, end_s=5, text="hello world", tokens=2),
        Chunk(seq_no=1, start_s=6, end_s=10, text="foo bar baz", tokens=3),
        Chunk(seq_no=2, start_s=11, end_s=15, text="test", tokens=1),
    ]
    replace_chunks(conn, vid_id, chunks)
    conn.commit()
    rows = conn.execute("SELECT COUNT(*) FROM transcript_chunk WHERE fk_video_id=?", (vid_id,)).fetchone()
    assert rows[0] == 3


def test_replace_chunks_delete_existing() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    vid_id = upsert_video(
        conn, ch_id, "vid1", "T", None, None, None, None, "ok", None,
    )
    old_chunks = [Chunk(seq_no=0, start_s=0, end_s=5, text="old", tokens=1)]
    replace_chunks(conn, vid_id, old_chunks)
    conn.commit()

    new_chunks = [
        Chunk(seq_no=0, start_s=0, end_s=3, text="new a", tokens=1),
        Chunk(seq_no=1, start_s=4, end_s=8, text="new b", tokens=1),
    ]
    replace_chunks(conn, vid_id, new_chunks, delete_existing=True)
    conn.commit()

    rows = conn.execute("SELECT text FROM transcript_chunk WHERE fk_video_id=? ORDER BY seq_no", (vid_id,)).fetchall()
    assert len(rows) == 2
    assert rows[0][0] == "new a"
    assert rows[1][0] == "new b"


def test_replace_chunks_no_delete() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    vid_id = upsert_video(
        conn, ch_id, "vid1", "T", None, None, None, None, "ok", None,
    )
    old_chunks = [Chunk(seq_no=0, start_s=0, end_s=5, text="old", tokens=1)]
    replace_chunks(conn, vid_id, old_chunks)
    conn.commit()

    new_chunks = [Chunk(seq_no=1, start_s=6, end_s=10, text="new", tokens=1)]
    replace_chunks(conn, vid_id, new_chunks, delete_existing=False)
    conn.commit()

    rows = conn.execute("SELECT COUNT(*) FROM transcript_chunk WHERE fk_video_id=?", (vid_id,)).fetchone()
    assert rows[0] == 2


def test_replace_chunks_empty_list() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    vid_id = upsert_video(
        conn, ch_id, "vid1", "T", None, None, None, None, "ok", None,
    )
    replace_chunks(conn, vid_id, [])
    conn.commit()


def test_video_exists_true() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    upsert_video(conn, ch_id, "vid1", "T", None, None, None, None, "ok", None)
    assert video_exists(conn, "vid1") is True


def test_video_exists_false() -> None:
    conn = _conn()
    assert video_exists(conn, "nonexistent") is False


def test_fetch_existing_ids_empty() -> None:
    conn = _conn()
    assert fetch_existing_ids(conn, []) == set()


def test_fetch_existing_ids_single_existing() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    upsert_video(conn, ch_id, "vid1", "T", None, None, None, None, "ok", None)
    assert fetch_existing_ids(conn, ["vid1"]) == {"vid1"}


def test_fetch_existing_ids_single_missing() -> None:
    conn = _conn()
    assert fetch_existing_ids(conn, ["nope"]) == set()


def test_fetch_existing_ids_mix_and_duplicates() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    upsert_video(conn, ch_id, "vid1", "T", None, None, None, None, "ok", None)
    upsert_video(conn, ch_id, "vid2", "T", None, None, None, None, "ok", None)
    result = fetch_existing_ids(conn, ["vid1", "vid2", "vid1", "missing"])
    assert result == {"vid1", "vid2"}


def test_fetch_existing_ids_400() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    ids = [f"vid{i:04d}" for i in range(400)]
    for vid in ids:
        upsert_video(conn, ch_id, vid, "T", None, None, None, None, "ok", None)
    result = fetch_existing_ids(conn, ids)
    assert result == set(ids)


def test_find_video_channel_found() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    upsert_video(conn, ch_id, "vid1", "T", None, None, None, None, "ok", None)
    result = find_video_channel(conn, "vid1")
    assert result is not None
    assert result[0] == ch_id
    assert result[1] == "UC123"


def test_find_video_channel_not_found() -> None:
    conn = _conn()
    assert find_video_channel(conn, "nonexistent") is None


def test_get_channel_url_found() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    url = get_channel_url(conn, ch_id)
    assert url == "https://yt.com/ch1"


def test_get_channel_url_not_found() -> None:
    conn = _conn()
    assert get_channel_url(conn, 999) is None


def test_search_chunks() -> None:
    conn = _conn()
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC123", "Ch", None, None)
    vid_id = upsert_video(
        conn, ch_id, "vid1", "T", None, None, None, None, "ok", None,
    )
    chunks = [
        Chunk(seq_no=0, start_s=0, end_s=5, text="bonjour le monde", tokens=3),
        Chunk(seq_no=1, start_s=6, end_s=10, text="python est génial", tokens=3),
    ]
    replace_chunks(conn, vid_id, chunks)
    conn.commit()

    results = search_chunks(conn, "bonjour")
    assert len(results) >= 1
    assert results[0]["text"] == "bonjour le monde"
    assert results[0]["youtube_id"] == "vid1"


# ---------------------------------------------------------------------------
# DbConn auto-reconnection
# ---------------------------------------------------------------------------

class TestDbConn:
    def test_execute_reconnects_on_stream_not_found(self) -> None:
        mock_conn1 = MagicMock()
        mock_conn2 = MagicMock()
        mock_conn1.execute.side_effect = ValueError("stream not found: abc123")
        fake_result = MagicMock()
        mock_conn2.execute.return_value = fake_result

        wrapper = DbConn(mock_conn1)

        with patch("lucas_v2.db.connection._raw_connect", return_value=mock_conn2):
            result = wrapper.execute("SELECT 1", ())

        mock_conn2.execute.assert_called_once_with("SELECT 1", ())
        assert result is fake_result

    def test_execute_raises_other_valueerrors(self) -> None:
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = ValueError("some other error")
        wrapper = DbConn(mock_conn)

        try:
            wrapper.execute("SELECT 1")
            assert False, "Should have raised"
        except ValueError as e:
            assert "some other error" in str(e)

    def test_commit_reconnects_on_stream_not_found(self) -> None:
        mock_conn1 = MagicMock()
        mock_conn2 = MagicMock()
        mock_conn1.commit.side_effect = ValueError("stream not found: xyz")

        wrapper = DbConn(mock_conn1)

        with patch("lucas_v2.db.connection._raw_connect", return_value=mock_conn2):
            wrapper.commit()

        mock_conn2.commit.assert_called_once()

    def test_commit_raises_other_valueerrors(self) -> None:
        mock_conn = MagicMock()
        mock_conn.commit.side_effect = ValueError("disk full")
        wrapper = DbConn(mock_conn)

        try:
            wrapper.commit()
            assert False, "Should have raised"
        except ValueError as e:
            assert "disk full" in str(e)

    def test_executescript_reconnects_on_stream_not_found(self) -> None:
        mock_conn1 = MagicMock()
        mock_conn2 = MagicMock()
        mock_conn1.executescript.side_effect = ValueError("stream not found: def456")

        wrapper = DbConn(mock_conn1)

        with patch("lucas_v2.db.connection._raw_connect", return_value=mock_conn2):
            wrapper.executescript("CREATE TABLE t (id INT)")

        mock_conn2.executescript.assert_called_once_with("CREATE TABLE t (id INT)")

    def test_rollback_reconnects_on_stream_not_found(self) -> None:
        mock_conn1 = MagicMock()
        mock_conn2 = MagicMock()
        mock_conn1.rollback.side_effect = ValueError("stream not found: ghi789")

        wrapper = DbConn(mock_conn1)

        with patch("lucas_v2.db.connection._raw_connect", return_value=mock_conn2):
            wrapper.rollback()

        # Rollback after stream loss just reconnects (no retry needed, transaction is dead)
        mock_conn2.rollback.assert_not_called()

    def test_execute_reconnects_only_once(self) -> None:
        mock_conn1 = MagicMock()
        mock_conn2 = MagicMock()
        mock_conn1.execute.side_effect = ValueError("stream not found: once")
        mock_conn2.execute.side_effect = ValueError("stream not found: again")

        wrapper = DbConn(mock_conn1)

        with patch("lucas_v2.db.connection._raw_connect", return_value=mock_conn2):
            try:
                wrapper.execute("SELECT 1")
                assert False, "Should have raised"
            except ValueError as e:
                assert "stream not found: again" in str(e)

        # _raw_connect called only once (no infinite loop)
        pass
