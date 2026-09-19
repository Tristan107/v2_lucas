from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

import streamlit as st


def get_version() -> str:
    """Retourne la version du paquet déclarée dans pyproject.toml."""
    try:
        return _pkg_version("lucas-v2")
    except PackageNotFoundError:
        return "dev"


def render_version_badge() -> None:
    """Affiche le numéro de version en haut à droite de la page."""
    v: str = get_version()
    st.html(
        f"""
        <div style="
            position:fixed;
            top:0.75rem;
            right:1.5rem;
            font-family:monospace;
            font-size:0.8rem;
            color:#666;
            z-index:9999;
            pointer-events:none;
        ">v{v}</div>
        """
    )
