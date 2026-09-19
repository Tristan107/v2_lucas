from __future__ import annotations

from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

import lucas_v2.ui.app as app_module
from lucas_v2.ui.db_search import ChannelStats, ChunkHit, VideoHit

VIDEO_ID = "abc123"

_SCRIPT = """
from __future__ import annotations

import streamlit as st
from lucas_v2.ui.app import render_youtube_page

st.session_state["current_page"] = "youtube"
render_youtube_page()
"""

_STATS_EDUCATION = [
    ChannelStats(owner="Jordan Bardella", orientation="droite", matched=5, total=100),
    ChannelStats(owner="Jean-Luc Mélenchon", orientation="extrême gauche", matched=3, total=80),
]

_STATS_SANTE_SAME = [
    ChannelStats(owner="Jordan Bardella", orientation="droite", matched=2, total=50),
    ChannelStats(owner="Marine Le Pen", orientation="extrême droite", matched=4, total=60),
]

_STATS_SANTE_ABSENT = [
    ChannelStats(owner="Jean-Luc Mélenchon", orientation="extrême gauche", matched=4, total=70),
]


def _video_hit() -> VideoHit:
    return VideoHit(
        youtube_str_id=VIDEO_ID,
        title="Le titre de test",
        upload_date="2024-01-01",
        owner="Jordan Bardella",
        orientation="droite",
        mentions=3,
    )


def _chunk_hit() -> ChunkHit:
    return ChunkHit(
        seq_no=0,
        start_s=95,
        end_s=120,
        snippet="Extrait sur éducation",
        youtube_str_id=VIDEO_ID,
    )


def _patch_db(
    monkeypatch: pytest.MonkeyPatch,
    stats_sante: list[ChannelStats] | None = None,
) -> list[str | None]:
    owner_filter_calls: list[str | None] = []
    stats_san = stats_sante if stats_sante is not None else _STATS_SANTE_SAME

    def _search_chunks_by_channel(conn: Any, match_query: str) -> list[ChannelStats]:
        if "éducat" in match_query:
            return _STATS_EDUCATION
        if "inexistant" in match_query:
            return []
        return stats_san

    def _search_videos(*args: Any, **kwargs: Any) -> list[VideoHit]:
        return [_video_hit()]

    def _count_videos(*args: Any, **kwargs: Any) -> int:
        owner_filter_calls.append(kwargs.get("owner_filter", args[2] if len(args) > 2 else None))
        return 1

    def _get_video(*args: Any, **kwargs: Any) -> VideoHit:
        return _video_hit()

    def _search_video_chunks(*args: Any, **kwargs: Any) -> list[ChunkHit]:
        return [_chunk_hit()]

    def _count_video_chunks(*args: Any, **kwargs: Any) -> int:
        return 1

    def _no_orientation(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(app_module, "search_videos", _search_videos)
    monkeypatch.setattr(app_module, "count_videos", _count_videos)
    monkeypatch.setattr(app_module, "get_video", _get_video)
    monkeypatch.setattr(app_module, "search_video_chunks", _search_video_chunks)
    monkeypatch.setattr(app_module, "count_video_chunks", _count_video_chunks)
    monkeypatch.setattr(app_module, "search_chunks_by_orientation", _no_orientation)
    monkeypatch.setattr(app_module, "search_chunks_by_channel", _search_chunks_by_channel)
    return owner_filter_calls


def test_changement_preset_conserve_filtre_candidat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un clic réel sur le dropdown applique le filtre ; un nouveau thème le conserve
    si le candidat est encore présent dans le breakdown."""
    owner_filter_calls = _patch_db(monkeypatch, stats_sante=_STATS_SANTE_SAME)
    at = AppTest.from_string(_SCRIPT, default_timeout=10)
    at.run()

    at.button(key="preset_0").click()
    at.run()
    assert at.session_state["last_match_query"] is not None

    # Interaction réelle : l'utilisateur clique sur un candidat dans le dropdown.
    at.selectbox(key="owner_selectbox").select("Bardella (Jordan)")
    at.run()
    assert at.session_state["owner_filter"] == "Jordan Bardella"
    assert at.selectbox(key="owner_selectbox").value == "Bardella (Jordan)"
    assert owner_filter_calls[-1] == "Jordan Bardella"

    # Changement de thème, candidat toujours présent dans le nouveau breakdown.
    at.button(key="preset_1").click()
    at.run()
    assert at.session_state["owner_filter"] == "Jordan Bardella"
    assert at.selectbox(key="owner_selectbox").value == "Bardella (Jordan)"
    assert owner_filter_calls[-1] == "Jordan Bardella"


def test_changement_preset_candidat_absent_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Candidat absent du nouveau thème → reset propre du dropdown et du filtre."""
    owner_filter_calls = _patch_db(monkeypatch, stats_sante=_STATS_SANTE_ABSENT)
    at = AppTest.from_string(_SCRIPT, default_timeout=10)
    at.run()

    at.button(key="preset_0").click()
    at.run()
    at.selectbox(key="owner_selectbox").select("Bardella (Jordan)")
    at.run()
    assert at.session_state["owner_filter"] == "Jordan Bardella"

    at.button(key="preset_1").click()
    at.run()
    assert at.session_state["owner_filter"] is None
    assert at.selectbox(key="owner_selectbox").value == "Toutes"
    assert owner_filter_calls[-1] is None


def test_recherche_manuelle_conserve_filtre(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une recherche manuelle conserve le filtre tant que le candidat reste présent."""
    owner_filter_calls = _patch_db(monkeypatch, stats_sante=_STATS_SANTE_SAME)
    at = AppTest.from_string(_SCRIPT, default_timeout=10)
    at.run()

    at.text_input(key="search_input").set_value("éducat*")
    at.run()
    at.selectbox(key="owner_selectbox").select("Bardella (Jordan)")
    at.run()
    assert at.session_state["owner_filter"] == "Jordan Bardella"
    assert owner_filter_calls[-1] == "Jordan Bardella"

    # Nouvelle recherche manuelle, candidat toujours présent dans le nouveau breakdown.
    at.text_input(key="search_input").set_value("école*")
    at.run()
    assert at.session_state["owner_filter"] == "Jordan Bardella"
    assert at.selectbox(key="owner_selectbox").value == "Bardella (Jordan)"
    assert owner_filter_calls[-1] == "Jordan Bardella"


def test_breakdown_vide_pas_de_reaplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Breakdown vide → reset ; une valeur périmée ne réapplique pas le filtre plus tard."""
    owner_filter_calls = _patch_db(monkeypatch, stats_sante=_STATS_SANTE_SAME)
    at = AppTest.from_string(_SCRIPT, default_timeout=10)
    at.run()

    at.text_input(key="search_input").set_value("éducat*")
    at.run()
    at.selectbox(key="owner_selectbox").select("Bardella (Jordan)")
    at.run()
    assert at.session_state["owner_filter"] == "Jordan Bardella"

    # Requête sans aucun résultat par candidat : le breakdown disparaît, filtre reset.
    at.text_input(key="search_input").set_value("inexistant*")
    at.run()
    assert at.session_state["owner_filter"] is None
    assert not at.get("selectbox")

    # Une recherche ultérieure ne réapplique pas l'ancienne sélection périmée.
    at.text_input(key="search_input").set_value("Santé*")
    at.run()
    assert at.session_state["owner_filter"] is None
    assert at.selectbox(key="owner_selectbox").value == "Toutes"
    assert owner_filter_calls[-1] is None
