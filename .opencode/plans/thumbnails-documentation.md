# Plan: Documenter les thumbnails dans AGENTS.md

## Objectif
Ajouter une section "UI Details" dans AGENTS.md pour documenter l'utilisation des thumbnails YouTube, qui ne sont pas stockées en base mais construites dynamiquement.

## Contexte technique
- **URL pattern**: `https://i.ytimg.com/vi_webp/{youtube_str_id}/default.webp`
- **Fichier source**: `src/lucas_v2/ui/app.py`, fonction `_render_video_row()` (lignes 135-156)
- **Layout**: colonnes Streamlit `[1, 4]` — miniature à gauche, contenu à droite
- **CSS dédié**: `.lucas-meta` pour l'alignement du texte sous la miniature (lignes 78-91)
- **Non affichées** dans la vue détail (`_render_video_detail`)

## Modification cible

**Fichier**: `AGENTS.md`

### Ajout: Section 11 — UI Details (après section 10)

```markdown
---

## 11. UI Details

### Thumbnails YouTube

Les thumbnails des vidéos ne sont **pas stockées en base**. Elles sont construites dynamiquement à partir du `youtube_str_id` via l'URL publique YouTube :

```
https://i.ytimg.com/vi_webp/{youtube_str_id}/default.webp
```

**Affichage** : Dans la liste de résultats de recherche (`_render_video_row` dans `ui/app.py`), chaque vidéo est affichée avec :
- Une miniature miniature à gauche (colonne 1/5 via `st.columns([1, 4])`)
- Le titre, la date, le chaîne, l'orientation et le nombre de mentions à droite

**CSS** : Le style `.lucas-meta` aligne la ligne de métadonnées sous le titre, avec un léger décalage négatif (`margin-top: -0.15rem`) pour coller au titre.

**Non utilisées** dans la vue détail d'une vidéo (`_render_video_detail`).
```

## Vérification
- Vérifier que la section s'intègre naturellement après les Turso Limits
- Vérifier que le format est cohérent avec le reste du document (markdown, code blocks)
- Aucun test nécessaire (documentation uniquement)
