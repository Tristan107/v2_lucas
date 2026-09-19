from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemePreset:
    label: str
    raw_query: str


PRESETS: tuple[ThemePreset, ...] = (
    ThemePreset(
        label="Éducation",
        raw_query="éducat* OR école* OR enseign* OR apprenti* OR formation* OR scola* OR pédagog* OR profess* OR diplome*",
    ),
    ThemePreset(
        label="Santé",
        raw_query="Santé* OR Hôpita* OR médecine* OR médica* OR EHPAD* OR CHU* OR Samu OR Soignant* OR infirmier* OR \"sécurité sociale\"",
    ),
    ThemePreset(
        label="Immigration",
        raw_query="immigr* OR migr* OR clandestin* OR passeur* OR \"sans-papier\"* OR \"carte de séjour\" OR \"titre de séjour\" OR OQTF OR \"reconduite à la frontière\" OR \"centre de rétention administrative\" OR \"Droit du sol\" OR \"Droit du sang\" OR \"préférence nationale\" OR \"Schengen\" OR \"asile\" OR \"Frontière*\"",
    ),
    ThemePreset(
        label="Économie",
        raw_query="budget* OR dette* OR impot* OR deficit* OR Économi*",
    ),
    ThemePreset(
        label="Écologie",
        raw_query="\"Mix énergétique\" OR nucleaire* OR écolo* OR \"transition écolo\"* OR \"voiture électrique\" OR \"voitures électriques\"",
    ),
    ThemePreset(
        label="Défense",
        raw_query="Défense OR Russ* OR pologn* OR Ukrain* OR dron* OR bomb* OR missil* OR geopolitiqu*",
    ),
)