from __future__ import annotations

from typing import Any

import libsql_experimental as libsql  # pyright: ignore[reportMissingModuleSource]

from lucas_v2.db import Chunk
from lucas_v2.db.operations import replace_chunks, upsert_channel, upsert_video
from lucas_v2.db.schema import init_schema
from lucas_v2.ui.db_search import count_videos
from lucas_v2.ui.presets import PRESETS
from lucas_v2.ui.query import build_match_query


def test_presets_valid_match_queries() -> None:
    for preset in PRESETS:
        result = build_match_query(preset.raw_query)
        assert isinstance(result, str)
        assert result


def test_presets_snapshots() -> None:
    expected = {
        "Éducation": "éducat* OR école* OR enseign* OR apprenti* OR formation* OR scola* OR pédagog* OR profess* OR diplome*",
        "Santé": 'Santé* OR Hôpita* OR médecine* OR médica* OR EHPAD* OR CHU* OR Samu OR Soignant* OR infirmier* OR "sécurité sociale"',
        "Immigration": 'immigr* OR migr* OR clandestin* OR passeur* OR "sans-papier"* OR "carte de séjour" OR "titre de séjour" OR OQTF OR "reconduite à la frontière" OR "centre de rétention administrative" OR "Droit du sol" OR "Droit du sang" OR "préférence nationale" OR "Schengen" OR "asile" OR "Frontière*"',
        "Économie": "budget* OR dette* OR impot* OR deficit* OR Économi*",
        "Écologie": '"Mix énergétique" OR nucleaire* OR écolo* OR "transition écolo"* OR "voiture électrique" OR "voitures électriques"',
        "Défense": "Défense OR Russ* OR pologn* OR Ukrain* OR dron* OR bomb* OR missil* OR geopolitiqu*",
    }
    actual = {p.label: p.raw_query for p in PRESETS}
    assert actual == expected
    assert "transition écolo" in expected["Écologie"]
    assert expected["Immigration"].count("centre de rétention administrative") == 1


def test_presets_ecologie_matches_transition_ecologique() -> None:
    conn = _conn()
    _seed(conn, [Chunk(seq_no=0, start_s=0, end_s=5, text="la transition écologique et le nucléaire", tokens=6)])
    preset = next(p for p in PRESETS if p.label == "Écologie")
    assert count_videos(conn, build_match_query(preset.raw_query)) >= 1


def test_presets_all_cover_corpus() -> None:
    conn = _conn()
    corpus = [
        "l éducation dans les écoles",
        "la sécurité sociale et le samu",
        "les immigrés sans papier à la frontière",
        "le budget et l économie",
        "la transition écologique et le nucléaire",
        "la défense, la Russie et l Ukraine",
    ]
    _seed(conn, [Chunk(seq_no=i, start_s=0, end_s=5, text=t, tokens=len(t.split())) for i, t in enumerate(corpus)])
    for preset in PRESETS:
        assert count_videos(conn, build_match_query(preset.raw_query)) >= 1


def _conn() -> Any:
    conn = libsql.connect(":memory:")  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
    init_schema(conn)
    return conn  # pyright: ignore[reportUnknownVariableType]


def _seed(conn: Any, chunks: list[Chunk]) -> None:
    ch_id = upsert_channel(conn, "https://yt.com/ch1", "UC1", "Chaîne", "gauche", "Alice")
    vid = upsert_video(conn, ch_id, "vid1", "Vidéo", "20250101", 120, "fr", "manual", "ok", None)
    replace_chunks(conn, vid, chunks)
    conn.commit()