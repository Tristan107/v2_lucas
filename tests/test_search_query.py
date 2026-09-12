from __future__ import annotations

import pytest

from lucas_v2.ui.query import build_match_query, format_date_fr, format_hhmmss, youtube_url


class TestBuildMatchQuery:
    def test_single_term(self) -> None:
        assert build_match_query("travail") == "travail"

    def test_two_terms_and(self) -> None:
        assert build_match_query("immigr* travail*") == "immigr* AND travail*"

    def test_multiple_spaces(self) -> None:
        assert build_match_query("  immigr*   travail*  ") == "immigr* AND travail*"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="vide"):
            build_match_query("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="vide"):
            build_match_query("   ")

    def test_three_terms(self) -> None:
        assert build_match_query("a b c") == "a AND b AND c"


class TestFormatHhmmss:
    def test_zero(self) -> None:
        assert format_hhmmss(0) == "00:00:00"

    def test_95_seconds(self) -> None:
        assert format_hhmmss(95) == "00:01:35"

    def test_9260_seconds(self) -> None:
        assert format_hhmmss(9260) == "02:34:20"

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="négatif"):
            format_hhmmss(-1)

    def test_exact_hour(self) -> None:
        assert format_hhmmss(3600) == "01:00:00"


class TestYoutubeUrl:
    def test_format(self) -> None:
        url = youtube_url("abc123", 120)
        assert url == "https://www.youtube.com/watch?v=abc123&t=120"

    def test_zero_start(self) -> None:
        url = youtube_url("xyz", 0)
        assert url == "https://www.youtube.com/watch?v=xyz&t=0"


class TestFormatDateFr:
    def test_valid(self) -> None:
        assert format_date_fr("20250615") == "15/06/2025"

    def test_none(self) -> None:
        assert format_date_fr(None) == ""

    def test_empty(self) -> None:
        assert format_date_fr("") == ""

    def test_invalid_returns_raw(self) -> None:
        assert format_date_fr("not-a-date") == "not-a-date"
