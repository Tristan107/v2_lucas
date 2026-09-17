# Plan : Recherche OU + Fix crash FTS5 + Sanitization

## Contexte

L'utilisateur veut pouvoir chercher avec un "OU" (ex: `immigr* OR travail*`) et des parenthèses (ex: `(éducation OR travail) AND immigr*`). Actuellement, `build_match_query()` join tout avec `AND`, ce qui casse les opérateurs explicites. De plus, des apostrophes dans la requête crashent FTS5 (`fts5: syntax error near "'"`).

## Problèmes identifiés

1. **Crash FTS5** : `l'immigration` → apostrophe non échappée → FTS5 tente de parser une phrase non fermée → erreur
2. **Pas de support OR** : `immigr* OR travail*` → `immigr* OR* travail*` (OR cassé par split())
3. **Parenthèses non gérées** : `(éducation OR travail)` → cassées par le tokenizer
4. **Pas de protection Streamlit** : erreur FTS5 → crash de l'app Streamlit

## Fichiers à modifier

### 1. `src/lucas_v2/ui/query.py` — Réécriture de `build_match_query()`

Nouvelle logique :
1. Tokeniser l'entrée (split whitespace)
2. Identifier les tokens : termes, opérateurs (`OR`, `AND`, `NOT` — insensible casse), parenthèses (`(`, `)`)
3. Échapper les `'` dans les termes → `''`
4. Insérer `AND` par défaut entre les termes manquants :
   - entre deux termes consécutifs
   - entre `)` et un terme
   - entre un terme et `(`
   - entre `)` et `(`
5. Ignorer les opérateurs en début/fin
6. Lever `ValueError` si la requête est vide après traitement

Exemples :

| Input | Output |
|-------|--------|
| `"immigr* travail*"` | `immigr* AND travail*` |
| `"immigr* OR travail*"` | `immigr* OR travail*` |
| `"immigr* OR travail* pénalité"` | `immigr* OR travail* AND pénalité` |
| `"(éducation OR travail) AND immigr*"` | `(éducation OR travail) AND immigr*` |
| `"immigr* (éducation OR travail)"` | `immigr* AND (éducation OR travail)` |
| `"l'immigration"` | `l''immigration` |
| `"immigr* NOT chômage"` | `immigr* NOT chômage` |
| `"OR test"` | `test` |
| `"test OR"` | `test` |
| `"NOT test"` | `test` |

### 2. `src/lucas_v2/ui/db_search.py` — try/except FTS5

Ajouter `try/except ValueError` (l'erreur FTS5 remonte comme ValueError via Turso) dans les 5 fonctions qui exécutent `MATCH ?` :
- `search_videos()` → retourner `[]`
- `search_video_chunks()` → retourner `[]`
- `count_videos()` → retourner `0`
- `count_video_chunks()` → retourner `0`
- `search_chunks_by_orientation()` → retourner `[]`

Logger l'erreur avec `logging.getLogger("lucas_v2")`.

### 3. `tests/test_search_query.py` — Nouveaux cas de test

Dans `TestBuildMatchQuery` :
- `test_or_two_terms`
- `test_or_and_mixed`
- `test_parentheses_with_or`
- `test_parentheses_implicit_and`
- `test_not_operator`
- `test_single_quote_escaped`
- `test_case_insensitive_or`
- `test_or_at_start_ignored`
- `test_or_at_end_ignored`
- `test_empty_after_operators`

### 4. `src/lucas_v2/ui/app.py` — Placeholder

Ligne 318 : mettre à jour le placeholder du `st.text_input` pour suggérer la syntaxe OR :
```
"immigr* OR travail*"
```

## Pas de changement
- Pas de modification DB
- Pas de nouveau fichier
- Pas de changement dans `ingest/`

## Validation
- `uv run pytest tests/test_search_query.py -v`
- `uv run pytest tests/ -v` (tous les tests)
- `uv run pyright` (zéro erreur)
