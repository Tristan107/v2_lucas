from __future__ import annotations

import html
import math
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import streamlit as st

from lucas_v2.db import connect
from lucas_v2.ui.db_search import (
    ChunkHit,
    VideoHit,
    count_video_chunks,
    count_videos,
    get_video,
    search_video_chunks,
    search_videos,
)
from lucas_v2.ui.query import build_match_query, format_date_fr, format_hhmmss, youtube_url

VIDEOS_PER_PAGE = 10
CHUNKS_PER_PAGE = 10


@st.cache_resource
def _get_conn() -> Any:
    load_dotenv(Path(".env"))
    return connect()


def _inject_compact_style() -> None:
    st.html(
        """
        <style>
            header[data-testid="stHeader"] { display: none; }
            .block-container { padding-top: 0.5rem !important; }

            /* Reset input border/shadow */
            div[data-testid="stTextInput"] { border: none !important; box-shadow: none !important; outline: none !important; }
            div[data-testid="stTextInput"]:focus-within { border: none !important; box-shadow: none !important; outline: none !important; }
            div[data-testid="stTextInputRootElement"]:focus-within,
            div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within {
                border-color: #457B9D !important;
                box-shadow: 0 0 0 1px #457B9D !important;
            }

            /* Adjust vertical layout spacing */
            div[data-testid="stVerticalBlock"] { gap: 0rem !important; }
            div[data-testid="stCaptionContainer"] { margin-bottom: 0.5rem !important; }
            hr { margin: 0.35rem 0 !important; }

            /* Force Tertiary Button Left Alignment & Remove Bottom Margin */
            div[data-testid="stButton"] {
                margin-bottom: 0 !important;
            }
            div[data-testid="stButton"] button[kind="tertiary"] {
                display: flex !important;
                justify-content: flex-start !important;
                align-items: flex-start !important;
                text-align: left !important;
                font-size: 1.15rem !important;
                font-weight: 600 !important;
                line-height: 1.35 !important;
                padding: 0 !important;
                margin: 0 !important;
                white-space: normal !important;
                width: 100% !important;
                min-height: unset !important;
            }
            div[data-testid="stButton"] button[kind="tertiary"] * {
                text-align: left !important;
                justify-content: flex-start !important;
                font-weight: 600 !important;
            }

            /* Metadata line pinned directly under title */
            .lucas-meta {
                font-size: 0.8rem;
                margin-top: -0.15rem !important;
                margin-bottom: 0.75rem !important;
                color: #666;
                text-align: left;
                line-height: 1.2;
            }
        </style>
        """
    )


def _render_youtube_header() -> None:
    st.html(
        """
        <div style="font-size:clamp(1.2em,2.5vw,2em);font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
            <span style="color:#E63946">L</span><span style="color:#457B9D">U</span><span style="color:#2A9D8F">C</span><span style="color:#E9C46A">A</span><span style="color:#457B9D">S</span>
            — Recherche YouTube
        </div>
        """
    )


def _sync_search_state(match_query: str) -> None:
    if st.session_state.get("last_match_query") != match_query:
        st.session_state["last_match_query"] = match_query
        st.session_state["video_page"] = 0
        st.session_state["selected_video_id"] = None
        st.session_state["chunk_page"] = 0


def _video_meta_line(v: VideoHit) -> str:
    parts = [p for p in [format_date_fr(v.upload_date), v.owner, f"[{v.orientation}]" if v.orientation else None] if p]
    return " • ".join(parts)


def _render_prev_next(page_key: str, page: int, total_pages: int) -> None:
    col_prev, col_label, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("← Précédent", disabled=(page <= 0), key=f"prev_{page_key}"):
            st.session_state[page_key] = page - 1
            st.rerun()
    with col_label:
        st.html(f"<div style='text-align:center'>Page {page + 1} sur {total_pages}</div>")
    with col_next:
        if st.button("Suivant →", disabled=(page >= total_pages - 1), key=f"next_{page_key}"):
            st.session_state[page_key] = page + 1
            st.rerun()


def _render_video_row(v: VideoHit) -> None:
    title = v.title or v.youtube_str_id
    if st.button(
        title,
        key=f"open_{v.youtube_str_id}",
        type="tertiary",
        use_container_width=True,
    ):
        st.session_state["selected_video_id"] = v.youtube_str_id
        st.session_state["chunk_page"] = 0
        st.rerun()

    meta = _video_meta_line(v)
    meta_line = f"{meta} ({v.mentions} mentions)" if meta else f"({v.mentions} mentions)"
    st.html(f'<div class="lucas-meta">{html.escape(meta_line)}</div>')


def _render_video_list(conn: Any, match_query: str) -> None:
    total = count_videos(conn, match_query)
    if total == 0:
        st.info("Aucun résultat trouvé.")
        return

    total_pages = max(1, math.ceil(total / VIDEOS_PER_PAGE))
    page = int(st.session_state.get("video_page", 0))
    page = max(0, min(page, total_pages - 1))
    st.session_state["video_page"] = page

    st.caption(f"{total} vidéos trouvées — Page {page + 1} sur {total_pages}")
    videos = search_videos(conn, match_query, limit=VIDEOS_PER_PAGE, offset=page * VIDEOS_PER_PAGE)
    for v in videos:
        _render_video_row(v)
    _render_prev_next("video_page", page, total_pages)


def _render_chunk_row(ch: ChunkHit) -> None:
    col_ts, col_snippet = st.columns([1, 5])
    with col_ts:
        st.link_button(format_hhmmss(ch.start_s), youtube_url(ch.youtube_str_id, ch.start_s), use_container_width=True)
    with col_snippet:
        st.markdown(ch.snippet)


def _render_video_detail(conn: Any, match_query: str, youtube_str_id: str) -> None:
    if st.button("← Retour à la liste", key="back_to_list"):
        st.session_state["selected_video_id"] = None
        st.rerun()

    v = get_video(conn, youtube_str_id)
    if v is None:
        st.error("Vidéo introuvable.")
        return

    title = v.title or v.youtube_str_id
    st.html(f'<h2 style="font-size:1.3em;font-weight:bold;text-align:left;">{html.escape(title)}</h2>')

    meta = _video_meta_line(v)
    if meta:
        st.caption(f"{meta} • {v.mentions} segments")
    st.link_button("Voir sur YouTube", f"https://www.youtube.com/watch?v={v.youtube_str_id}")

    total = count_video_chunks(conn, match_query, youtube_str_id)
    if total == 0:
        st.info("Aucun extrait pour cette recherche dans cette vidéo.")
        return

    total_pages = max(1, math.ceil(total / CHUNKS_PER_PAGE))
    page = int(st.session_state.get("chunk_page", 0))
    page = max(0, min(page, total_pages - 1))
    st.session_state["chunk_page"] = page

    st.caption(f"{total} extraits — Page {page + 1} sur {total_pages}")
    chunks: list[ChunkHit] = search_video_chunks(
        conn, match_query, youtube_str_id, limit=CHUNKS_PER_PAGE, offset=page * CHUNKS_PER_PAGE
    )
    for ch in chunks:
        _render_chunk_row(ch)
    st.divider()
    _render_prev_next("chunk_page", page, total_pages)


def render_youtube_page() -> None:
    _inject_compact_style()
    _render_youtube_header()

    col_search, col_btn = st.columns([5, 1])
    with col_search:
        raw_query = st.text_input("Rechercher", placeholder="immigr* travail*", label_visibility="collapsed")
    with col_btn:
        search_clicked = st.button("Rechercher", use_container_width=True)

    if not search_clicked and not raw_query:
        return
    if not raw_query:
        st.warning("Entrez un ou plusieurs termes à rechercher.")
        return
    try:
        match_query = build_match_query(raw_query)
    except ValueError:
        st.warning("Requête vide.")
        return

    _sync_search_state(match_query)
    conn = _get_conn()
    selected = st.session_state.get("selected_video_id")
    if selected:
        _render_video_detail(conn, match_query, str(selected))
    else:
        _render_video_list(conn, match_query)