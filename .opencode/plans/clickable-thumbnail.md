# Plan : Rendre le thumbnail cliquable (vue détail)

## Contexte

Dans `_render_video_row` (`src/lucas_v2/ui/app.py`, ligne 136-157), le thumbnail est un `st.image()` statique. L'utilisateur veut qu'un clic sur le thumbnail ouvre la vue détail de la vidéo (même comportement que le bouton titre).

**Contrainte** : `st.components.v1.html()` crée un iframe isolé — le JavaScript dans l'iframe ne peut pas modifier `st.session_state` directement. On utilise `window.frameElement` pour remonter au DOM parent Streamlit.

## Solution proposée

Remplacer `st.image()` par `st.components.v1.html()` avec un `<img>` cliquable. Le handler JavaScript utilise `window.frameElement` pour retrouver l'iframe dans le DOM parent, puis clique le bouton titre dans la même ligne.

### Fichier modifié : `src/lucas_v2/ui/app.py`

#### 1. Nouvelle fonction `_render_clickable_thumbnail`

```python
def _render_clickable_thumbnail(youtube_str_id: str) -> None:
    """Affiche un thumbnail YouTube cliquable qui ouvre la vue détail."""
    thumb_url = f"https://i.ytimg.com/vi_webp/{youtube_str_id}/default.webp"
    safe_id = html.escape(youtube_str_id)
    safe_url = html.escape(thumb_url)

    st.components.v1.html(
        f"""
        <style>
            .thumb-link img {{
                width: 100%;
                border-radius: 8px;
                cursor: pointer;
                transition: opacity 0.2s;
            }}
            .thumb-link:hover img {{
                opacity: 0.85;
            }}
        </style>
        <a class="thumb-link" href="#" data-video-id="{safe_id}">
            <img src="{safe_url}" alt="Miniature" />
        </a>
        <script>
        document.querySelector('.thumb-link').addEventListener('click', function(e) {{
            e.preventDefault();
            // window.frameElement = l'élément <iframe> dans le DOM parent
            var iframe = window.frameElement;
            if (!iframe) return;
            // Remonter au stHorizontalBlock (st.columns) contenant cette ligne
            var block = iframe.closest('[data-testid="stHorizontalBlock"]');
            if (!block) return;
            // La 2ème colonne contient le bouton titre
            var columns = block.querySelectorAll('[data-testid="stColumn"]');
            if (columns.length >= 2) {{
                var btn = columns[1].querySelector('button[kind="tertiary"]');
                if (btn) btn.click();
            }}
        }});
        </script>
        """,
        height=120,
    )
```

#### 2. Modifier `_render_video_row`

Remplacer le bloc `st.image()` par `_render_clickable_thumbnail()` :

```python
def _render_video_row(v: VideoHit) -> None:
    col_thumb, col_content = st.columns([1, 4])
    with col_thumb:
        _render_clickable_thumbnail(v.youtube_str_id)  # ← remplace st.image()
    with col_content:
        # ... reste identique (bouton titre + métadonnées)
```

### Comment ça marche le sélecteur DOM

```
stHorizontalBlock
├── stColumn (colonne 1 — thumbnail)
│   └── <iframe> ← window.frameElement nous donne cet élément
│       └── <a class="thumb-link" data-video-id="abc123">
│           └── <img> (le thumbnail)
└── stColumn (colonne 2 — contenu)
    └── button[kind="tertiary"] ← on clique celui-ci
```

- `window.frameElement` → récupère l'élément `<iframe>` dans le DOM parent (pas de cross-origin puisque c'est du même domaine)
- `.closest('[data-testid="stHorizontalBlock"]')` → remonte au conteneur `st.columns`
- `columns[1].querySelector('button[kind="tertiary"]')` → cible le bouton titre dans la 2ème colonne

**Avantage** : Pas besoin de chercher par texte ou par clé `open_{id}` — le sélecteur est basé sur la structure DOM des colonnes, ce qui est plus robuste.

## Tradeoffs

| Aspect | Détail |
|--------|--------|
| **Fonctionnel** | Le clic ouvre bien la vue détail (même behavior que le bouton titre) |
| **Robustesse** | `window.frameElement` + sélection par colonne = plus robuste que par texte/clé |
| **Fragilité** | Dépend de la structure DOM Streamlit (`stHorizontalBlock`, `stColumn`, `button[kind="tertiary"]`). Peut casser si Streamlit change sa structure DOM |
| **Hauteur** | `height=120` pour l'iframe — à ajuster selon le rendu souhaité |
| **data-video-id** | Inutile pour le clic actuel, mais conservé comme attribute data- pour usage futur (logging, analytics) |

## Plan de test

1. `uv run streamlit run streamlit_app.py`
2. Lancer une recherche (ex: "immigration")
3. Vérifier que le thumbnail est affiché avec un curseur pointer au survol
4. **Cliquer sur le thumbnail** → la vue détail de la vidéo s'ouvre ✅
5. Cliquer "← Retour à la liste" → retour à la liste
6. Cliquer sur le bouton titre → même comportement qu'avant (pas de regression) ✅
7. Vérifier que pyright passe : `uv run pyright`
8. Lancer les tests : `uv run pytest tests/ -v`
