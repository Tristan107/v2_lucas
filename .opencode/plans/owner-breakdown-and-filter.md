# Plan : Répartition chaînes + candidats (côte à côte) + Filtrage

## Contexte

L'utilisateur souhaite afficher deux breakdowns côte à côte dans l'interface de recherche :
1. **Répartition par chaîne** : bar chart montrant les mentions par chaîne YouTube
2. **Répartition par candidat (owner)** : bar chart montrant les mentions par candidat/personnalité politique

Les deux breakdowns doivent être **côte à côte** (deux colonnes Streamlit) et chaque item doit être **cliquable** (ou avoir un élément cliquable à côté) pour filtrer les résultats.

## Réponses aux questions

- **Disposition** : `st.columns([1, 1])` — deux colonnes de largeur égale
- **Éléments cliquables** : `st.selectbox` sous chaque breakdown (un par breakdown), permettant de filtrer
- **Filtrage combiné** : les filtres chaîne et owner sont indépendants, combinés avec AND
- **Reset** : option "Toutes" / "Tous" dans chaque selectbox + reset auto quand la requête change

---

## Fichiers à modifier

### 1. `src/lucas_v2/ui/db_search.py`

#### a. Dataclass `ChannelStats` (après `OrientationStats`)

```python
@dataclass(frozen=True, slots=True)
class ChannelStats:
    channel_title: str | None
    matched: int
    total: int
```

#### b. Dataclass `OwnerStats` (après `ChannelStats`)

```python
@dataclass(frozen=True, slots=True)
class OwnerStats:
    owner: str | None
    matched: int
    total: int
```

#### c. Fonction `search_chunks_by_channel`

```python
def search_chunks_by_channel(conn: Any, match_query: str) -> list[ChannelStats]:
    """Return per-channel chunk counts: matched (FTS) vs total (all chunks in DB).

    Results are sorted by ratio descending (highest proportion first).
    Channels with total == 0 are excluded.
    """
```

**Logique :**
- Requête 1 : compter les chunks matchés par `c.title` via FTS
- Requête 2 : compter le total de chunks par `c.title` dans toute la DB
- Combiner et trier par ratio matched/total décroissant

#### d. Fonction `search_chunks_by_owner`

```python
def search_chunks_by_owner(conn: Any, match_query: str) -> list[OwnerStats]:
    """Return per-owner chunk counts: matched (FTS) vs total (all chunks in DB).

    Results are sorted by ratio descending (highest proportion first).
    Owners with total == 0 are excluded.
    """
```

**Logique :**
- Requête 1 : compter les chunks matchés par `c.owner` via FTS
- Requête 2 : compter le total de chunks par `c.owner` dans toute la DB
- Combiner et trier par ratio matched/total décroissant

#### e. Modifier `search_videos` — ajouter filtres channel_filter et owner_filter

Signature modifiée :
```python
def search_videos(
    conn: Any,
    match_query: str,
    limit: int = 10,
    offset: int = 0,
    channel_filter: str | None = None,
    owner_filter: str | None = None,
) -> list[VideoHit]:
```

**Logique :**
- Si `channel_filter` est fourni, ajouter `AND c.title = ?` à la clause WHERE
- Si `owner_filter` est fourni, ajouter `AND c.owner = ?` à la clause WHERE
- Les deux filtres sont combinés avec AND

#### f. Modifier `count_videos` — ajouter les mêmes filtres

Signature modifiée :
```python
def count_videos(
    conn: Any,
    match_query: str,
    channel_filter: str | None = None,
    owner_filter: str | None = None,
) -> int:
```

---

### 2. `src/lucas_v2/ui/app.py`

#### a. Variables de session

Ajouter dans `_sync_search_state` :
```python
st.session_state["channel_filter"] = None
st.session_state["owner_filter"] = None
```

#### b. Imports — ajouter les nouvelles fonctions/dataclasses

```python
from lucas_v2.ui.db_search import (
    ChunkHit,
    VideoHit,
    ChannelStats,
    OwnerStats,
    count_video_chunks,
    count_videos,
    get_video,
    search_chunks_by_channel,
    search_chunks_by_orientation,
    search_chunks_by_owner,
    search_video_chunks,
    search_videos,
)
```

#### c. Fonction `_render_channel_breakdown` (après `_render_orientation_breakdown`)

```python
def _render_channel_breakdown(conn: Any, match_query: str) -> list[ChannelStats]:
    """Render channel breakdown bar chart. Return stats for selectbox options."""
```

**Logique :**
- Appeler `search_chunks_by_channel(conn, match_query)`
- Filtrer les channels avec `total == 0`
- Afficher un bar chart par channel (même format que l'orientation)
- Pas de header titre ici (sera dans le header de colonne)
- Retourner les stats pour alimenter le selectbox

#### d. Fonction `_render_owner_breakdown` (après `_render_channel_breakdown`)

```python
def _render_owner_breakdown(conn: Any, match_query: str) -> list[OwnerStats]:
    """Render owner breakdown bar chart. Return stats for selectbox options."""
```

**Logique :**
- Appeler `search_chunks_by_owner(conn, match_query)`
- Filtrer les owners avec `total == 0`
- Afficher un bar chart par owner (même format que l'orientation)
- Pas de header titre ici (sera dans le colonne)
- Retourner les stats pour alimenter le selectbox

#### e. Modifier `_render_video_list` — layout côte à côte

Remplacer l'appel unique à `_render_orientation_breakdown` par :

```python
def _render_video_list(conn: Any, match_query: str) -> None:
    total = count_videos(conn, match_query)
    if total == 0:
        st.info("Aucun résultat trouvé.")
        return

    # Récupérer les filtres actuels
    channel_filter = st.session_state.get("channel_filter")
    owner_filter = st.session_state.get("owner_filter")

    # Recompter avec filtres pour l'affichage du total
    total = count_videos(conn, match_query, channel_filter, owner_filter)
    if total == 0:
        st.info("Aucun résultat trouvé avec ces filtres.")
        return

    # Breakdown orientation (pleine largeur, au-dessus)
    _render_orientation_breakdown(conn, match_query)

    # Breakdowns chaîne et owner côte à côte
    col_channel, col_owner = st.columns(2)

    with col_channel:
        st.html('<div style="font-size:0.85rem;font-weight:600;color:#444;margin-bottom:6px">Par chaîne</div>')
        channel_stats = _render_channel_breakdown(conn, match_query)
        channel_options = ["Toutes"] + [
            f"{s.channel_title or 'non classé'} ({s.matched}/{s.total})"
            for s in channel_stats
        ]
        # Mapper la sélection vers le channel_title pur
        channel_map = {channel_options[0]: None}
        for s in channel_stats:
            label = f"{s.channel_title or 'non classé'} ({s.matched}/{s.total})"
            channel_map[label] = s.channel_title

        selected_channel = st.selectbox(
            "Filtrer par chaîne",
            channel_options,
            index=0 if not channel_filter else next(
                (i for i, opt in enumerate(channel_options) if channel_map.get(opt) == channel_filter),
                0,
            ),
            key="select_channel",
            label_visibility="collapsed",
        )
        new_channel_filter = channel_map.get(selected_channel)
        if new_channel_filter != channel_filter:
            st.session_state["channel_filter"] = new_channel_filter
            st.rerun()

    with col_owner:
        st.html('<div style="font-size:0.85rem;font-weight:600;color:#444;margin-bottom:6px">Par candidat</div>')
        owner_stats = _render_owner_breakdown(conn, match_query)
        owner_options = ["Tous"] + [
            f"{s.owner or 'non classé'} ({s.matched}/{s.total})"
            for s in owner_stats
        ]
        owner_map = {owner_options[0]: None}
        for s in owner_stats:
            label = f"{s.owner or 'non classé'} ({s.matched}/{s.total})"
            owner_map[label] = s.owner

        selected_owner = st.selectbox(
            "Filtrer par candidat",
            owner_options,
            index=0 if not owner_filter else next(
                (i for i, opt in enumerate(owner_options) if owner_map.get(opt) == owner_filter),
                0,
            ),
            key="select_owner",
            label_visibility="collapsed",
        )
        new_owner_filter = owner_map.get(selected_owner)
        if new_owner_filter != owner_filter:
            st.session_state["owner_filter"] = new_owner_filter
            st.rerun()

    # Chips filtres actifs (au-dessus de la liste)
    _render_active_filters()

    # Pagination et liste
    total_pages = max(1, math.ceil(total / VIDEOS_PER_PAGE))
    page = int(st.session_state.get("video_page", 0))
    page = max(0, min(page, total_pages - 1))
    st.session_state["video_page"] = page

    st.caption(f"{total} vidéos trouvées — Page {page + 1} sur {total_pages}")
    videos = search_videos(
        conn, match_query,
        limit=VIDEOS_PER_PAGE,
        offset=page * VIDEOS_PER_PAGE,
        channel_filter=channel_filter,
        owner_filter=owner_filter,
    )
    for v in videos:
        _render_video_row(v)
    _render_prev_next("video_page", page, total_pages)
```

#### f. Fonction `_render_active_filters`

```python
def _render_active_filters() -> None:
    """Affiche des chips pour les filtres actifs avec bouton × pour supprimer."""
    channel_filter = st.session_state.get("channel_filter")
    owner_filter = st.session_state.get("owner_filter")

    if not channel_filter and not owner_filter:
        return

    chips_html = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:0.5rem">'
    if channel_filter:
        safe = html.escape(channel_filter)
        chips_html += (
            f'<span style="background:#e8f4f8;border-radius:16px;padding:4px 12px;font-size:0.82rem;'
            f'display:inline-flex;align-items:center;gap:6px">'
            f'Chaîne : {safe}'
            f'</span>'
        )
    if owner_filter:
        safe = html.escape(owner_filter)
        chips_html += (
            f'<span style="background:#f0e8f8;border-radius:16px;padding:4px 12px;font-size:0.82rem;'
            f'display:inline-flex;align-items:center;gap:6px">'
            f'Candidat : {safe}'
            f'</span>'
        )
    chips_html += '</div>'
    st.html(chips_html)

    # Boutons reset sous les chips
    col_ch, col_ow, _ = st.columns([1, 1, 3])
    with col_ch:
        if channel_filter and st.button("× Effacer chaîne", key="clear_ch"):
            st.session_state["channel_filter"] = None
            st.rerun()
    with col_ow:
        if owner_filter and st.button("× Effacer candidat", key="clear_ow"):
            st.session_state["owner_filter"] = None
            st.rerun()
```

#### g. Modifier `_sync_search_state`

```python
def _sync_search_state(match_query: str) -> None:
    if st.session_state.get("last_match_query") != match_query:
        st.session_state["last_match_query"] = match_query
        st.session_state["video_page"] = 0
        st.session_state["selected_video_id"] = None
        st.session_state["chunk_page"] = 0
        st.session_state["channel_filter"] = None  # ← ajout
        st.session_state["owner_filter"] = None    # ← ajout
```

---

### 3. `tests/test_search_db.py`

#### a. Imports — ajouter les nouvelles fonctions/dataclasses

```python
from lucas_v2.ui.db_search import (
    count_video_chunks,
    count_videos,
    get_video,
    search_chunks_by_channel,
    search_chunks_by_orientation,
    search_chunks_by_owner,
    search_video_chunks,
    search_videos,
)
```

#### b. Test `test_search_chunks_by_channel_single`

- Une seule chaîne, vérifier que `channel_title` est correct
- Vérifier matched/total

#### c. Test `test_search_chunks_by_channel_multi`

- Plusieurs chaînes avec titres différents
- Vérifier le tri par ratio matched/total

#### d. Test `test_search_chunks_by_channel_empty`

- Requête sans résultat → liste vide

#### e. Test `test_search_chunks_by_owner_single`

- Une seule chaîne, vérifier que owner est correct

#### f. Test `test_search_chunks_by_owner_multi`

- Plusieurs chaînes avec owners différents
- Vérifier le tri par ratio matched/total

#### g. Test `test_search_chunks_by_owner_empty`

- Requête sans résultat → liste vide

#### h. Test `test_search_videos_with_channel_filter`

- Vérifier que le filtre channel fonctionne correctement

#### i. Test `test_search_videos_with_owner_filter`

- Vérifier que le filtre owner fonctionne correctement

#### j. Test `test_search_videos_with_both_filters`

- Vérifier la combinaison AND des deux filtres

---

## Flux utilisateur

1. **Recherche initiale** : L'utilisateur entre une requête et clique "Rechercher"
2. **Affichage** :
   - Bar chart par orientation (pleine largeur)
   - **Deux colonnes côte à côte** :
     - Gauche : "Par chaîne" + bar chart + selectbox "Filtrer par chaîne"
     - Droite : "Par candidat" + bar chart + selectbox "Filtrer par candidat"
   - Chips des filtres actifs (si sélectionnés)
   - Liste des vidéos filtrées
3. **Filtrage par chaîne** :
   - L'utilisateur sélectionne une chaîne dans le selectbox de gauche
   - La liste se met à jour avec les vidéos de cette chaîne uniquement
   - Un chip "Chaîne : Lucides" apparaît au-dessus de la liste
4. **Filtrage par candidat** :
   - L'utilisateur sélectionne un candidat dans le selectbox de droite
   - La liste se met à jour avec les vidéos de ce candidat
   - Un chip "Candidat : Mélenchon" apparaît
5. **Filtrage combiné** :
   - Les deux filtres sont actifs simultanément → AND logique
6. **Suppression des filtres** :
   - Clic sur "× Effacer chaîne" ou "× Effacer candidat"
   - Ou sélection de "Toutes" / "Tous" dans le selectbox
   - Le filtre se supprime et la liste se met à jour

---

## Contraintes techniques

- **Langage** : Tous les strings utilisateur en français
- **Type annotations** : Obligatoires sur toutes les fonctions
- **Complexité cognitive** : ≤ 15 par fonction
- **Tests** : Maintenir la couverture existante
- **Pyright** : Zéro erreur/avertissement
- **Streamlit** : Ne jamais utiliser `use_container_width=True` — utiliser `width="stretch"`

---

## Tests fonctionnels

1. Lancer l'UI : `uv run streamlit run streamlit_app.py`
2. Rechercher un terme (ex: "immigration")
3. Vérifier que les deux breakdowns s'affichent côte à côte
4. Vérifier que le bar chart par chaîne affiche les bonnes chaînes avec pourcentages
5. Vérifier que le bar chart par candidat affiche les bons candidats avec pourpercentages
6. Sélectionner une chaîne dans le selectbox → vérifier que le filtre s'applique
7. Vérifier que le chip "Chaîne : ..." s'affiche
8. Sélectionner un candidat → vérifier que le filtre s'applique en AND
9. Vérifier que les deux chips s'affichent
10. Cliquer "× Effacer chaîne" → vérifier que le filtre se supprime
11. Changer la requête → vérifier que les filtres se reset
12. Lancer les tests : `uv run pytest tests/ -v`
13. Vérifier pyright : `uv run pyright`
