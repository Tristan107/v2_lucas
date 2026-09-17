# Plan : Rendre les thumbnails YouTube cliquables

## Contexte

Dans `_render_video_row` (`ui/app.py`), la miniature YouTube (`st.image`) n'est pas cliquable. Le CSS overlay avec `st.button("")` + `position: absolute` ne fonctionne pas car le DOM Streamlit ne correspond pas aux sélecteurs CSS utilisés.

## Solution retenue : `st.form` + `st.form_submit_button`

Wrapper l'image dans un `st.form` borderless avec un `st.form_submit_button` "▶" qui déclenche l'ouverture de la vue détail. C'est l'approche la plus fiable car elle utilise le mécanisme natif de Streamlit.

## Fichiers à modifier

### `src/lucas_v2/ui/app.py`

#### 1. `_render_video_row` (l.153-167)

Remplacer le bloc `col_thumb` actuel :

```python
def _render_video_row(v: VideoHit) -> None:
    col_thumb, col_content = st.columns([1, 4])
    with col_thumb:
        with st.form(key=f"tf_{v.youtube_str_id}", clear_on_submit=False, border=False):
            st.image(
                f"https://i.ytimg.com/vi_webp/{v.youtube_str_id}/default.webp",
                use_container_width=True,
            )
            if st.form_submit_button("▶", use_container_width=True):
                st.session_state["selected_video_id"] = v.youtube_str_id
                st.session_state["chunk_page"] = 0
                st.rerun()
    with col_content:
        # ... reste inchangé
```

#### 2. `_inject_compact_style` (l.83-99)

Supprimer le CSS overlay cassé (l.83-99) et ajouter un style pour le bouton du formulaire :

```css
/* Supprimer ces lignes :
div[data-testid="stColumn"]:has(div[data-testid="stImage"]) {
    position: relative;
}
div[data-testid="stColumn"]:has(div[data-testid="stImage"]) button {
    position: absolute;
    ...
}
```

Remplacer par :

```css
/* Thumbnail form submit button */
div[data-testid="stForm"] div[data-testid="stButton"] button {
    font-size: 0.8rem !important;
    padding: 0.1rem 0.5rem !important;
    min-height: unset !important;
    line-height: 1.2 !important;
}
```

## Tests

- `uv run pyright` — zéro erreur
- `uv run pytest tests/ -v` — tests existants passent
- Vérification manuelle : le bouton "▶" sur la miniature est cliquable et ouvre la vue détail
