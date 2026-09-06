from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from lucas_v2 import (
    INTER_VIDEO_DELAY_S,
    extract_video_id,
    print_dry_run_summary,
    resolve_channel,
    cli,
    ingest,
    paced_sleep,
)
from lucas_v2.config import ChannelSpec


# ---------------------------------------------------------------------------
# extract_video_id
# ---------------------------------------------------------------------------

class TestExtractVideoId:
    def test_standard_url(self) -> None:
        assert extract_video_id("https://www.youtube.com/watch?v=abc12345678") == "abc12345678"

    def test_short_url(self) -> None:
        assert extract_video_id("https://youtu.be/abc12345678") == "abc12345678"

    def test_url_with_extra_params(self) -> None:
        assert extract_video_id("https://www.youtube.com/watch?v=abc12345678&t=10") == "abc12345678"

    def test_invalid_url(self) -> None:
        assert extract_video_id("https://example.com") is None

    def test_empty_string(self) -> None:
        assert extract_video_id("") is None


# ---------------------------------------------------------------------------
# resolve_channel — local imports inside function body
# ---------------------------------------------------------------------------

class TestResolveChannel:
    @patch("lucas_v2.db.upsert_channel")
    @patch("lucas_v2.youtube_api.resolve_channel_id")
    def test_success(
        self, mock_resolve: MagicMock, mock_upsert: MagicMock
    ) -> None:
        mock_resolve.return_value = ("UC123", "My Channel")
        mock_upsert.return_value = 42
        spec = ChannelSpec(url="@test", max_videos=1, since_days=None, lang="fr")
        conn = MagicMock()
        result = resolve_channel(spec, conn)
        assert result is not None
        assert result[0] == 42
        assert result[1] == "UC123"
        assert result[2] == "My Channel"

    @patch("lucas_v2.youtube_api.resolve_channel_id")
    def test_failure_returns_none(self, mock_resolve: MagicMock) -> None:
        mock_resolve.side_effect = ValueError("not found")
        spec = ChannelSpec(url="@bad", max_videos=1, since_days=None, lang="fr")
        conn = MagicMock()
        result = resolve_channel(spec, conn)
        assert result is None


# ---------------------------------------------------------------------------
# fetch_videos — local import of list_videos
# ---------------------------------------------------------------------------

class TestFetchVideos:
    @patch("lucas_v2.youtube_api.list_videos")
    def test_success(self, mock_list: MagicMock) -> None:
        from lucas_v2 import fetch_videos  # pyright: ignore[reportPrivateUsage]

        mock_list.return_value = [{"youtube_str_id": "v1"}]
        spec = ChannelSpec(url="@ch", max_videos=5, since_days=30, lang="fr")
        result = fetch_videos("UC123", spec)
        assert len(result) == 1
        mock_list.assert_called_once_with("UC123", 5, 30)

    @patch("lucas_v2.youtube_api.list_videos")
    def test_error_returns_empty(self, mock_list: MagicMock) -> None:
        from lucas_v2 import fetch_videos  # pyright: ignore[reportPrivateUsage]

        mock_list.side_effect = RuntimeError("api error")
        spec = ChannelSpec(url="@ch", max_videos=5, since_days=None, lang="fr")
        result = fetch_videos("UC123", spec)
        assert result == []


# ---------------------------------------------------------------------------
# paced_sleep
# ---------------------------------------------------------------------------

class TestPacedSleep:
    @patch("lucas_v2.time.sleep")
    @patch("lucas_v2.random.uniform", return_value=2.5)
    def test_sleeps_base_plus_jitter(self, mock_uniform: MagicMock, mock_sleep: MagicMock) -> None:
        paced_sleep(10, 5.0)
        mock_uniform.assert_called_once_with(0, 5.0)
        mock_sleep.assert_called_once_with(12.5)


# ---------------------------------------------------------------------------
# process_videos — local imports of video_exists, RateLimitedError
# ---------------------------------------------------------------------------

class TestProcessVideos:
    @patch("lucas_v2.db.video_exists")
    def test_dry_run_new(self, mock_exists: MagicMock) -> None:
        from lucas_v2 import process_videos  # pyright: ignore[reportPrivateUsage]

        mock_exists.return_value = False
        conn = MagicMock()
        videos = [{"youtube_str_id": "v1", "title": "T"}]
        new, existing = process_videos(videos, 1, conn, force=False, dry_run=True, tok=None)
        assert new == 1
        assert existing == 0

    @patch("lucas_v2.db.video_exists")
    def test_dry_run_existing(self, mock_exists: MagicMock) -> None:
        from lucas_v2 import process_videos  # pyright: ignore[reportPrivateUsage]

        mock_exists.return_value = True
        conn = MagicMock()
        videos = [{"youtube_str_id": "v1", "title": "T"}]
        new, existing = process_videos(videos, 1, conn, force=False, dry_run=True, tok=None)
        assert new == 0
        assert existing == 1

    @patch("lucas_v2.db.video_exists")
    def test_skips_existing_when_not_force(self, mock_exists: MagicMock) -> None:
        from lucas_v2 import process_videos  # pyright: ignore[reportPrivateUsage]

        mock_exists.return_value = True
        conn = MagicMock()
        videos = [{"youtube_str_id": "v1", "title": "T"}]
        process_videos(videos, 1, conn, force=False, dry_run=False, tok=None)

    @patch("lucas_v2.download_and_store")
    @patch("lucas_v2.db.video_exists")
    def test_force_downloads_existing(
        self, mock_exists: MagicMock, mock_dl: MagicMock
    ) -> None:
        from lucas_v2 import process_videos  # pyright: ignore[reportPrivateUsage]

        mock_exists.return_value = True
        conn = MagicMock()
        videos = [{"youtube_str_id": "v1", "title": "T"}]
        process_videos(videos, 1, conn, force=True, dry_run=False, tok=None)
        mock_dl.assert_called_once()

    @patch("lucas_v2.paced_sleep")
    @patch("lucas_v2.download_and_store")
    @patch("lucas_v2.db.video_exists", return_value=False)
    def test_paced_sleep_between_videos(
        self, mock_exists: MagicMock, mock_dl: MagicMock, mock_sleep: MagicMock
    ) -> None:
        from lucas_v2 import process_videos  # pyright: ignore[reportPrivateUsage]

        conn = MagicMock()
        videos = [
            {"youtube_str_id": "v1", "title": "T1"},
            {"youtube_str_id": "v2", "title": "T2"},
        ]
        process_videos(videos, 1, conn, force=False, dry_run=False, tok=None)
        mock_sleep.assert_called_once_with(INTER_VIDEO_DELAY_S)

    @patch("lucas_v2.paced_sleep")
    @patch("lucas_v2.download_and_store")
    @patch("lucas_v2.db.video_exists", return_value=False)
    def test_break_on_rate_limited(
        self, mock_exists: MagicMock, mock_dl: MagicMock, mock_sleep: MagicMock
    ) -> None:
        from lucas_v2 import process_videos  # pyright: ignore[reportPrivateUsage]
        from lucas_v2.subs import RateLimitedError

        mock_dl.side_effect = RateLimitedError("429")
        conn = MagicMock()
        videos = [
            {"youtube_str_id": "v1", "title": "T1"},
            {"youtube_str_id": "v2", "title": "T2"},
        ]
        process_videos(videos, 1, conn, force=False, dry_run=False, tok=None)
        assert mock_dl.call_count == 1


# ---------------------------------------------------------------------------
# print_dry_run_summary
# ---------------------------------------------------------------------------

class TestPrintDryRunSummary:
    def test_output(self) -> None:
        results: list[tuple[str, str | None, int, int]] = [
            ("https://yt.com/ch1", "Channel 1", 3, 2),
            ("https://yt.com/ch2", None, 0, 5),
        ]
        print_dry_run_summary(results)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

class TestCLI:
    def test_cli_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Lucas v2" in result.output

    def test_ingest_missing_config(self) -> None:
        runner = CliRunner()
        result = runner.invoke(ingest, ["-c", "/nonexistent/config.yaml"])
        assert result.exit_code == 1

    @patch("lucas_v2.process_videos", return_value=(1, 0))
    @patch("lucas_v2.fetch_videos", return_value=[{"youtube_str_id": "v1", "title": "V1"}])
    @patch("lucas_v2.resolve_channel", return_value=(1, "UC123", "Test"))
    @patch("lucas_v2.chunking.get_tokenizer", return_value=None)
    @patch("lucas_v2.schema.init_schema")
    @patch("lucas_v2.db.connect")
    @patch("lucas_v2.logging_config.setup_logging")
    def test_ingest_dry_run(
        self,
        mock_logging: MagicMock,
        mock_connect: MagicMock,
        mock_schema: MagicMock,
        mock_tok: MagicMock,
        mock_resolve: MagicMock,
        mock_fetch: MagicMock,
        mock_process: MagicMock,
        tmp_path: Any,
    ) -> None:
        yaml_content = """\
defaults:
  max_videos: 1
channels:
  - url: https://youtube.com/@TestChannel
"""
        config_file = tmp_path / "channels.yaml"
        config_file.write_text(yaml_content, encoding="utf-8")
        mock_logging.return_value = MagicMock()
        mock_connect.return_value = MagicMock()

        runner = CliRunner()
        result = runner.invoke(ingest, ["-c", str(config_file), "--dry-run"])
        assert result.exit_code == 0
