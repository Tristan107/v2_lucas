from __future__ import annotations

from lucas_v2.ui.app import _parse_owner_name  # pyright: ignore[reportPrivateUsage]


def test_parse_owner_name_simple() -> None:
    assert _parse_owner_name("Jordan Bardella") == "Bardella (Jordan)"


def test_parse_owner_name_particle_de() -> None:
    assert _parse_owner_name("Dominique de Villepin") == "de Villepin (Dominique)"


def test_parse_owner_name_particle_le_pen() -> None:
    assert _parse_owner_name("Marine Le Pen") == "Le Pen (Marine)"


def test_parse_owner_name_hyphenated() -> None:
    assert _parse_owner_name("Nicolas Dupont-Aignan") == "Dupont-Aignan (Nicolas)"


def test_parse_owner_name_single_word() -> None:
    assert _parse_owner_name("Madonna") == "Madonna"


def test_parse_owner_name_with_suffix() -> None:
    assert _parse_owner_name("Olivier Faure PS") == "PS (Olivier Faure)"


def test_parse_owner_name_two_parts() -> None:
    assert _parse_owner_name("Fabien Roussel") == "Roussel (Fabien)"


def test_parse_owner_name_three_parts() -> None:
    assert _parse_owner_name("Jean-Luc Mélenchon") == "Mélenchon (Jean-Luc)"
