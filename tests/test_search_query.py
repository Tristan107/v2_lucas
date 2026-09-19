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

    def test_or_two_terms(self) -> None:
        assert build_match_query("immigr* OR travail*") == "immigr* OR travail*"

    def test_or_and_mixed(self) -> None:
        assert build_match_query("immigr* OR travail* pénalité") == "immigr* OR travail* AND pénalité"

    def test_parentheses_with_or(self) -> None:
        assert build_match_query("(éducation OR travail) AND immigr*") == "(éducation OR travail) AND immigr*"

    def test_parentheses_implicit_and(self) -> None:
        assert build_match_query("immigr* (éducation OR travail)") == "immigr* AND (éducation OR travail)"

    def test_not_operator(self) -> None:
        assert build_match_query("immigr* NOT chômage") == "immigr* NOT chômage"

    def test_single_quote_escaped(self) -> None:
        assert build_match_query("l'immigration") == "l immigration"

    def test_case_insensitive_or(self) -> None:
        assert build_match_query("immigr* or travail*") == "immigr* OR travail*"

    def test_or_at_start_ignored(self) -> None:
        assert build_match_query("OR test") == "test"

    def test_or_at_end_ignored(self) -> None:
        assert build_match_query("test OR") == "test"

    def test_empty_after_operators(self) -> None:
        with pytest.raises(ValueError, match="vide"):
            build_match_query("OR AND NOT")

    def test_parentheses_implicit_and_between_parens(self) -> None:
        assert build_match_query("(a OR b) (c OR d)") == "(a OR b) AND (c OR d)"

    def test_quoted_phrase_preserved(self) -> None:
        assert build_match_query('"sécurité sociale"') == '"sécurité sociale"'

    def test_quoted_phrase_or_unchanged(self) -> None:
        assert build_match_query('"Mix énergétique" OR nucleaire*') == '"Mix énergétique" OR nucleaire*'

    def test_quoted_long_phrase_or_unchanged(self) -> None:
        assert build_match_query('"centre de rétention administrative" OR OQTF') == '"centre de rétention administrative" OR OQTF'

    def test_quoted_phrase_prefix(self) -> None:
        assert build_match_query('"sans-papier"*') == '"sans-papier"*'
        assert build_match_query('"transition écolo"*') == '"transition écolo"*'

    def test_two_quoted_phrases_implicit_and(self) -> None:
        assert build_match_query('"a b" "c d"') == '"a b" AND "c d"'

    def test_quoted_operator_stays_term(self) -> None:
        assert build_match_query('"AND" test') == '"AND" AND test'

    def test_quoted_apostrophe_replaced(self) -> None:
        assert build_match_query('"l\'école"') == '"l école"'


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
