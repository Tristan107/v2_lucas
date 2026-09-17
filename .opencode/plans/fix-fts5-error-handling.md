# Fix : Gestion d'erreur FTS5 trop large dans `db_search.py`

## Problème

Quand l'utilisateur tape `feu*` (ou toute autre requête), le log affiche parfois :
```
Requête FTS5 invalide : feu*
```
alors que `feu*` est une syntaxe FTS5 parfaitement valide (query prefix).

**Cause racine** : Les blocs `except ValueError:` dans `db_search.py` attrapent **toutes** les `ValueError` de `libsql_experimental` et les classifient toutes comme "Requête FTS5 invalide". Or `libsql_experimental` wrappe **toutes** les erreurs SQLite/Turso en `ValueError` — pas seulement les erreurs de syntaxe FTS5.

Quand une erreur transitoire Turso se produit (glitch réseau, cursor timeout, etc.), elle est correctement gérée par `DbConn` uniquement si le message contient `"stream not found"`. Les autres `ValueError` sont re-raises par `DbConn` puis attrapées par les blocs `except ValueError:` de `db_search.py`, qui les classifient à tort comme erreurs de syntaxe FTS5.

**Preuve** : Toutes les requêtes FTS5 avec `feu*` fonctionnent parfaitement (348 vidéos, 6 orientations). Les vraies erreurs FTS5 contiennent `"fts5: syntax err"` dans le message (pas de "stream"), tandis que les erreurs transitoires contiennent d'autres messages.

## Solution

Modifier les 5 blocs `except ValueError:` dans `db_search.py` pour inspecter le message d'erreur :

1. Si le message contient `"fts5"` ou `"syntax"` → c'est une vraie erreur de syntaxe FTS5 → logger `"Requête FTS5 invalide : {query}"` (comme avant)
2. Sinon → c'est une erreur transitoire/connexion → logger le vrai message d'erreur avec `logger.error()` pour debugging
3. Dans les deux cas, retourner `[]` / `0` (dégradation gracieuse, comportement actuel préservé)

## Fichiers à modifier

### `src/lucas_v2/ui/db_search.py`

Ajouter une fonction helper en haut du fichier :

```python
def _log_fts_error(match_query: str, e: ValueError) -> None:
    """Classe et logge les erreurs ValueError des requêtes FTS5."""
    err_msg = str(e).lower()
    if "fts5" in err_msg or "syntax" in err_msg:
        logger.warning("Requête FTS5 invalide : %s", match_query)
    else:
        logger.error("Erreur de connexion lors de la recherche FTS5 (query=%s) : %s", match_query, e)
```

Puis remplacer chaque bloc :

```python
# Avant
except ValueError:
    logger.warning("Requête FTS5 invalide : %s", match_query)
    return []

# Après
except ValueError as e:
    _log_fts_error(match_query, e)
    return []
```

**5 endroits à modifier** (lignes 58-60, 95-97, 123-125, 164-166, 187-189) :

| Fonction | Ligne actuelle |
|----------|---------------|
| `search_videos` | 58-60 |
| `search_video_chunks` | 95-97 |
| `count_videos` | 123-125 |
| `count_video_chunks` | 164-166 |
| `search_chunks_by_orientation` | 187-189 |

### `tests/test_search_db.py`

Ajouter des tests pour vérifier le comportement d'erreur :

1. **Test requête FTS5 invalide** : Mock `conn.execute()` pour lever `ValueError("fts5: syntax err")` → vérifier que `logger.warning` est appelé avec "Requête FTS5 invalide"
2. **Test erreur transitoire** : Mock `conn.execute()` pour lever `ValueError("network timeout")` → vérifier que `logger.error` est appelé avec le vrai message d'erreur
3. **Test requête valide** : Vérifier qu'aucun log n'est émis pour une requête correcte comme `feu*`

## Validation

1. `uv run pytest tests/test_search_db.py -v` — tests existants + nouveaux
2. `uv run pytest tests/test_search_query.py -v` — tests de build_match_query intacts
3. `uv run pyright` — zéro erreur
4. Vérification manuelle dans Streamlit : taper `feu*` dans la recherche, observer les logs — le message "Requête FTS5 invalide" ne doit plus apparaître pour des requêtes valides
