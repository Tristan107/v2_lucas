# Fix: Filtre candidat ne fonctionne pas

## Contexte

Le filtre par candidat dans l'UI Streamlit (`src/lucas_v2/ui/app.py`) a 3 bugs :
1. Le filtre ne s'applique pas quand on change de candidat
2. Le selectbox est saisissable (l'utilisateur veut un dropdown classique)
3. Le chip "Candidat: X" est toujours rouge au lieu d'utiliser la couleur du candidat

**Bug bonus** : les options du selectbox peuvent contenir des doublons (un candidat avec plusieurs chaînes).

---

## Root cause — Bug 1

Dans `_render_video_list()` (lignes 317-348), la variable `owner_filter` est lue à la ligne 318 **avant** que `_render_channel_breakdown()` (ligne 329) ne rende le selectbox. Le selectbox écrit la nouvelle valeur dans `session_state` (ligne 288), mais la variable Python `owner_filter` reste l'ancienne valeur pendant toute l'exécution. Résultat : `search_videos()` et `count_videos()` sont appelés avec l'ancien filtre.

---

## Fichier modifié

`src/lucas_v2/ui/app.py`

---

## Changements

### 1. `_render_video_list()` — Réordonner le rendu

Déplacer les breakdowns (qui contiennent le selectbox) AVANT la lecture de `owner_filter` et les requêtes.

**Avant** (lignes 317-348) :
```python
def _render_video_list(conn: Any, match_query: str) -> None:
    owner_filter = st.session_state.get("owner_filter")      # ANCIENNE valeur
    total = count_videos(conn, match_query, owner_filter=owner_filter)
    if total == 0:
        st.info("Aucun résultat trouvé.")
        return
    col_orient, col_channel = st.columns(2)
    with col_orient:
        _render_orientation_breakdown(conn, match_query)
    with col_channel:
        _render_channel_breakdown(conn, match_query)          # met à jour session_state
    _render_active_filters()
    # ... reste avec owner_filter = ancienne valeur
```

**Après** :
```python
def _render_video_list(conn: Any, match_query: str) -> None:
    # 1. Rendre les breakdowns EN PREMIER (le selectbox met à jour session_state)
    col_orient, col_channel = st.columns(2)
    with col_orient:
        _render_orientation_breakdown(conn, match_query)
    with col_channel:
        _render_channel_breakdown(conn, match_query)

    # 2. Lire le filtre APRÈS le selectbox
    owner_filter = st.session_state.get("owner_filter")

    # 3. Compter et afficher les résultats avec le bon filtre
    total = count_videos(conn, match_query, owner_filter=owner_filter)
    if total == 0:
        st.info("Aucun résultat trouvé.")
        return

    _render_active_filters()

    total_pages = max(1, math.ceil(total / VIDEOS_PER_PAGE))
    page = int(st.session_state.get("video_page", 0))
    page = max(0, min(page, total_pages - 1))
    st.session_state["video_page"] = page

    st.caption(f"{total} vidéos trouvées — Page {page + 1} sur {total_pages}")
    videos = search_videos(
        conn, match_query,
        limit=VIDEOS_PER_PAGE, offset=page * VIDEOS_PER_PAGE,
        owner_filter=owner_filter,
    )
    for v in videos:
        _render_video_row(v)
    _render_prev_next("video_page", page, total_pages)
```

### 2. `_render_channel_breakdown()` — Dédupliquer + non-saisissable + sauver les couleurs

**a) Dédupliquer les options** (un candidat avec 2 chaînes = 1 seule option) :

Remplacer la ligne 281 `options = ["Toutes"] + [s.owner for s in stats]` par :
```python
seen_owners: set[str] = set()
unique_stats: list[ChannelStats] = []
for s in stats:
    if s.owner and s.owner not in seen_owners:
        seen_owners.add(s.owner)
        unique_stats.append(s)
options = ["Toutes"] + [s.owner for s in unique_stats]
```

**b) Rendre le selectbox non-saisissable** :

```python
selected = st.selectbox(
    "Filtrer par candidat",
    options,
    index=index,
    key="owner_selectbox",
    accept_new_options=False,
    filter_mode=None,
)
```

`filter_mode=None` désactive complètement la saisie (vérifié dans le code source de Streamlit — les options sont `'fuzzy'`, `'contains'`, `'prefix'`, ou `None`).

**c) Sauvegarder le mapping owner→orientation pour la couleur du chip** :

Ajouter après le bloc du selectbox (après la ligne 288) :
```python
owner_orientation: dict[str, str | None] = {}
for s in stats:
    if s.owner and s.owner not in owner_orientation:
        owner_orientation[s.owner] = s.orientation
st.session_state["owner_orientation"] = owner_orientation
```

### 3. `_render_active_filters()` — Couleur dynamique du chip + suppression du bouton "Effacer tous"

Remplacer les couleurs hardcoded par la couleur de l'orientation du candidat, et supprimer le bouton "Effacer tous" (il ne fonctionne pas car `st.rerun()` ne clear pas le widget selectbox — la valeur est gardée via le `key`).

```python
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
```

Note : `{color}15` ajoute un alpha hex (~8%) pour un fond pastel. Les couleurs dans `ORIENTATION_COLORS` sont toutes en format 7 caractères (`#B22222`), donc `#B2222215` est un hex 8 caractères (rgba) — CSS valide.

---

## Vérifications

1. **Fonctionnel** : Lancer `uv run streamlit run streamlit_app.py`, chercher un terme, changer le candidat → la liste se filtrer immédiatement
2. **Dropdown classique** : Impossible de taper dans le selectbox
3. **Chip coloré** : Le chip "Candidat: X" affiche la couleur de l'orientation
4. **Doublons** : Un candidat avec plusieurs chaînes n'apparaît qu'une fois
5. **Tests** : `uv run pytest tests/ -v` passe
6. **Types** : `uv run pyright` sans erreurs
