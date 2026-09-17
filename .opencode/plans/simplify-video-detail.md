# Plan : Simplifier la page de détail vidéo

## Résumé des changements

7 modifications dans 2 fichiers, toutes dans `src/lucas_v2/ui/app.py` et `streamlit_app.py`.

---

## 1. Supprimer le bouton "← Accueil" de la page YouTube

**Fichier** : `streamlit_app.py`, lignes 112-113

```python
# SUPPRIMER ces 2 lignes :
if st.button("← Accueil"):
    _navigate_to("home")
```

La navigation vers l'accueil reste possible via le bouton "← Accueil" de la page Sondages.

---

## 2. Masquer la barre de recherche quand on affiche le détail d'une vidéo

**Fichier** : `src/lucas_v2/ui/app.py`, fonction `render_youtube_page()` (lignes 312-340)

Actuellement, la barre de recherche (`st.text_input` + bouton) s'affiche toujours. Quand `selected_video_id` est défini, on est en mode détail — la barre de recherche n'a rien à faire là.

**Changement** : Déplacer la barre de recherche dans un bloc conditionnel `if not selected:`.

```python
def render_youtube_page() -> None:
    _inject_compact_style()
    _render_youtube_header()

    selected = st.session_state.get("selected_video_id")

    if selected:
        # Mode détail : pas de barre de recherche
        conn = _get_conn()
        match_query = str(st.session_state.get("last_match_query", ""))
        with st.spinner("Recherche en cours…"):
            _render_video_detail(conn, match_query, str(selected))
        return

    # Mode liste : barre de recherche
    col_search, col_btn = st.columns([5, 1])
    with col_search:
        raw_query = st.text_input("Rechercher", placeholder="immigr* OR travail*", label_visibility="collapsed")
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
```

---

## 3. Supprimer le `st.divider()` avant la pagination

**Fichier** : `src/lucas_v2/ui/app.py`, fonction `_render_video_detail()`, ligne 308

```python
# SUPPRIMER cette ligne :
    st.divider()
```

C'est le trait qui chevauche "Précédent" / "Suivant".

---

## 4. Supprimer le bouton "Voir sur YouTube"

**Fichier** : `src/lucas_v2/ui/app.py`, fonction `_render_video_detail()`, ligne 290

```python
# SUPPRIMER cette ligne :
    st.link_button("Voir sur YouTube", f"https://www.youtube.com/watch?v={v.youtube_str_id}")
```

Les boutons de timestamp suffisent pour naviguer vers YouTube.

---

## 5. Reformater la ligne de métadonnées

**Fichier** : `src/lucas_v2/ui/app.py`, fonction `_render_video_detail()`, lignes 287-289

Remplacer :
```python
    meta = _video_meta_line(v)
    if meta:
        st.caption(f"{meta} • {v.mentions} segments")
```

Par :
```python
    meta = _video_meta_line(v)
    if meta:
        st.caption(f"{meta} • {total} extraits sur {v.mentions}")
```

`total` = nombre d'extraits correspondant à la recherche (déjà calculé juste après via `count_video_chunks`), `v.mentions` = nombre total de chunks de la vidéo. Il faut donc déplacer le calcul de `total` avant l'affichage de la métadonnée.

---

## 6. Supprimer la caption de pagination redondante

**Fichier** : `src/lucas_v2/ui/app.py`, fonction `_render_video_detail()`, ligne 302

```python
# SUPPRIMER cette ligne :
    st.caption(f"{total} extraits — Page {page + 1} sur {total_pages}")
```

L'info est maintenant intégrée dans la ligne de métadonnées (étape 5).

---

## 7. Ajouter de l'espace entre les boutons de timestamp

**Fichier** : `src/lucas_v2/ui/app.py`, fonction `_render_video_detail()`

Dans la boucle qui affiche les chunks, ajouter un espaceur entre chaque chunk (sauf le dernier) :

```python
    for i, ch in enumerate(chunks):
        _render_chunk_row(ch)
        if i < len(chunks) - 1:
            st.html("<div style='margin-bottom:0.5rem'></div>")
```

---

## Résumé des fichiers modifiés

| Fichier | Changement |
|---------|-----------|
| `streamlit_app.py` | Supprimer le bouton "← Accueil" (2 lignes) |
| `src/lucas_v2/ui/app.py` | Masquer la barre de recherche en mode détail, supprimer `st.divider()`, supprimer "Voir sur YouTube", reformater métadonnées, supprimer caption pagination, ajouter espace entre chunks |

## Tests fonctionnels

1. `uv run streamlit run streamlit_app.py`
2. Aller sur YouTube, faire une recherche → la barre de recherche apparaît
3. Cliquer sur une vidéo → la barre de recherche disparaît, le titre + métadonnées s'affichent
4. Vérifier qu'il n'y a pas de "← Accueil", ni de "← Retour à la liste", ni de "Voir sur YouTube"
5. Vérifier la ligne de métadonnées : `12/09/2026 • Jean-Luc Mélenchon • [gauche] • 2 extraits sur 149`
6. Vérifier qu'il n'y a pas de caption "X extraits — Page 1 sur Y" séparée
7. Vérifier que les boutons de timestamp ont de l'espace entre eux
8. Vérifier qu'il n'y a pas de trait horizontal qui chevauche "Précédent" / "Suivant"
9. Revenir à la liste via le bouton "← Précédent" (la barre de recherche réapparaît avec la requête précédente)
10. Vérifier `uv run pytest tests/ -v` et `uv run pyright` passent
