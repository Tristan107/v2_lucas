from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from lucas_v2.ui.app import render_youtube_page
from lucas_v2.ui.components import render_version_badge

IMG_DIR = Path(__file__).parent / "src" / "lucas_v2" / "ui" / "img"


def _img_to_data_uri(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{data}"


def _navigate_to(page: str) -> None:
    st.session_state["current_page"] = page
    if page == "home":
        st.query_params.clear()
    else:
        st.query_params["page"] = page
    st.rerun()


def render_homepage() -> None:
    yt_logo = _img_to_data_uri(IMG_DIR / "Youtube_logo.png")

    st.html(
        """
        <style>
            header[data-testid="stHeader"] { display: none; }
            .block-container { padding-top: 2rem !important; }
        </style>
        """
    )
    render_version_badge()

    st.html(
        f"""
        <div style="text-align:center;margin-bottom:0.5rem;">
            <span style="font-size:clamp(1.5em,3vw,2.5em);font-weight:bold;">
                <span style="color:#E63946">L</span><span style="color:#457B9D">U</span><span style="color:#2A9D8F">C</span><span style="color:#E9C46A">A</span><span style="color:#457B9D">S</span>
                — <span style="color:#E63946">L</span>'<span style="color:#457B9D">U</span>sine de <span style="color:#2A9D8F">C</span>ollecte d'informations<br>et d'<span style="color:#E9C46A">A</span>nalyse <span style="color:#457B9D">S</span>ynthétique
            </span>
        </div>
        <div style="text-align:center;margin-bottom:2.5rem;">
            <span style="font-size:clamp(1em,2vw,1.4em);color:#666;">
                🏛️ Veille politique automatisée — Échéance présidentielle 2027
            </span>
        </div>
        <div style="display:flex;justify-content:center;gap:3rem;">
            <a href="?page=youtube" style="text-decoration:none;">
                <div style="
                    width:220px;height:200px;
                    border:2px solid #ddd;border-radius:18px;
                    display:flex;flex-direction:column;align-items:center;justify-content:center;
                    background:#fff;transition:box-shadow .2s,transform .2s;cursor:pointer;
                " onmouseover="this.style.boxShadow='0 6px 24px rgba(0,0,0,.15)';this.style.transform='translateY(-4px)'"
                   onmouseout="this.style.boxShadow='none';this.style.transform='none'">
                    <img src="{yt_logo}" style="width:80px;height:auto;margin-bottom:16px;" />
                    <span style="font-size:1.25rem;font-weight:700;color:#264653;">YouTube</span>
                </div>
            </a>
            <a href="?page=sondages" style="text-decoration:none;">
                <div style="
                    width:220px;height:200px;
                    border:2px solid #ddd;border-radius:18px;
                    display:flex;flex-direction:column;align-items:center;justify-content:center;
                    background:#fff;transition:box-shadow .2s,transform .2s;cursor:pointer;
                " onmouseover="this.style.boxShadow='0 6px 24px rgba(0,0,0,.15)';this.style.transform='translateY(-4px)'"
                   onmouseout="this.style.boxShadow='none';this.style.transform='none'">
                    <span style="font-size:64px;margin-bottom:12px;">📋</span>
                    <span style="font-size:1.25rem;font-weight:700;color:#264653;">Sondages</span>
                </div>
            </a>
        </div>
        """
    )


def render_sondages_page() -> None:
    if st.button("← Accueil"):
        _navigate_to("home")
    render_version_badge()
    st.html(
        """
        <div style="text-align:center;margin-top:2rem;">
            <span style="font-size:clamp(1.2em,2.5vw,2em);font-weight:bold;">
                <span style="color:#E63946">L</span><span style="color:#457B9D">U</span><span style="color:#2A9D8F">C</span><span style="color:#E9C46A">A</span><span style="color:#457B9D">S</span>
                — Sondages
            </span>
        </div>
        <div style="text-align:center;margin-top:2rem;">
            <span style="font-size:1.2em;color:#666;">📋 Bientôt disponible</span>
        </div>
        """
    )


# --- Main routing ---
params = st.query_params
if "page" in params:
    target = str(params["page"])
    if target in ("youtube", "sondages"):
        st.session_state["current_page"] = target

if "current_page" not in st.session_state:
    st.session_state["current_page"] = "home"

page = st.session_state["current_page"]
if page == "youtube":
    render_youtube_page()
elif page == "sondages":
    render_sondages_page()
else:
    render_homepage()
