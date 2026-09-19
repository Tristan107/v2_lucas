from __future__ import annotations

import html
import math
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import streamlit as st

from lucas_v2.db.connection import connect
from lucas_v2.ui.components import render_version_badge
from lucas_v2.ui.db_search import (
    ChannelStats,
    ChunkHit,
    VideoHit,
    count_video_chunks,
    count_videos,
    get_video,
    search_chunks_by_channel,
    search_chunks_by_orientation,
    search_video_chunks,
    search_videos,
)
from lucas_v2.ui.presets import PRESETS
from lucas_v2.ui.query import build_match_query, format_date_fr, format_hhmmss, youtube_url

VIDEOS_PER_PAGE = 10
CHUNKS_PER_PAGE = 10

_PARTICLES = {"de", "du", "des", "le", "la", "les"}


def _parse_owner_name(raw: str) -> str:
    """Convertit 'Jordan Bardella' en 'Bardella (Jordan)' pour l'affichage."""
    parts = raw.strip().split()
    if len(parts) < 2:
        return raw
    idx = len(parts) - 1
    while idx > 0 and parts[idx - 1].lower() in _PARTICLES:
        idx -= 1
    last_name = " ".join(parts[idx:])
    first_name = " ".join(parts[:idx])
    return f"{last_name} ({first_name})"


@st.cache_resource
def _get_conn() -> Any:
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)
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

            /* Override selectbox focus border color */
            div[data-testid="stSelectbox"] [data-focus-within] {
                border-color: #457B9D !important;
                box-shadow: 0 0 0 1px #457B9D !important;
            }
            /* Override selectbox clear button border */
            div[data-testid="stSelectbox"] button[aria-label="Clear value"] {
                border-color: #457B9D !important;
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
                font-size: 1.45rem !important;
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
                font-size: inherit !important;
            }

            /* Thumbnail alignment in video list */
            div[data-testid="stImage"] {
                margin-top: 0.15rem !important;
            }

            /* Metadata line pinned directly under title */
            .lucas-meta {
                font-size: 1.0rem;
                margin-top: -0.15rem !important;
                margin-bottom: 0.75rem !important;
                color: #666;
                text-align: left;
                line-height: 1.2;
            }

            /* Tous les boutons en gras (même poids que les noms de candidats) */
            div[data-testid="stButton"] button,
            div[data-testid="stButton"] button *,
            div[data-testid="stLinkButton"] a,
            div[data-testid="stLinkButton"] a * {
                font-weight: 600 !important;
            }

            /* Espace entre la rangée de pills et la barre de recherche */
            div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"]:nth-child(2) {
                margin-bottom: 0.75rem !important;
            }

            /* Espace entre la barre de recherche et la ligne « Répartition par orientation / candidat » */
            div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"]:nth-child(4) {
                margin-top: 0.75rem !important;
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
        st.session_state["owner_filter"] = None


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


def _render_clickable_thumbnail(youtube_str_id: str) -> None:
    """Affiche un thumbnail YouTube cliquable qui ouvre la vue détail."""
    thumb_url = f"https://i.ytimg.com/vi_webp/{youtube_str_id}/default.webp"
    safe_id = html.escape(youtube_str_id)
    safe_url = html.escape(thumb_url)

    st.iframe(
        f"""
        <style>
            .thumb-link img {{
                width: 100%;
                border-radius: 8px;
                cursor: pointer;
                transition: opacity 0.2s;
            }}
            .thumb-link:hover img {{
                opacity: 0.85;
            }}
        </style>
        <a class="thumb-link" href="#" data-video-id="{safe_id}">
            <img src="{safe_url}" alt="Miniature" />
        </a>
        <script>
        document.querySelector('.thumb-link').addEventListener('click', function(e) {{
            e.preventDefault();
            var iframe = window.frameElement;
            if (!iframe) return;
            var block = iframe.closest('[data-testid="stHorizontalBlock"]');
            if (!block) return;
            var columns = block.querySelectorAll('[data-testid="stColumn"]');
            if (columns.length >= 2) {{
                var btn = columns[1].querySelector('button[kind="tertiary"]');
                if (btn) btn.click();
            }}
        }});
        </script>
        """,
        height=120,
    )


def _render_video_row(v: VideoHit) -> None:
    col_thumb, col_content = st.columns([1, 4])
    with col_thumb:
        _render_clickable_thumbnail(v.youtube_str_id)
    with col_content:
        title = v.title or v.youtube_str_id
        if st.button(
            title,
            key=f"open_{v.youtube_str_id}",
            type="tertiary",
            width="stretch",
        ):
            st.session_state["selected_video_id"] = v.youtube_str_id
            st.session_state["chunk_page"] = 0
            st.rerun()

        meta = _video_meta_line(v)
        meta_line = f"{meta} ({v.mentions} mentions)" if meta else f"({v.mentions} mentions)"
        st.html(f'<div class="lucas-meta">{html.escape(meta_line)}</div>')


ORIENTATION_COLORS: dict[str, str] = {
    "extrême gauche": "#B22222",
    "gauche": "#E63946",
    "centre gauche": "#F4A9A8",
    "centre droit": "#A8C8E8",
    "droite": "#1D3557",
    "extrême droite": "#2D2D2D",
}
_DEFAULT_COLOR = "#999999"


def _orientation_color(orientation: str | None) -> str:
    return ORIENTATION_COLORS.get(orientation or "", _DEFAULT_COLOR)


def _render_orientation_breakdown(conn: Any, match_query: str) -> None:
    stats = search_chunks_by_orientation(conn, match_query)
    stats = [s for s in stats if s.total > 0]
    if not stats:
        return

    rows_html = ""
    for s in stats:
        color = _orientation_color(s.orientation)
        pct = s.matched / s.total * 100
        bar_width = min(pct, 100)
        label = s.orientation or "non classé"
        rows_html += (
            f'<div style="margin-bottom:6px">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px">'
            f'<span style="font-size:0.85rem;color:{color};font-weight:600">{html.escape(label)}</span>'
            f'<span style="font-size:0.78rem;color:#888">{s.matched}/{s.total} <b style="color:{color}">{pct:.1f}%</b></span>'
            f'</div>'
            f'<div style="background:#e0e0e0;border-radius:4px;height:8px;overflow:hidden">'
            f'<div style="background:{color};height:100%;width:{bar_width:.1f}%;border-radius:4px"></div>'
            f'</div>'
            f'</div>'
        )

    st.html(
        f'<div style="margin-bottom:0.75rem">'
        f'<div style="font-size:0.85rem;font-weight:600;color:#444;margin-bottom:6px">Répartition par orientation</div>'
        f'{rows_html}'
        f'</div>'
    )


def _render_channel_breakdown(conn: Any, match_query: str) -> None:
    stats = search_chunks_by_channel(conn, match_query)
    stats = [s for s in stats if s.total > 0 and s.owner is not None]
    if not stats:
        return

    rows_html = ""
    for s in stats:
        color = _orientation_color(s.orientation)
        pct = s.matched / s.total * 100
        bar_width = min(pct, 100)
        label = s.owner or "inconnu"
        rows_html += (
            f'<div style="margin-bottom:6px">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px">'
            f'<span style="font-size:0.85rem;color:{color};font-weight:600">{html.escape(label)}</span>'
            f'<span style="font-size:0.78rem;color:#888">{s.matched}/{s.total} <b style="color:{color}">{pct:.1f}%</b></span>'
            f'</div>'
            f'<div style="background:#e0e0e0;border-radius:4px;height:8px;overflow:hidden">'
            f'<div style="background:{color};height:100%;width:{bar_width:.1f}%;border-radius:4px"></div>'
            f'</div>'
            f'</div>'
        )

    st.html(
        f'<div style="margin-bottom:0.75rem">'
        f'<div style="font-size:0.85rem;font-weight:600;color:#444;margin-bottom:6px">Répartition par candidat</div>'
        f'{rows_html}'
        f'</div>'
    )

    seen_owners: set[str] = set()
    unique_stats: list[ChannelStats] = []
    for s in stats:
        if s.owner and s.owner not in seen_owners:
            seen_owners.add(s.owner)
            unique_stats.append(s)

    display_to_raw: dict[str, str] = {}
    for s in unique_stats:
        dn = _parse_owner_name(s.owner or "")
        display_to_raw[dn] = s.owner  # type: ignore[assignment]

    sorted_display = sorted(display_to_raw.keys(), key=lambda n: n.split("(")[0].strip().casefold())
    options = ["Toutes"] + sorted_display

    owner_orientation: dict[str, str | None] = {}
    for s in stats:
        if s.owner and s.owner not in owner_orientation:
            owner_orientation[s.owner] = s.orientation
    st.session_state["owner_orientation"] = owner_orientation

    current = st.session_state.get("owner_filter")
    if current is None:
        index = 0
    else:
        reverse_map = {v: k for k, v in display_to_raw.items()}
        current_display = reverse_map.get(current, "")
        index = options.index(current_display) if current_display in options else 0
    selected = st.selectbox(
        "Filtrer par candidat",
        options,
        index=index,
        key="owner_selectbox",
        accept_new_options=False,
        filter_mode=None,
    )
    if selected == "Toutes":
        st.session_state["owner_filter"] = None
    else:
        st.session_state["owner_filter"] = display_to_raw.get(selected)


def _render_active_filters() -> None:
    owner_filter = st.session_state.get("owner_filter")
    if not owner_filter:
        return

    owner_orientation = st.session_state.get("owner_orientation", {})
    orientation = owner_orientation.get(owner_filter)
    color = _orientation_color(orientation)

    chips_html = (
        f'<span style="display:inline-flex;align-items:center;gap:4px;'
        f'background:{color}15;color:{color};border-radius:16px;padding:2px 10px;'
        f'font-size:0.82rem;font-weight:500">'
        f'Candidat: {html.escape(owner_filter)}'
        f'</span>'
    )

    st.html(
        f'<div style="margin-bottom:0.5rem;display:flex;flex-wrap:wrap;gap:6px;align-items:center">'
        f'{chips_html}'
        f'</div>'
    )


def _render_preset_row() -> None:
    """Affiche les pills de recherche thématique au-dessus de la barre de recherche."""
    current = st.session_state.get("last_match_query")
    cols = st.columns(len(PRESETS))
    for i, preset in enumerate(PRESETS):
        with cols[i]:
            match_query = build_match_query(preset.raw_query)
            active = match_query == current
            if st.button(
                preset.label,
                key=f"preset_{i}",
                type="primary" if active else "secondary",
                width="stretch",
                help=preset.raw_query,
            ):
                st.session_state["search_input"] = preset.raw_query
                st.session_state["last_match_query"] = match_query
                st.session_state["video_page"] = 0
                st.session_state["chunk_page"] = 0
                st.session_state["owner_filter"] = None
                st.rerun()


def _render_video_list(conn: Any, match_query: str) -> None:
    col_orient, col_channel = st.columns(2)
    with col_orient:
        _render_orientation_breakdown(conn, match_query)
    with col_channel:
        _render_channel_breakdown(conn, match_query)

    owner_filter = st.session_state.get("owner_filter")

    total = count_videos(conn, match_query, owner_filter=owner_filter)
    if total == 0:
        st.info("Aucun résultat trouvé.")
        return

    _render_active_filters()

    total_pages = max(1, math.ceil(total / VIDEOS_PER_PAGE))
    page = int(st.session_state.get("video_page", 0))
    page = max(0, min(page, total_pages - 1))
    st.session_state["video_page"] = page

    st.caption(f"{total} vidéos trouvées — Triées par nombre de mentions — Page {page + 1} sur {total_pages}")
    videos = search_videos(
        conn,
        match_query,
        limit=VIDEOS_PER_PAGE,
        offset=page * VIDEOS_PER_PAGE,
        owner_filter=owner_filter,
    )
    for v in videos:
        _render_video_row(v)
    _render_prev_next("video_page", page, total_pages)


def _render_chunk_row(ch: ChunkHit) -> None:
    col_ts, col_snippet = st.columns([1, 5])
    with col_ts:
        st.link_button(format_hhmmss(ch.start_s), youtube_url(ch.youtube_str_id, ch.start_s), width="stretch")
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

    total = count_video_chunks(conn, match_query, youtube_str_id)

    meta = _video_meta_line(v)
    if meta:
        st.caption(f"{meta} • {total} extraits sur {v.mentions}")

    if total == 0:
        st.info("Aucun extrait pour cette recherche dans cette vidéo.")
        return

    total_pages = max(1, math.ceil(total / CHUNKS_PER_PAGE))
    page = int(st.session_state.get("chunk_page", 0))
    page = max(0, min(page, total_pages - 1))
    st.session_state["chunk_page"] = page

    chunks: list[ChunkHit] = search_video_chunks(
        conn, match_query, youtube_str_id, limit=CHUNKS_PER_PAGE, offset=page * CHUNKS_PER_PAGE
    )
    for i, ch in enumerate(chunks):
        _render_chunk_row(ch)
        if i < len(chunks) - 1:
            st.html("<div style='margin-bottom:0.5rem'></div>")

    st.html("<div style='margin-bottom:0.5rem'></div>")
    _render_prev_next("chunk_page", page, total_pages)


def render_youtube_page() -> None:
    _inject_compact_style()
    _render_youtube_header()
    render_version_badge()

    selected = st.session_state.get("selected_video_id")

    if selected:
        conn = _get_conn()
        match_query = str(st.session_state.get("last_match_query", ""))
        with st.spinner("Recherche en cours…"):
            _render_video_detail(conn, match_query, str(selected))
        return

    _render_preset_row()
    col_search, col_btn = st.columns([5, 1])
    with col_search:
        raw_query = st.text_input(
            "Rechercher",
            key="search_input",
            placeholder="immigr* OR travail*",
            label_visibility="collapsed",
        )
    with col_btn:
        search_clicked = st.button("Rechercher", width="stretch")

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
    with st.spinner("Recherche en cours…"):
        _render_video_list(conn, match_query)