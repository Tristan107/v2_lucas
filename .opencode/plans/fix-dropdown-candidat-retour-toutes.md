# Fix : clic sur le dropdown candidat → retour à « Toutes » (régression du plan fix-preset-perte-filtre-candidat)

## Contexte / Symptôme

Après l'implémentation de `.opencode/plans/fix-preset-perte-filtre-candidat.md`, un bug inverse est apparu :

1. Choisir un thème (pill preset) → la recherche s'exécute.
2. **Cliquer sur un candidat dans le dropdown « Filtrer par candidat »** → le dropdown revient immédiatement à « Toutes » et la liste n'est jamais filtrée.

Les « tests de non régression » ajoutés par ce plan passent (3/3) mais **ne déclenchent pas le bug**.

## Root cause

### Mécanisme exact

Le bloc de synchronisation ajouté dans `_render_channel_breakdown()` (`src/lucas_v2/ui/app.py`, lignes 346-355) écrase la sélection de l'utilisateur :

```python
current = st.session_state.get("owner_filter")      # ← source de vérité, ENCORE ANCIENNE
...
target = options[index]
if st.session_state.get("owner_selectbox") != target:
    st.session_state["owner_selectbox"] = target     # ← écrase le widget
```

Séquence au clic sur un candidat (widget géré par Streamlit) :

1. L'utilisateur clique « Bardella (Jordan) » → Streamlit enregistre la nouvelle valeur dans `session_state["owner_selectbox"]` puis **relance le script**.
2. Pendant ce run, `owner_filter` contient **toujours l'ancienne valeur** (`None`) : la source de vérité n'a pas encore été mise à jour, car c'est justement ce run qui va la recalculer depuis le widget.
3. Le code de sync dérive `target = "Toutes"` depuis cette valeur périmée, constate `owner_selectbox != "Toutes"` et **écrase la sélection** de l'utilisateur.
4. `st.selectbox(...)` lit donc « Toutes » → `selected == "Toutes"` → `owner_filter = None`.

### Preuve (diagnostic AppTest, streamlit 1.63.0)

Interaction réelle simulée (monkeypatch des fonctions DB du module `app`, `selectbox.select("Bardella (Jordan)")` après `preset_0`) :

```
after preset_0     : owner_filter = None | widget = Toutes
after select click : owner_filter = None | widget = Toutes | count_videos saw owner_filter = None
after preset_1     : owner_filter = None | widget = Toutes | count_videos saw owner_filter = None
```

→ Le clic ne filtre jamais. Bug reproduit.

### Pourquoi les tests existants ne « testent rien »

`tests/test_preset_filter_persistence.py` fixe le filtre **à la main** au lieu de simuler l'interaction :

```python
at.session_state["owner_filter"] = "Jordan Bardella"   # ← ne passe PAS par le widget
at.run()
```

Cela exerce uniquement le chemin « synchroniser le widget depuis la source de vérité » (qui reste cohérent), jamais le chemin « l'utilisateur clique sur le dropdown » (le seul cassé). D'où : 3 tests PASSED, bug présent en production.

Vérifié : sur le code actuel, le scénario « click réel » échoue (`owner_filter` reste `None`), alors que tous les tests passent (3/3).

## Décision de conception

Conserver la conception validée par `fix-preset-perte-filtre-candidat.md` (conservation du filtre au changement de thème + reset propre si candidat absent), mais **inverser la priorité au run** :

- **Une valeur de widget déjà présente et valide (∈ options) fait foi** : elle reflète une interaction utilisateur récente ou un état déjà cohérent. On laisse `st.selectbox` la lire et `owner_filter` est ré-aligné via le mapping post-selectbox (bloc existant inchangé).
- **On ne resynchronise le widget que si sa valeur est absente** (premier rendu) **ou périmée** (candidat disparu du breakdown après changement de thème/recherche) : on recalcule alors `target` depuis `owner_filter`, puis reset propre vers « Toutes » si le candidat a disparu.
- **Branche « breakdown vide »** : en plus du reset de `owner_filter`, **supprimer la clé widget** (`pop`) pour qu'une valeur périmée ne « ressuscite » pas silencieusement lors d'un breakdown ultérieur contenant à nouveau le candidat.

`owner_filter` reste la source de vérité applicative pour le SQL ; le widget est un miroir, mais un miroir qui **ne doit jamais être écrasé pendant le run où l'utilisateur vient de le modifier** (son état en session est la seule trace de cette modification).

## Fichiers modifiés

- `src/lucas_v2/ui/app.py`
- `tests/test_preset_filter_persistence.py` (réécriture complète)

Aucun changement requis dans `_sync_search_state()` ni dans le handler de `_render_preset_row()` : la suppression de `owner_filter = None` du plan précédent est correcte et **doit être conservée**.

## Changements

### 1. `src/lucas_v2/ui/app.py` — branche « breakdown vide » (ligne ~296)

Remplacer :

```python
    if not stats:
        st.session_state["owner_filter"] = None
        return
```

par :

```python
    if not stats:
        st.session_state["owner_filter"] = None
        st.session_state.pop("owner_selectbox", None)
        return
```

`st.session_state` côté script est un `SessionStateProxy` (`MutableMapping`) : `pop(key, default)` est disponible (hérité de `collections.abc.MutableMapping`), contrairement au proxy externe `at.session_state` des tests.

### 2. `src/lucas_v2/ui/app.py` — bloc de synchronisation (lignes 346-355)

Remplacer :

```python
    current = st.session_state.get("owner_filter")
    reverse_map = {v: k for k, v in display_to_raw.items()}
    current_display = reverse_map.get(current) if current else None
    if current_display not in options:
        current_display = None
    index = options.index(current_display) if current_display else 0

    target = options[index]
    if st.session_state.get("owner_selectbox") != target:
        st.session_state["owner_selectbox"] = target
```

par :

```python
    current = st.session_state.get("owner_filter")
    reverse_map = {v: k for k, v in display_to_raw.items()}

    # Une valeur de widget déjà présente et valide (dans les options) fait foi :
    # elle reflète une interaction utilisateur récente sur le dropdown. Pendant ce
    # run, owner_filter contient encore l'ancienne valeur, donc resynchroniser le
    # widget dessus écraserait la sélection de l'utilisateur. On ne resynchronise
    # que si la valeur est absente (premier rendu) ou périmée (candidat disparu du
    # breakdown après changement de thème ou de recherche).
    widget_value = st.session_state.get("owner_selectbox")
    if widget_value not in options:
        current_display = reverse_map.get(current) if current else None
        if current_display not in options:
            current_display = None
        target = current_display or "Toutes"
        if widget_value != target:
            st.session_state["owner_selectbox"] = target
```

Le reste du bloc (instantiation du `st.selectbox` sans paramètre `index`, puis le mapping `selected` → `owner_filter`) est **inchangé**.

Scénarios couverts (validés par AppTest avec le patch de la fonction, streamlit 1.63.0) :

| Scénario | Résultat |
|----------|----------|
| Clic sur « Bardella (Jordan) » | `owner_filter = "Jordan Bardella"`, widget = « Bardella (Jordan) », `count_videos` reçoit le filtre |
| Changement de thème, candidat présent | Filtre conservé, liste filtrée |
| Changement de thème, candidat absent | Widget remis à « Toutes », `owner_filter = None` |
| Premier rendu (aucune valeur widget) | Widget créé à « Toutes », pas de filtre |
| Breakdown vide (aucun résultat par candidat) | Reset + `pop` de la clé widget |
| Recherche ultérieure après breakdown vide | Pas de réapplication sournoise, widget = « Toutes » |

### 3. `tests/test_preset_filter_persistence.py` — réécriture complète

Principes :

- **Simuler la vraie interaction** : `at.selectbox(key="owner_selectbox").select("Bardella (Jordan)")` puis `at.run()` (remplace l'écriture directe `at.session_state["owner_filter"] = ...`).
- **Mock `_search_chunks_by_channel` branché sur le `match_query`** (comme prévu initialement par le plan, mais jamais implémenté) et non sur un compteur d'appels fragile.
- Les assertions vérifient à la fois la valeur affichée par le widget, `owner_filter` en session, et le paramètre reçu par `count_videos`.

```python
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
    """Un clic réel sur le dropdown applique le filtre ; un nouveau thème le conserve"""
    """si le candidat est encore présent dans le breakdown."""
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
```

Note : `at.get("selectbox")` renvoie une liste éventuellement vide (`Sequence[Node]`), compatible avec `assert not ...` et pyright. Les autres tests UI (`test_ui_navigation.py`) mockent `search_chunks_by_channel` à `[]` : ils passent par la branche « breakdown vide » désormais munie du `pop`, sans impact sur leurs assertions.

## Tests de non-régression — pourquoi la nouvelle suite détecte le bug

Sur le **code actuel (bugué)**, les tests réécrits échouent dès l'assertion `owner_filter == "Jordan Bardella"` après le clic simulé — le diagnostic AppTest ci-dessus le démontre. Sur le **code corrigé**, ils passent (validé via patch de la fonction dans un diagnostic hors-repo). La suite est donc un vrai garde-fou.

## Vérifications

1. `uv run pytest tests/ -v` — l'ensemble passe, y compris les 4 tests réécrits, et en particulier ils doivent **échouer** si on annule le correctif (garde-fou vérifié manuellement).
2. `uv run pyright` — zéro erreur/avertissement (conformité strict ; `from __future__ import annotations` déjà présent dans les deux fichiers).
3. Fonctionnel manuel : `uv run streamlit run streamlit_app.py`
   - Thème + clic sur un candidat → la liste se filtre immédiatement, le dropdown affiche bien le candidat (chip « Candidat: X » visible).
   - Cliquer sur un autre candidat → filtre appliqué immédiatement (comportement existant, non régressé).
   - Changer de thème où le candidat a des résultats → conservé **et** filtré.
   - Changer vers un thème sans le candidat → retour à « Toutes », liste complète du thème.
   - Recherche sans aucun résultat puis nouvelle recherche → pas de réapplication sournoise de l'ancien filtre.