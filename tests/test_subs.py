from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from lucas_v2.subs import (
    RateLimitedError,
    _base_opts,
    _choose_track,
    _extract_meta,
    _run_with_retry,
    download_srt,
)


# ---------------------------------------------------------------------------
# Pure functions — no mocks
# ---------------------------------------------------------------------------

class TestChooseTrack:
    def test_fr_manual_priority(self) -> None:
        manual = {"fr", "en", "es"}
        auto: set[str] = set()
        assert _choose_track(manual, auto) == ("fr", "manual")

    def test_fr_orig_manual(self) -> None:
        manual = {"fr-orig", "en"}
        auto: set[str] = set()
        assert _choose_track(manual, auto) == ("fr-orig", "manual")

    def test_fr_auto(self) -> None:
        manual: set[str] = set()
        auto = {"fr", "en"}
        assert _choose_track(manual, auto) == ("fr", "auto")

    def test_fr_orig_auto(self) -> None:
        manual: set[str] = set()
        auto = {"fr-orig", "en"}
        assert _choose_track(manual, auto) == ("fr-orig", "auto")

    def test_no_french(self) -> None:
        manual = {"en", "es"}
        auto = {"de"}
        assert _choose_track(manual, auto) == (None, None)

    def test_manual_preferred_over_auto(self) -> None:
        manual = {"fr"}
        auto = {"fr", "fr-orig"}
        assert _choose_track(manual, auto) == ("fr", "manual")

    def test_fr_orig_manual_beats_fr_auto(self) -> None:
        manual = {"fr-orig"}
        auto = {"fr"}
        assert _choose_track(manual, auto) == ("fr-orig", "manual")

    def test_empty_sets(self) -> None:
        assert _choose_track(set(), set()) == (None, None)


class TestExtractMeta:
    def test_extracts_all_fields(self) -> None:
        info: dict[str, Any] = {
            "title": "My Video",
            "upload_date": "20250115",
            "duration": 300,
            "channel_url": "https://youtube.com/@ch",
            "id": "vid123",
        }
        meta = _extract_meta(info)
        assert meta["title"] == "My Video"
        assert meta["upload_date"] == "20250115"
        assert meta["duration"] == 300
        assert meta["channel_url"] == "https://youtube.com/@ch"
        assert meta["video_id"] == "vid123"

    def test_missing_fields(self) -> None:
        meta = _extract_meta({})
        assert meta["title"] is None
        assert meta["upload_date"] is None
        assert meta["duration"] is None
        assert meta["channel_url"] is None
        assert meta["video_id"] is None


class TestBaseOpts:
    def test_returns_dict(self) -> None:
        opts = _base_opts("/tmp/test")
        assert isinstance(opts, dict)
        assert opts["skip_download"] is True
        assert opts["quiet"] is True
        assert opts["retries"] == 3
        assert "/tmp/test" in opts["outtmpl"]


# ---------------------------------------------------------------------------
# Mocked yt-dlp tests
# ---------------------------------------------------------------------------

class TestDownloadSrt:
    @patch("lucas_v2.subs.shutil.rmtree")
    @patch("lucas_v2.subs._do_download")
    @patch("lucas_v2.subs.tempfile.mkdtemp", return_value="/tmp/testdir")
    def test_returns_do_download_result(
        self, mock_mkdtemp: MagicMock, mock_do: MagicMock, mock_rmtree: MagicMock
    ) -> None:
        mock_do.return_value = ("srt text", "fr", "manual", {"title": "T"})
        result = download_srt("vid123")
        assert result == ("srt text", "fr", "manual", {"title": "T"})
        mock_rmtree.assert_called_once()

    @patch("lucas_v2.subs.shutil.rmtree")
    @patch("lucas_v2.subs._do_download")
    @patch("lucas_v2.subs.tempfile.mkdtemp", return_value="/tmp/testdir")
    def test_cleansup_on_error(
        self, mock_mkdtemp: MagicMock, mock_do: MagicMock, mock_rmtree: MagicMock
    ) -> None:
        mock_do.side_effect = RuntimeError("boom")
        try:
            download_srt("vid123")
        except RuntimeError:
            pass
        mock_rmtree.assert_called_once()


class TestRunWithRetry:
    @patch("lucas_v2.subs.yt_dlp.YoutubeDL")
    def test_success_no_retry(self, mock_ydl_cls: MagicMock) -> None:
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        _run_with_retry({}, "https://example.com")
        mock_ydl.extract_info.assert_called_once()

    @patch("lucas_v2.subs.time.sleep")
    @patch("lucas_v2.subs._retry_download")
    @patch("lucas_v2.subs.yt_dlp.YoutubeDL")
    def test_429_triggers_retry(
        self, mock_ydl_cls: MagicMock, mock_retry: MagicMock, mock_sleep: MagicMock
    ) -> None:
        from yt_dlp.utils import DownloadError

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = DownloadError("HTTP Error 429")
        _run_with_retry({}, "https://example.com")
        mock_sleep.assert_called_once_with(60)
        mock_retry.assert_called_once()

    @patch("lucas_v2.subs.yt_dlp.YoutubeDL")
    def test_non_429_error_raises(self, mock_ydl_cls: MagicMock) -> None:
        from yt_dlp.utils import DownloadError

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = DownloadError("HTTP Error 404")
        try:
            _run_with_retry({}, "https://example.com")
            assert False, "Should have raised"
        except DownloadError:
            pass


class TestRetryDownload:
    @patch("lucas_v2.subs.yt_dlp.YoutubeDL")
    def test_success(self, mock_ydl_cls: MagicMock) -> None:
        from lucas_v2.subs import _retry_download

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        _retry_download({}, "https://example.com")
        mock_ydl.extract_info.assert_called_once()

    @patch("lucas_v2.subs.yt_dlp.YoutubeDL")
    def test_429_raises_rate_limited(self, mock_ydl_cls: MagicMock) -> None:
        from lucas_v2.subs import _retry_download
        from yt_dlp.utils import DownloadError

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = DownloadError("HTTP Error 429")
        try:
            _retry_download({}, "https://example.com")
            assert False, "Should have raised"
        except RateLimitedError as e:
            assert "Rate-limit" in str(e)

    @patch("lucas_v2.subs.yt_dlp.YoutubeDL")
    def test_non_429_error_raises(self, mock_ydl_cls: MagicMock) -> None:
        from lucas_v2.subs import _retry_download
        from yt_dlp.utils import DownloadError

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = DownloadError("HTTP Error 404")
        try:
            _retry_download({}, "https://example.com")
            assert False, "Should have raised"
        except DownloadError:
            pass
