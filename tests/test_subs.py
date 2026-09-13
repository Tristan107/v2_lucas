from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from lucas_v2.ingest.subs import (
    AbortIngestion,
    MAX_CONSECUTIVE_429,
    RETRY_DELAYS_S,
    RateLimitState,
    RateLimitedError,
    backoff_delay,
    base_opts,
    choose_track,
    check_abort,
    extract_meta,
    is_retryable,
    record_429,
    reset_rate_limit,
    run_with_retry,
    download_srt,
)


# ---------------------------------------------------------------------------
# Pure functions — no mocks
# ---------------------------------------------------------------------------

class TestRateLimitState:
    def test_record_429_increments(self) -> None:
        state = RateLimitState()
        record_429(state)
        assert state.consecutive_429 == 1

    def test_record_429_accumulates(self) -> None:
        state = RateLimitState()
        record_429(state)
        record_429(state)
        record_429(state)
        assert state.consecutive_429 == 3

    def test_reset_rate_limit(self) -> None:
        state = RateLimitState(consecutive_429=5)
        reset_rate_limit(state)
        assert state.consecutive_429 == 0

    def test_check_abort_below_threshold(self) -> None:
        state = RateLimitState(consecutive_429=MAX_CONSECUTIVE_429 - 1)
        check_abort(state, "https://example.com")
        assert state.consecutive_429 == MAX_CONSECUTIVE_429 - 1

    def test_check_abort_at_threshold(self) -> None:
        state = RateLimitState(consecutive_429=MAX_CONSECUTIVE_429)
        with pytest.raises(AbortIngestion, match="6x HTTP 429"):
            check_abort(state, "https://example.com")

    def test_check_abort_above_threshold(self) -> None:
        state = RateLimitState(consecutive_429=MAX_CONSECUTIVE_429 + 1)
        with pytest.raises(AbortIngestion):
            check_abort(state, "https://example.com")


class TestChooseTrack:
    def test_fr_manual_priority(self) -> None:
        manual = {"fr", "en", "es"}
        auto: set[str] = set()
        assert choose_track(manual, auto) == ("fr", "manual")

    def test_fr_orig_manual(self) -> None:
        manual = {"fr-orig", "en"}
        auto: set[str] = set()
        assert choose_track(manual, auto) == ("fr-orig", "manual")

    def test_fr_auto(self) -> None:
        manual: set[str] = set()
        auto = {"fr", "en"}
        assert choose_track(manual, auto) == ("fr", "auto")

    def test_fr_orig_auto(self) -> None:
        manual: set[str] = set()
        auto = {"fr-orig", "en"}
        assert choose_track(manual, auto) == ("fr-orig", "auto")

    def test_no_french(self) -> None:
        manual = {"en", "es"}
        auto = {"de"}
        assert choose_track(manual, auto) == (None, None)

    def test_manual_preferred_over_auto(self) -> None:
        manual = {"fr"}
        auto = {"fr", "fr-orig"}
        assert choose_track(manual, auto) == ("fr", "manual")

    def test_fr_orig_manual_beats_fr_auto(self) -> None:
        manual = {"fr-orig"}
        auto = {"fr"}
        assert choose_track(manual, auto) == ("fr-orig", "manual")

    def test_empty_sets(self) -> None:
        assert choose_track(set(), set()) == (None, None)


class TestExtractMeta:
    def test_extracts_all_fields(self) -> None:
        info: dict[str, Any] = {
            "title": "My Video",
            "upload_date": "20250115",
            "duration": 300,
            "channel_url": "https://youtube.com/@ch",
            "id": "vid123",
        }
        meta = extract_meta(info)
        assert meta["title"] == "My Video"
        assert meta["upload_date"] == "20250115"
        assert meta["duration"] == 300
        assert meta["channel_url"] == "https://youtube.com/@ch"
        assert meta["video_id"] == "vid123"

    def test_missing_fields(self) -> None:
        meta = extract_meta({})
        assert meta["title"] is None
        assert meta["upload_date"] is None
        assert meta["duration"] is None
        assert meta["channel_url"] is None
        assert meta["video_id"] is None


class TestBaseOpts:
    def test_returns_dict(self) -> None:
        opts = base_opts("/tmp/test")
        assert isinstance(opts, dict)
        assert opts["skip_download"] is True
        assert opts["quiet"] is True
        assert opts["retries"] == 3
        assert opts["extractor_retries"] == 2
        assert opts["fragment_retries"] == 2
        assert opts["retry_sleep"] == {"extractor": 30}
        assert "/tmp/test" in opts["outtmpl"]


class TestIsRetryable:
    def test_429is_retryable(self) -> None:
        assert is_retryable(Exception("HTTP Error 429")) is True

    def test_404_not_retryable(self) -> None:
        assert is_retryable(Exception("HTTP Error 404")) is False

    def test_empty_not_retryable(self) -> None:
        assert is_retryable(Exception("")) is False


class TestBackoffDelay:
    def test_uses_retry_after_header(self) -> None:
        delay = backoff_delay(0, Exception("Retry-After: 45"))
        assert delay == 45.0

    def test_uses_table_when_no_header(self) -> None:
        delay = backoff_delay(1, Exception("429"))
        assert RETRY_DELAYS_S[1] <= delay <= RETRY_DELAYS_S[1] + 5.0


# ---------------------------------------------------------------------------
# Mocked yt-dlp tests
# ---------------------------------------------------------------------------

class TestDownloadSrt:
    @patch("lucas_v2.ingest.subs.shutil.rmtree")
    @patch("lucas_v2.ingest.subs.do_download")
    @patch("lucas_v2.ingest.subs.tempfile.mkdtemp", return_value="/tmp/testdir")
    def test_returns_do_download_result(
        self, mock_mkdtemp: MagicMock, mock_do: MagicMock, mock_rmtree: MagicMock
    ) -> None:
        mock_do.return_value = ("srt text", "fr", "manual", {"title": "T"})
        rate_state = RateLimitState()
        result = download_srt("vid123", rate_state)
        assert result == ("srt text", "fr", "manual", {"title": "T"})
        mock_rmtree.assert_called_once()

    @patch("lucas_v2.ingest.subs.shutil.rmtree")
    @patch("lucas_v2.ingest.subs.do_download")
    @patch("lucas_v2.ingest.subs.tempfile.mkdtemp", return_value="/tmp/testdir")
    def test_cleansup_on_error(
        self, mock_mkdtemp: MagicMock, mock_do: MagicMock, mock_rmtree: MagicMock
    ) -> None:
        mock_do.side_effect = RuntimeError("boom")
        rate_state = RateLimitState()
        try:
            download_srt("vid123", rate_state)
        except RuntimeError:
            pass
        mock_rmtree.assert_called_once()


class TestRunWithRetry:
    @patch("lucas_v2.ingest.subs.yt_dlp.YoutubeDL")
    def test_success_no_retry(self, mock_ydl_cls: MagicMock) -> None:
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        rate_state = RateLimitState()
        run_with_retry({}, "https://example.com", rate_state)
        mock_ydl.extract_info.assert_called_once()
        assert rate_state.consecutive_429 == 0

    @patch("lucas_v2.ingest.subs.time.sleep", return_value=None)
    @patch("lucas_v2.ingest.subs.random.uniform", return_value=0.0)
    @patch("lucas_v2.ingest.subs.yt_dlp.YoutubeDL")
    def test_429_retries_3x(
        self, mock_ydl_cls: MagicMock, mock_uniform: MagicMock, mock_sleep: MagicMock
    ) -> None:
        from yt_dlp.utils import DownloadError

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = DownloadError("HTTP Error 429")
        rate_state = RateLimitState()
        try:
            run_with_retry({}, "https://example.com", rate_state)
            assert False, "Should have raised"
        except RateLimitedError:
            pass
        assert mock_sleep.call_count == 2
        mock_ydl.extract_info.assert_called()
        assert rate_state.consecutive_429 == 3

    @patch("lucas_v2.ingest.subs.time.sleep", return_value=None)
    @patch("lucas_v2.ingest.subs.random.uniform", return_value=0.0)
    @patch("lucas_v2.ingest.subs.yt_dlp.YoutubeDL")
    def test_429_retry_after_header(
        self, mock_ydl_cls: MagicMock, mock_uniform: MagicMock, mock_sleep: MagicMock
    ) -> None:
        from yt_dlp.utils import DownloadError

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = DownloadError("429 Retry-After: 45")
        rate_state = RateLimitState()
        try:
            run_with_retry({}, "https://example.com", rate_state)
            assert False, "Should have raised"
        except RateLimitedError:
            pass
        mock_sleep.assert_called_with(45.0)

    @patch("lucas_v2.ingest.subs.yt_dlp.YoutubeDL")
    def test_non_429_error_raises(self, mock_ydl_cls: MagicMock) -> None:
        from yt_dlp.utils import DownloadError

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = DownloadError("HTTP Error 404")
        rate_state = RateLimitState()
        try:
            run_with_retry({}, "https://example.com", rate_state)
            assert False, "Should have raised"
        except DownloadError:
            pass
        assert rate_state.consecutive_429 == 0

    @patch("lucas_v2.ingest.subs.time.sleep", return_value=None)
    @patch("lucas_v2.ingest.subs.random.uniform", return_value=0.0)
    @patch("lucas_v2.ingest.subs.yt_dlp.YoutubeDL")
    def test_429_abort_at_threshold(
        self, mock_ydl_cls: MagicMock, mock_uniform: MagicMock, mock_sleep: MagicMock
    ) -> None:
        from yt_dlp.utils import DownloadError

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = DownloadError("HTTP Error 429")
        rate_state = RateLimitState(consecutive_429=3)
        with pytest.raises(AbortIngestion):
            run_with_retry({}, "https://example.com", rate_state)
        assert rate_state.consecutive_429 == 6
        assert mock_sleep.call_count == 2

    @patch("lucas_v2.ingest.subs.time.sleep", return_value=None)
    @patch("lucas_v2.ingest.subs.random.uniform", return_value=0.0)
    @patch("lucas_v2.ingest.subs.yt_dlp.YoutubeDL")
    def test_429_then_success_resets_state(
        self, mock_ydl_cls: MagicMock, mock_uniform: MagicMock, mock_sleep: MagicMock
    ) -> None:
        from yt_dlp.utils import DownloadError

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = [
            DownloadError("HTTP Error 429"),
            DownloadError("HTTP Error 429"),
            None,
        ]
        rate_state = RateLimitState()
        run_with_retry({}, "https://example.com", rate_state)
        assert rate_state.consecutive_429 == 0
