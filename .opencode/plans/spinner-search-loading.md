# Plan : Ajout d'un spinner de chargement sous la barre de recherche

## Contexte

L'UI Streamlit de Lucas v2 n'a aucun indicateur de chargement quand l'utilisateur lance une recherche. La page semble figée le temps que les requêtes FTS5 s'exécutent. L'objectif est d'ajouter un spinner natif Streamlit (`st.spinner()`) sous la barre de recherche pendant le chargement des résultats.

## Fichier modifié

`src/lucas_v2/ui/app.py` — fonction `render_youtube_page()`

## Modification

Dans la fonction `render_youtube_page()` (lignes 239-251), envelopper le bloc d'exécution de la recherche dans un `st.spinner()`.

### Avant (lignes 239-251)

```python
    _sync_search_state(match_query)
    conn = _get_conn()
    selected = st.session_state.get("selected_video_id")
    if selected:
        _render_video_detail(conn, match_query, str(selected))
    else:
        _render_video_list(conn, match_query)
```

### Après

```python
    _sync_search_state(match_query)
    conn = _get_conn()
    with st.spinner("Recherche en cours…"):
        selected = st.session_state.get("selected_video_id")
        if selected:
            _render_video_detail(conn, match_query, str(selected))
        else:
            _render_video_list(conn, match_query)
```

## Vérifications

1. `uv run streamlit run streamlit_app.py` — tester manuellement :
   - Le spinner apparaît sous la barre de recherche pendant le chargement
   - Le spinner disparaît quand les résultats s'affichent
   - La pagination fonctionne toujours
   - Le clic sur une vidéo et le retour à la liste fonctionnent
2. `uv run pyright` — zéro erreur de type
