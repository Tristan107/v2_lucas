from __future__ import annotations

import pytest
import streamlit as st

from lucas_v2.ui.components import get_version, render_version_badge


def test_get_version_non_vide() -> None:
    v: str = get_version()
    assert isinstance(v, str)
    assert v


def test_render_version_badge_injecte_html(monkeypatch: pytest.MonkeyPatch) -> None:
    appels: list[str] = []

    def _faux_html(contenu: str, *args: object, **kwargs: object) -> None:
        appels.append(contenu)

    monkeypatch.setattr(st, "html", _faux_html)
    render_version_badge()
    assert len(appels) == 1
    assert f"v{get_version()}" in appels[0]
