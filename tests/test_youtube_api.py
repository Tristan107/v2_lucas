from __future__ import annotations

from unittest.mock import MagicMock, patch

from lucas_v2.youtube_api import (
    _extract_channel_ref,
    _iso_to_yyyymmdd,
    _parse_iso_duration,
    _process_playlist_item,
    list_videos,
    resolve_channel_id,
)


# ---------------------------------------------------------------------------
# Pure utility functions — no mocks
# ---------------------------------------------------------------------------

class TestParseIsoDuration:
    def test_pt1h2m3s(self) -> None:
        assert _parse_iso_duration("PT1H2M3S") == 3723

    def test_pt5m(self) -> None:
        assert _parse_iso_duration("PT5M") == 300

    def test_pt30s(self) -> None:
        assert _parse_iso_duration("PT30S") == 30

    def test_pt1h(self) -> None:
        assert _parse_iso_duration("PT1H") == 3600

    def test_empty_string(self) -> None:
        assert _parse_iso_duration("") is None

    def test_not_pt_prefix(self) -> None:
        assert _parse_iso_duration("P1D") is None

    def test_pt0s_returns_none(self) -> None:
        assert _parse_iso_duration("PT0S") is None

    def test_pt1h30m(self) -> None:
        assert _parse_iso_duration("PT1H30M") == 5400


class TestIsoToYyyymmdd:
    def test_valid_date(self) -> None:
        assert _iso_to_yyyymmdd("2025-01-15T10:30:00Z") == "20250115"

    def test_valid_with_offset(self) -> None:
        assert _iso_to_yyyymmdd("2025-12-31T23:59:59+00:00") == "20251231"

    def test_empty_string(self) -> None:
        assert _iso_to_yyyymmdd("") is None

    def test_invalid_date(self) -> None:
        assert _iso_to_yyyymmdd("not-a-date") is None


class TestExtractChannelRef:
    def test_uc_id_url(self) -> None:
        kind, value = _extract_channel_ref("https://www.youtube.com/channel/UC1234567890abcdef1234")
        assert kind == "id"
        assert value == "UC1234567890abcdef1234"

    def test_handle_url(self) -> None:
        kind, value = _extract_channel_ref("https://www.youtube.com/@HandleName")
        assert kind == "handle"
        assert value == "@HandleName"

    def test_handle_url_with_extras(self) -> None:
        kind, value = _extract_channel_ref("https://www.youtube.com/@HandleName/videos")
        assert kind == "handle"
        assert value == "@HandleName"

    def test_bare_handle(self) -> None:
        kind, value = _extract_channel_ref("@Someone")
        assert kind == "handle"
        assert value == "@Someone"

    def test_plain_name(self) -> None:
        kind, value = _extract_channel_ref("SomeChannel")
        assert kind == "handle"
        assert value == "@SomeChannel"

    def test_c_channel_url(self) -> None:
        kind, value = _extract_channel_ref("https://www.youtube.com/c/SomeChannel")
        assert kind == "query"
        assert value == "SomeChannel"

    def test_user_url(self) -> None:
        kind, value = _extract_channel_ref("https://www.youtube.com/user/SomeUser")
        assert kind == "query"
        assert value == "SomeUser"

    def test_strips_trailing_slash(self) -> None:
        kind, value = _extract_channel_ref("https://www.youtube.com/@Handle/")
        assert kind == "handle"
        assert value == "@Handle"

    def test_strips_whitespace(self) -> None:
        kind, value = _extract_channel_ref("  @Handle  ")
        assert kind == "handle"
        assert value == "@Handle"

    def test_query_fallback_complex(self) -> None:
        kind, value = _extract_channel_ref("https://example.com/something")
        assert kind == "query"
        assert value == "https://example.com/something"


# ---------------------------------------------------------------------------
# _process_playlist_item — pure function
# ---------------------------------------------------------------------------

class TestProcessPlaylistItem:
    def test_extracts_video_id(self) -> None:
        item = {
            "snippet": {"publishedAt": "2025-01-15T10:00:00Z", "title": "Test"},
            "contentDetails": {"videoId": "abc123"},
        }
        video_ids: list[str] = []
        video_meta: dict[str, dict[str, str]] = {}
        result = _process_playlist_item(item, None, video_ids, video_meta)
        assert result is False
        assert video_ids == ["abc123"]
        assert video_meta["abc123"]["title"] == "Test"

    def test_no_video_id(self) -> None:
        item = {"snippet": {"publishedAt": ""}, "contentDetails": {}}
        video_ids: list[str] = []
        video_meta: dict[str, dict[str, str]] = {}
        result = _process_playlist_item(item, None, video_ids, video_meta)
        assert result is False
        assert video_ids == []

    def test_cutoff_reached(self) -> None:
        from datetime import datetime, timezone

        item = {
            "snippet": {"publishedAt": "2020-01-01T00:00:00Z", "title": "Old"},
            "contentDetails": {"videoId": "old1"},
        }
        cutoff = datetime(2024, 1, 1, tzinfo=timezone.utc)
        video_ids: list[str] = []
        video_meta: dict[str, dict[str, str]] = {}
        result = _process_playlist_item(item, cutoff, video_ids, video_meta)
        assert result is True
        assert video_ids == []

    def test_before_cutoff_keeps_video(self) -> None:
        from datetime import datetime, timezone

        item = {
            "snippet": {"publishedAt": "2025-06-01T00:00:00Z", "title": "Recent"},
            "contentDetails": {"videoId": "rec1"},
        }
        cutoff = datetime(2024, 1, 1, tzinfo=timezone.utc)
        video_ids: list[str] = []
        video_meta: dict[str, dict[str, str]] = {}
        result = _process_playlist_item(item, cutoff, video_ids, video_meta)
        assert result is False
        assert video_ids == ["rec1"]

    def test_resource_id_fallback(self) -> None:
        item = {
            "snippet": {
                "publishedAt": "2025-01-01T00:00:00Z",
                "title": "Fallback",
                "resourceId": {"videoId": "res1"},
            },
            "contentDetails": {},
        }
        video_ids: list[str] = []
        video_meta: dict[str, dict[str, str]] = {}
        _process_playlist_item(item, None, video_ids, video_meta)
        assert video_ids == ["res1"]


# ---------------------------------------------------------------------------
# API-calling functions — mocked youtube client
# ---------------------------------------------------------------------------

def _mock_youtube() -> MagicMock:
    return MagicMock()


class TestResolveChannelId:
    @patch("lucas_v2.youtube_api._get_client")
    def test_by_id(self, mock_get_client: MagicMock) -> None:
        mock_yt = _mock_youtube()
        mock_get_client.return_value = mock_yt
        mock_yt.channels().list().execute.return_value = {
            "items": [{"id": "UC123", "snippet": {"title": "My Channel"}}]
        }
        ch_id, title = resolve_channel_id("https://youtube.com/channel/UC1234567890abcdefghij")
        assert ch_id == "UC123"
        assert title == "My Channel"

    @patch("lucas_v2.youtube_api._get_client")
    def test_by_handle(self, mock_get_client: MagicMock) -> None:
        mock_yt = _mock_youtube()
        mock_get_client.return_value = mock_yt
        mock_yt.channels().list().execute.return_value = {
            "items": [{"id": "UC456", "snippet": {"title": "Handle Chan"}}]
        }
        ch_id, title = resolve_channel_id("@MyHandle")
        assert ch_id == "UC456"
        assert title == "Handle Chan"

    @patch("lucas_v2.youtube_api._get_client")
    def test_by_search_fallback(self, mock_get_client: MagicMock) -> None:
        mock_yt = _mock_youtube()
        mock_get_client.return_value = mock_yt
        # handle resolution returns empty → falls back to search
        mock_yt.channels().list().execute.return_value = {"items": []}
        mock_yt.search().list().execute.return_value = {
            "items": [{"snippet": {"channelId": "UC789", "title": "Found"}}]
        }
        ch_id, title = resolve_channel_id("SomeUnknownChannel")
        assert ch_id == "UC789"
        assert title == "Found"

    @patch("lucas_v2.youtube_api._get_client")
    def test_not_found_raises(self, mock_get_client: MagicMock) -> None:
        mock_yt = _mock_youtube()
        mock_get_client.return_value = mock_yt
        mock_yt.channels().list().execute.return_value = {"items": []}
        mock_yt.search().list().execute.return_value = {"items": []}
        try:
            resolve_channel_id("Nonexistent")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "introuvable" in str(e)


class TestListVideos:
    @patch("lucas_v2.youtube_api._get_client")
    def test_returns_videos(self, mock_get_client: MagicMock) -> None:
        mock_yt = _mock_youtube()
        mock_get_client.return_value = mock_yt

        mock_yt.channels().list().execute.return_value = {
            "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "PL123"}}}]
        }
        mock_yt.playlistItems().list().execute.return_value = {
            "items": [
                {
                    "snippet": {"publishedAt": "2025-01-15T10:00:00Z", "title": "Vid1"},
                    "contentDetails": {"videoId": "v1"},
                }
            ],
            "nextPageToken": None,
        }
        mock_yt.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "v1",
                    "contentDetails": {"duration": "PT5M30S"},
                    "snippet": {"title": "Vid1"},
                }
            ]
        }
        videos = list_videos("UC123", max_videos=1)
        assert len(videos) == 1
        assert videos[0]["video_id"] == "v1"
        assert videos[0]["duration_s"] == 330

    @patch("lucas_v2.youtube_api._get_client")
    def test_empty_channel(self, mock_get_client: MagicMock) -> None:
        mock_yt = _mock_youtube()
        mock_get_client.return_value = mock_yt
        mock_yt.channels().list().execute.return_value = {"items": []}
        videos = list_videos("UC_empty", max_videos=1)
        assert videos == []

    @patch("lucas_v2.youtube_api._get_client")
    def test_no_videos_in_playlist(self, mock_get_client: MagicMock) -> None:
        mock_yt = _mock_youtube()
        mock_get_client.return_value = mock_yt
        mock_yt.channels().list().execute.return_value = {
            "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "PL_empty"}}}]
        }
        mock_yt.playlistItems().list().execute.return_value = {
            "items": [],
            "nextPageToken": None,
        }
        videos = list_videos("UC123", max_videos=5)
        assert videos == []
