# Densité premier écran — résultats de recherche

## Contexte
`src/lucas_v2/ui/app.py` : chaque vidéo empile titre `###` + meta + bouton
`Voir les extraits` + `st.divider()` → ~150-180px/vidéo, 2-3 visibles seulement.
Header LUCAS intact, `VIDEOS_PER_PAGE=10` inchangé (choix utilisateur).

## Corrections validées avec l'utilisateur
- Bouton à droite du champ : gain vertical = 1 ligne supprimée (mise en colonnes).
  Réduire le bouton (loupe vs texte) ne change rien verticalement → bouton texte conservé.
- Masquer le label `Rechercher` : gain vertical net = 0 (le padding d'alignement du
  bouton compense). Conservé avec `label_visibility="collapsed"` pour lisibilité /
  accessibilité uniquement.

## Changements
1. `_inject_compact_style()` : gaps verticaux + `hr` + classes `.lucas-title` (~1rem,
   1 ligne, ellipsis) et `.lucas-meta` (0.8rem). Ne pas toucher au header.
2. `render_app()` : `st.columns([5, 1])` — champ (label collapsed) + bouton
   `Rechercher` (`use_container_width=True`) sur une seule ligne.
3. `_render_video_list()` : par vidéo `st.columns([4, 1])` — gauche titre compact +
   meta, droite `st.button(f"{mentions} mentions →", type="tertiary",
   key=f"open_{id}")`. Même `session_state` + `rerun()`. Supprimer le bouton
   `Voir les extraits` et alléger `st.divider()`.
   Extraire `_render_video_row(v)` si complexité > 15.

## Fichiers
- Modifié : `src/lucas_v2/ui/app.py` uniquement. Aucun changement DB.

## Vérifications
- `pyright` zéro erreur/warning, complexité ≤ 15.
- `pytest tests/test_search_query.py tests/test_search_db.py`.
- Manuel : densité doublée à 1920×1080, Entrée == clic, clic mentions == ancien
  bouton, `← Retour` conserve page/requête, pagination inchangée.
