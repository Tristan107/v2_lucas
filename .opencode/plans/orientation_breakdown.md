# Plan : Répartition des chunks par orientation après recherche

## Objectif

Afficher au-dessus des résultats de recherche un récapitulatif du nombre de chunks matchant la requête par orientation (`channel.orientation`), divisé par le nombre total de chunks en base pour cette orientation, sous forme de barres de progression colorées.

## Fichiers modifiés

| Fichier | Changement |
|---|---|
| `src/lucas_v2/ui/db_search.py` | Ajouter `OrientationStats` dataclass + `search_chunks_by_orientation()` |
| `src/lucas_v2/ui/app.py` | Ajouter `_render_orientation_breakdown()` + import + appel dans `_render_video_list()` |
| `tests/test_search_db.py` | Tests de la nouvelle fonction DB |

## Étape 1 : `src/lucas_v2/ui/db_search.py` — Nouveau dataclass + fonction DB

### 1a. Ajouter le dataclass `OrientationStats`

Après la définition de `ChunkHit` (ligne 25), ajouter :

```python
@dataclass(frozen=True, slots=True)
class OrientationStats:
    orientation: str | None
    matched: int
    total: int
```

### 1b. Ajouter `search_chunks_by_orientation()`

Nouvelle fonction après `count_video_chunks()` (ligne 141). Deux requêtes SQL :

**Requête 1 — chunks matchant par orientation :**
```sql
SELECT c.orientation, COUNT(*) AS matched
FROM transcript_chunk_fts f
JOIN transcript_chunk tc ON tc.id = f.rowid
JOIN video v ON v.id = tc.fk_video_id
LEFT JOIN channel c ON c.id = v.fk_channel_id
WHERE transcript_chunk_fts MATCH ?
GROUP BY c.orientation
```

**Requête 2 — total chunks par orientation (dénominateur) :**
```sql
SELECT c.orientation, COUNT(tc.id) AS total
FROM transcript_chunk tc
JOIN video v ON v.id = tc.fk_video_id
LEFT JOIN channel c ON c.id = v.fk_channel_id
GROUP BY c.orientation
```

**Logique de fusion en Python :**
- Exécuter les deux requêtes
- Construire un dict `orientation → total` depuis la requête 2
- Pour chaque row de la requête 1, créer `OrientationStats(orientation, matched, total=lookup[orientation])`
- Trier par ratio décroissant (`matched / total`)
- Retourner `list[OrientationStats]`

Signature :
```python
def search_chunks_by_orientation(conn: Any, match_query: str) -> list[OrientationStats]:
```

## Étape 2 : `src/lucas_v2/ui/app.py` — Rendu HTML des barres

### 2a. Ajouter l'import

Ajouter `OrientationStats` et `search_chunks_by_orientation` à l'import depuis `lucas_v2.ui.db_search`.

### 2b. Ajouter le mapping des couleurs

```python
ORIENTATION_COLORS: dict[str, str] = {
    "extrême gauche": "#B22222",
    "gauche": "#E63946",
    "centre gauche": "#F4A9A8",
    "centre droit": "#A8C8E8",
    "droite": "#1D3557",
    "extrême droite": "#2D2D2D",
}
_DEFAULT_COLOR = "#999999"
```

### 2c. Ajouter `_render_orientation_breakdown(conn, match_query)`

- Appelle `search_chunks_by_orientation(conn, match_query)`
- Si la liste est vide → retourner immédiatement
- Filtrer les entrées où `total == 0` (ratio 0/0 → pas pertinent)
- Si après filtrage rien à afficher → retourner
- Rendre via `st.html()` :
  - Titre : **"Répartition par orientation"** (style gras, taille ~1rem)
  - Pour chaque `OrientationStats` (trié par ratio décroissant) :
    - Ligne avec : nom de l'orientation (coloré), `matched/total` en gris, pourcentage en gras
    - Barre `<div>` : `height: 8px`, `border-radius: 4px`, fond gris clair (`#e0e0e0`), remplissage coloré avec `width` = `min(ratio * 100, 100)%`
- Utiliser `html.escape()` sur les noms d'orientation pour éviter les injections HTML

### 2d. Intégrer dans `_render_video_list()`

Après la vérification `if total == 0: ... return` (ligne 201), avant `total_pages = ...` (ligne 204), ajouter :

```python
_render_orientation_breakdown(conn, match_query)
```

## Étape 3 : Tests dans `tests/test_search_db.py`

### Test `test_search_chunks_by_orientation`
- Créer 2 channels avec orientations différentes ("gauche", "droite")
- Créer 2 videos (1 par channel)
- Créer des chunks avec texte variable (certains matchent "travail*", d'autres non)
- Appeler `search_chunks_by_orientation(conn, "travail*")`
- Vérifier que les ratios sont corrects

### Test `test_search_chunks_by_orientation_empty`
- Créer des channels/videos/chunks sans aucun match
- Vérifier que la liste retournée est vide (ou tous ratios à 0)

## Étape 4 : Vérifications

- [ ] `uv run pyright` → 0 erreurs
- [ ] `uv run pytest tests/ -v` → tous les tests passent
- [ ] `uv run streamlit run streamlit_app.py` → vérifier visuellement l'affichage des barres
