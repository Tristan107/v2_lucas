# Fix : Les presets nécessitent 2 clics pour afficher le highlight

## Problème

Quand on clique sur un bouton preset thématique (ex: "Éducation"), le style actif
(police blanche sur fond rouge, `type="primary"`) ne s'affiche qu'au **deuxième clic**.

## Cause racine

Ordre d'exécution dans `render_youtube_page()` (`ui/app.py` lignes 496-536) :

1. `_render_preset_row()` est appelé **en premier** (ligne 510)
   - Lit `last_match_query` depuis `session_state` pour déterminer quel preset est actif
2. Le clic sur le preset met à jour `search_input` dans `session_state`
3. Le `st.text_input` retourne l'**ancienne valeur** (vide) sur ce run
   → `_sync_search_state()` n'est jamais appelé (early return ligne 522-523)
4. Au rerun suivant (déclenché par le changement de `search_input`) :
   - `_render_preset_row()` est appelé **avant** `_sync_search_state()` (ligne 533)
   - `last_match_query` est encore l'ancienne valeur → bouton `type="secondary"`
5. Ce n'est qu'au **deuxième clic** que `last_match_query` a été mis à jour
   par `_sync_search_state()` du run précédent → `type="primary"`

## Solution

Ajouter **une seule ligne** dans le handler du clic preset pour mettre à jour
`last_match_query` immédiatement.

### Fichier : `src/lucas_v2/ui/app.py`

Dans `_render_preset_row()` (lignes 407-411), ajouter `last_match_query` :

```python
# AVANT (lignes 407-411) :
            ):
                st.session_state["search_input"] = preset.raw_query
                st.session_state["video_page"] = 0
                st.session_state["chunk_page"] = 0
                st.session_state["owner_filter"] = None

# APRÈS :
            ):
                st.session_state["search_input"] = preset.raw_query
                st.session_state["last_match_query"] = match_query
                st.session_state["video_page"] = 0
                st.session_state["chunk_page"] = 0
                st.session_state["owner_filter"] = None
```

La variable `match_query` est déjà calculée à la ligne 399
(`match_query = build_match_query(preset.raw_query)`), donc on la réutilise directement.

## Pourquoi ça fonctionne

1. Clic sur le preset → `last_match_query` est mis à jour immédiatement
2. Streamlit déclenche un rerun automatique (changement de `search_input`)
3. Au rerun, `_render_preset_row()` lit `last_match_query` = la bonne valeur
4. Le preset correspondant a `active = True` → `type="primary"` → **highlighté**

## Test fonctionnel

1. Lancer `uv run streamlit run streamlit_app.py`
2. Aller sur la page YouTube
3. Cliquer sur un preset (ex: "Éducation")
4. **Vérifier** : le bouton passe immédiatement en `type="primary"` (fond coloré, texte blanc)
5. **Vérifier** : la recherche s'exécute et les résultats s'affichent
6. Cliquer sur un autre preset (ex: "Immigration")
7. **Vérifier** : le highlight passe au nouveau preset, l'ancien redevient secondaire

## Vérification technique

- `uv run pyright` — aucune erreur (pas de changement de type)
- `uv run pytest tests/ -v` — tous les tests passent (pas de logique métier affectée)
