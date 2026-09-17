# Plan : Zone cliquable vidéo + correction déprecation `use_container_width`

## Objectif

1. **Zone cliquable** : Dans chaque ligne de résultat (`_render_video_row`), remplacer le bouton titre + le HTML meta par un **seul gros bouton** contenant le titre et les métadonnées, de la hauteur de la miniature (120×90 → ~105px affiché).
2. **Correction déprecation** : Remplacer tous les `use_container_width=True` par `width="stretch"`.

## Fichier modifié

`src/lucas_v2/ui/app.py` — seul fichier concerné.

---

## Changement 1 — Bouton unique dans `_render_video_row` (lignes 135–156)

**Avant :**
```python
def _render_video_row(v: VideoHit) -> None:
    col_thumb, col_content = st.columns([1, 4])
    with col_thumb:
        st.image(
            f"https://i.ytimg.com/vi_webp/{v.youtube_str_id}/default.webp",
            use_container_width=True,
        )
    with col_content:
        title = v.title or v.youtube_str_id
        if st.button(
            title,
            key=f"open_{v.youtube_str_id}",
            type="tertiary",
            use_container_width=True,
        ):
            st.session_state["selected_video_id"] = v.youtube_str_id
            st.session_state["chunk_page"] = 0
            st.rerun()

        meta = _video_meta_line(v)
        meta_line = f"{meta} ({v.mentions} mentions)" if meta else f"({v.mentions} mentions)"
        st.html(f'<div class="lucas-meta">{html.escape(meta_line)}</div>')
```

**Après :**
```python
def _render_video_row(v: VideoHit) -> None:
    col_thumb, col_content = st.columns([1, 4])
    with col_thumb:
        st.image(
            f"https://i.ytimg.com/vi_webp/{v.youtube_str_id}/default.webp",
            width="stretch",
        )
    with col_content:
        title = v.title or v.youtube_str_id
        meta = _video_meta_line(v)
        meta_line = f"{meta} ({v.mentions} mentions)" if meta else f"({v.mentions} mentions)"
        if st.button(
            f"{title}\n{meta_line}",
            key=f"open_{v.youtube_str_id}",
            type="tertiary",
            width="stretch",
        ):
            st.session_state["selected_video_id"] = v.youtube_str_id
            st.session_state["chunk_page"] = 0
            st.rerun()
```

Points clés :
- Le `st.html` meta est supprimé — le texte meta est intégré au label du bouton avec un `\n`
- `use_container_width=True` → `width="stretch"` (image + bouton)
- Le `key` reste identique pour ne pas casser le session state

---

## Changement 2 — CSS : hauteur du bouton = hauteur miniature (dans `_inject_compact_style`)

La miniature YouTube `default.webp` fait 120×90 natif. Affichée dans une colonne 1/5 avec `width="stretch"`, elle fait ~105px de haut à la largeur habituelle (~700px de conteneur).

Ajouter dans le bloc `<style>` de `_inject_compact_style` :

```css
/* Gros bouton cliquable = hauteur miniature */
div[data-testid="stButton"] button[kind="tertiary"] {
    min-height: 105px !important;
    display: flex !important;
    justify-content: flex-start !important;
    align-items: flex-start !important;
    text-align: left !important;
    font-size: 1.15rem !important;
    font-weight: 600 !important;
    line-height: 1.35 !important;
    padding: 0.25rem !important;
    margin: 0 !important;
    white-space: normal !important;
    width: 100% !important;
    border-radius: 0.375rem !important;
    border: 1px solid #e0e0e0 !important;
    cursor: pointer !important;
}
div[data-testid="stButton"] button[kind="tertiary"]:hover {
    background-color: #f5f5f5 !important;
}
```

Le `min-height: 105px` garantit que le bouton est au moins aussi haut que la miniature. Le bouton s'étendra si le texte est long.

---

## Changement 3 — Correction déprecation `use_container_width`

Quatre occurrences dans `app.py`, toutes remplacées par `width="stretch"` :

| Ligne | Avant | Après |
|-------|-------|-------|
| ~140 | `st.image(..., use_container_width=True)` | `st.image(..., width="stretch")` |
| ~148 | `st.button(..., use_container_width=True)` | `st.button(..., width="stretch")` |
| ~180 | `st.link_button(..., use_container_width=True)` | `st.link_button(..., width="stretch")` |
| ~231 | `st.button("Rechercher", ..., use_container_width=True)` | `st.button("Rechercher", ..., width="stretch")` |

(Les lignes 140 et 148 sont déjà couvertes par le changement 1 ci-dessus.)

---

## Changement 4 — Nettoyage CSS obsolète

Le style `.lucas-meta` n'est plus utilisé (le meta est maintenant dans le bouton). **Le supprimer** du bloc `<style>` pour éviter du code mort.

Supprimer :
```css
.lucas-meta {
    font-size: 0.8rem;
    margin-top: -0.15rem !important;
    margin-bottom: 0.75rem !important;
    color: #666;
    text-align: left;
    line-height: 1.2;
}
```

---

## Vérification fonctionnelle

1. `uv run streamlit run streamlit_app.py`
2. Lancer une recherche (ex: `immigr*`)
3. Vérifier que chaque ligne de vidéo affiche :
   - La miniature à gauche (colonne 1/5)
   - Un gros bouton à droite contenant titre + meta, de la même hauteur que la miniature
   - Le bouton a une bordure légère et un effet hover
4. Cliquer sur le bouton → ouvre la vue détail de la vidéo
5. Vérifier que la page de détail fonctionne (bouton retour, pagination chunks)
6. Vérifier le bouton "Rechercher" fonctionne toujours
7. Vérifier les liens timestamp dans la vue détail
8. Plus d'avertissement `use_container_width` dans la console Streamlit
