# Fix : Répartition par owner + filtre par owner

## Résumé
Corriger deux bugs : (1) la répartition par chaîne affiche le titre de la chaîne au lieu du nom du owner, (2) le filtre par chaîne ne fonctionne pas. Ajouter une contrainte UNIQUE sur `owner` en DB.

## Problèmes identifiés

| Bug | Fichier | Ligne | Cause |
|-----|---------|-------|-------|
| Affiche titre chaîne | app.py | L262 | `_render_channel_breakdown` utilise `s.channel_title` au lieu de `s.owner` |
| Pas de champ owner | db_search.py | L52-56 | `ChannelStats` n'a pas de champ `owner` |
| Requête ne sélectionne pas owner | db_search.py | L276 | `search_chunks_by_channel` sélectionne `c.title` pas `c.owner` |
| Filtre sur mauvaise colonne | db_search.py | L74-75 | `search_videos` filtre sur `c.title` au lieu de `c.owner` |
| Sélecteur utilise titres | app.py | L282-285 | Les options du selectbox sont les titres de chaîne |

## Étapes d'implémentation

### 1. Schema : ajouter UNIQUE sur owner
**Fichier :** `src/lucas_v2/db/schema.sql`

Ajouter après la définition de la table `channel` :
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_channel_owner_unique ON channel(owner) WHERE owner IS NOT NULL;
```

### 2. Dataclass : ajouter owner à ChannelStats
**Fichier :** `src/lucas_v2/ui/db_search.py`

```python
@dataclass(frozen=True, slots=True)
class ChannelStats:
    owner: str | None       # ← nouveau (remplace channel_title)
    orientation: str | None
    matched: int
    total: int
```

### 3. Requête : sélectionner owner dans search_chunks_by_channel
**Fichier :** `src/lucas_v2/ui/db_search.py`

Modifier la requête matched_rows (L275-283) :
```sql
-- AVANT
SELECT v.fk_channel_id, c.title, c.orientation, COUNT(*) AS matched
-- APRÈS
SELECT v.fk_channel_id, c.owner, c.orientation, COUNT(*) AS matched
```

Modifier la construction de ChannelStats (L306-312) :
```python
ChannelStats(
    owner=title,       # ← c'est maintenant c.owner
    orientation=orient,
    matched=matched,
    total=total,
)
```

### 4. UI : afficher owner dans le breakdown
**Fichier :** `src/lucas_v2/ui/app.py`

Dans `_render_channel_breakdown()` (L251-289) :
- Filtrer les stats pour exclure les owners NULL : `stats = [s for s in stats if s.owner is not None]`
- Label : `s.owner` au lieu de `s.channel_title`
- Selectbox options : `["Toutes"] + [s.owner for s in stats]`
- Session state : `owner_filter` au lieu de `channel_filter`
- Titre de la section : "Répartition par candidat" au lieu de "Répartition par chaîne"

### 5. Filtre : utiliser owner dans search_videos et count_videos
**Fichier :** `src/lucas_v2/ui/db_search.py`

Dans `search_videos()` et `count_videos()` :
- Renommer le paramètre `channel_filter` → `owner_filter` (si pas déjà fait)
- Clause WHERE : `c.owner = ?` au lieu de `c.title = ?`

### 6. UI : passer owner_filter dans _render_video_list
**Fichier :** `src/lucas_v2/ui/app.py`

Dans `_render_video_list()` :
- Lire `owner_filter` depuis session_state (pas `channel_filter`)
- Passer `owner_filter` à `search_videos()` et `count_videos()`

### 7. Chips : afficher "Candidat: X" au lieu de "Chaîne: X"
**Fichier :** `src/lucas_v2/ui/app.py`

Dans `_render_active_filters()` :
- Utiliser `owner_filter` au lieu de `channel_filter`
- Label : "Candidat:" au lieu de "Chaîne:"

### 8. Tests : mettre à jour
**Fichier :** `tests/test_search_db.py`

- `test_search_chunks_by_channel_single` : vérifier `s.owner == "Alice"`
- `test_search_chunks_by_channel_multi` : vérifier `s.owner`
- `test_search_chunks_by_channel_null_title` : ce channel a owner="Bob", pas NULL. Ajouter un test avec owner=NULL qui vérifie qu'il est exclu
- `test_search_videos_with_channel_filter` → renommer en `test_search_videos_with_owner_filter` et utiliser `owner_filter="Alice"`
- `test_count_videos_with_filters` : adapter les appels

## Fichiers modifiés

| Fichier | Type |
|---------|------|
| `src/lucas_v2/db/schema.sql` | Ajout index UNIQUE owner |
| `src/lucas_v2/ui/db_search.py` | ChannelStats.owner, requête, filtres |
| `src/lucas_v2/ui/app.py` | Breakdown owner, filtre owner, chips |
| `tests/test_search_db.py` | Tests adaptés |

## Validation

```bash
uv run pytest tests/ -v
uv run pyright
uv run streamlit run streamlit_app.py
```

Vérifier dans l'UI :
1. La répartition affiche les noms des candidats (pas des chaînes)
2. Les owners NULL ne sont pas affichés
3. Sélectionner un candidat filtre les vidéos
4. Le chip affiche "Candidat: X"
5. "Effacer tous" supprime le filtre
