from __future__ import annotations

from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

import lucas_v2.ui.app as app_module
from lucas_v2.ui.db_search import ChunkHit, VideoHit

VIDEO_ID = "abc123"

_SCRIPT = """
from __future__ import annotations

import streamlit as st
from lucas_v2.ui.app import render_youtube_page

st.session_state["current_page"] = "youtube"
render_youtube_page()
"""


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
        snippet="Extrait sur immigration",
        youtube_str_id=VIDEO_ID,
    )


def _patch_db(monkeypatch: pytest.MonkeyPatch) -> None:
    def _search_videos(*args: Any, **kwargs: Any) -> list[VideoHit]:
        return [_video_hit()]

    def _count_videos(*args: Any, **kwargs: Any) -> int:
        return 1

    def _get_video(*args: Any, **kwargs: Any) -> VideoHit:
        return _video_hit()

    def _search_video_chunks(*args: Any, **kwargs: Any) -> list[ChunkHit]:
        return [_chunk_hit()]

    def _count_video_chunks(*args: Any, **kwargs: Any) -> int:
        return 1

    monkeypatch.setattr(app_module, "search_videos", _search_videos)
    monkeypatch.setattr(app_module, "count_videos", _count_videos)
    monkeypatch.setattr(app_module, "get_video", _get_video)
    monkeypatch.setattr(app_module, "search_video_chunks", _search_video_chunks)
    monkeypatch.setattr(app_module, "count_video_chunks", _count_video_chunks)
    def _no_stats(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(app_module, "search_chunks_by_orientation", _no_stats)
    monkeypatch.setattr(app_module, "search_chunks_by_channel", _no_stats)


def test_retour_liste_conserve_filtre(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le retour à la liste réaffiche la requête saisie (régression 439625e)."""
    _patch_db(monkeypatch)
    at = AppTest.from_string(_SCRIPT, default_timeout=10)
    at.run()

    at.text_input(key="search_input").set_value("immigration")
    at.run()
    assert at.session_state["last_raw_query"] == "immigration"

    at.button(key=f"open_{VIDEO_ID}").click()
    at.run()
    assert at.session_state["selected_video_id"] == VIDEO_ID

    at.button(key="back_to_list").click()
    at.run()
    assert at.text_input(key="search_input").value == "immigration"
    assert any(b.key == f"open_{VIDEO_ID}" for b in at.get("button"))


def test_retour_liste_conserve_derniere_requete(monkeypatch: pytest.MonkeyPatch) -> None:
    """Après une 2ᵉ recherche, le retour restaure la nouvelle requête, pas l'ancienne."""
    _patch_db(monkeypatch)
    at = AppTest.from_string(_SCRIPT, default_timeout=10)
    at.run()

    at.text_input(key="search_input").set_value("immigration")
    at.run()
    at.button(key=f"open_{VIDEO_ID}").click()
    at.run()
    at.button(key="back_to_list").click()
    at.run()
    assert at.text_input(key="search_input").value == "immigration"

    at.text_input(key="search_input").set_value("economie")
    at.run()
    assert at.session_state["last_raw_query"] == "economie"
    at.button(key=f"open_{VIDEO_ID}").click()
    at.run()
    at.button(key="back_to_list").click()
    at.run()
    assert at.text_input(key="search_input").value == "economie"