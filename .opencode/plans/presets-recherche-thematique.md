# Presets de recherche thématique (pills au-dessus de la barre de recherche)

## Objectif

Ajouter, au-dessus de la barre de recherche de la page YouTube (vue liste), une rangée de
6 boutons-pills thématiques. Un clic remplit `st.text_input("search_input")` avec la
requête FTS brute pré-définie **et** lance immédiatement la recherche.

Décisions validées avec l'utilisateur :
- Composant : `st.button` natifs (`type="secondary"` / `primary` si actif), dans une rangée de colonnes.
- Les presets vivent dans un module dédié `ui/presets.py` (dataclass frozen).
- Correction racine de `build_match_query()` pour préserver les phrases entre guillemets.
- Requêtes gardées textuellement telles que fournies, SAUF :
  - `"transition écolo*"` → `"transition écolo"*` (le `*` dans une phrase entre guillemets est silencieusement mort ; le préfixe de phrase fonctionne : vérifié sur `"transition écologique"`).
  - Doublon `"centre de rétention administrative"` supprimé dans Immigration.
- Re-clic sur un preset déjà actif : retour page 0 + filtre candidat vidé (pas de no-op).
- Pills rendues en vue liste uniquement, toujours au-dessus de la barre.

## Contexte factuel (vérifié)

- `build_match_query(raw)` (dans `ui/query.py`) transforme l'entrée utilisateur en requête FTS5.
  Bug actuel : le `split()` sur espaces découpe `"sécurité sociale"` en `"sécurité` + `sociale"`,
  puis l'insertion d'`AND` implicite produit `"sécurité AND sociale"` → requête FTS invalide/vide.
  Même bug pour tous les presets à phrases.
- `st.text_input(key="search_input")` s'initialise depuis `st.session_state["search_input"]`
  au rendu. Comme les pills sont rendues AVANT la barre, poser la clé au clic suffit ;
  le garde `if not search_clicked and not raw_query: return` laisse passer une requête non vide.
  Pas de `st.rerun()` ni de flag supplémentaire.
- FTS5 (`unicode61 remove_diacritics 2`) gère accents et majuscules (vérifié : `École*` matche
  `école`, `OQTF` matche `oqtf`). Le préfixe de phrase `"sans-papier"*` et le préfixe
  mono-token `"Frontière*"` fonctionnent.
- Tests FTS : `tests/test_search_db.py` et `tests/test_db.py` utilisent
  `libsql.connect(":memory:")` + `init_schema(conn)` → FTS5 réel disponible en test.

## Modifications

### 1. Nouveau module `src/lucas_v2/ui/presets.py`

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemePreset:
    label: str
    raw_query: str


PRESETS: tuple[ThemePreset, ...] = (
    ThemePreset(
        label="Éducation",
        raw_query="éducat* OR école* OR enseign* OR apprenti* OR formation* OR scola* OR pédagog* OR profess* OR diplome*",
    ),
    ThemePreset(
        label="Santé",
        raw_query="Santé* OR Hôpita* OR médecine* OR médica* OR EHPAD* OR CHU* OR Samu OR Soignant* OR infirmier* OR \"sécurité sociale\"",
    ),
    ThemePreset(
        label="Immigration",
        raw_query="immigr* OR migr* OR clandestin* OR passeur* OR \"sans-papier\"* OR \"carte de séjour\" OR \"titre de séjour\" OR OQTF OR \"reconduite à la frontière\" OR \"centre de rétention administrative\" OR \"Droit du sol\" OR \"Droit du sang\" OR \"préférence nationale\" OR \"Schengen\" OR \"asile\" OR \"Frontière*\"",
    ),
    ThemePreset(
        label="Économie",
        raw_query="budget* OR dette* OR impot* OR deficit* OR Économi*",
    ),
    ThemePreset(
        label="Écologie",
        raw_query="\"Mix énergétique\" OR nucleaire* OR écolo* OR \"transition écologique" OR \"voiture électrique\" OR \"voitures électriques\"",
    ),
    ThemePreset(
        label="Défense",
        raw_query="Défense OR Russ* OR pologn* OR Ukrain* OR dron* OR bomb* OR missil* OR geopolitiqu*",
    ),
)
```

Conventions : `from __future__ import annotations`, dataclass `frozen=True, slots=True`
(identique aux dataclasses de `ui/db_search.py`), commentaires/libellés en français.
L'ordre du tuple = ordre d'affichage.

### 2. `src/lucas_v2/ui/query.py` — corriger `build_match_query()`

Remplacer le découpage `raw.split()` par un tokenizer qui traite une région entre
guillemets (optionnellement suivie de `*`) comme une seule unité.

Nouvelle fonction interne :

```python
def _tokenize(raw: str) -> list[str]:
    """Découpe l'entrée en tokens bruts en préservant les phrases entre guillemets.

    ``'"sécurité sociale" OR école*'`` → ``['"sécurité sociale"', 'OR', 'école*']``.
    Un ``*`` directement après le guillemet fermant est absorbé dans le token
    (préfixe de phrase : ``"transition écolo"*``).
    Une apostrophe est remplacée par un espace (comportement existant).
    """
```

Règles du scanner (parcours caractère par caractère, en ignorant les espaces) :
- Si le caractère est `"` (guillemet ouvrant) :
  - lire jusqu'au guillemet fermant suivant ; si absent, consommer jusqu'à la fin ;
  - si le caractère suivant est `*`, l'absorber ;
  - remplacer les `'` par des espaces dans le contenu ;
  - émettre `"<contenu>"` (ou `"<contenu>"*`), toujours classé TERM.
- Si `(` ou `)` : émettre tel quel (PAREN).
- Sinon : lire la suite de caractères non-espaces (comme `split()`), puis :
  - si `upper()` ∈ {`OR`, `AND`, `NOT`} → OP ;
  - sinon → TERM avec remplacement des `'` par des espaces.
  - un token en toute lettre `"and"` entre guillemets reste un TERM (il est produit par le
    cas guillemet, pas par ce cas).

Le reste de `build_match_query` (classification, suppression des OP en tête/fin,
insertion d'`AND` entre tokens adjacents non-OP, `ValueError` si vide) reste identique,
mais itère sur les tokens du tokenizer au lieu de `raw.split()`.

Comportements invariants à conserver (couverts par les tests existants) :
- `"immigr* travail*"` → `"immigr* AND travail*"`
- `"l'immigration"` → `"l immigration"`
- `"(a OR b) (c OR d)"` → `"(a OR b) AND (c OR d)"`
- `"OR test"` → `"test"`, `"test OR"` → `"test"`, `"OR AND NOT"` → ValueError

Nouveaux comportements (à tester) :
- `'"sécurité sociale"'` → `'"sécurité sociale"'`
- `'"Mix énergétique" OR nucleaire*'` → inchangé
- `'"centre de rétention administrative" OR OQTF'` → inchangé
- `'"sans-papier"*'` → inchangé ; `'"transition écolo"*'` → inchangé
- `'"a b" "c d"'` → `'"a b" AND "c d"'`
- `'"AND" test'` → `'"AND" AND test'` (AND entre guillemets reste un terme)
- `'"l\'école"'` → `'"l école"'`

Contrainte : garder la complexité cognitive ≤ 15 par fonction (éclater en petits helpers
si besoin, ex. `_scan_quoted`).

### 3. `src/lucas_v2/ui/app.py` — rendu des pills

Imports : ajouter `PRESETS` (et éventuellement `ThemePreset` pour le typage) depuis
`lucas_v2.ui.presets`.

Nouvelle fonction :

```python
def _render_preset_row() -> None:
    """Affiche les pills de recherche thématique au-dessus de la barre de recherche."""
    current = st.session_state.get("last_match_query")
    cols = st.columns(len(PRESETS))
    for i, preset in enumerate(PRESETS):
        with cols[i]:
            match_query = build_match_query(preset.raw_query)
            active = match_query == current
            if st.button(
                preset.label,
                key=f"preset_{i}",
                type="primary" if active else "secondary",
                width="stretch",
                help=preset.raw_query,
            ):
                st.session_state["search_input"] = preset.raw_query
                st.session_state["video_page"] = 0
                st.session_state["chunk_page"] = 0
                st.session_state["owner_filter"] = None
```

Notes d'implémentation :
- `key=f"preset_{i}"` stable (pas le label : libellés uniques mais index plus sûr).
- `build_match_query(preset.raw_query)` ne peut pas lever ici (presets statiques,
  validés par les tests) ; pas de try/except nécessaire.
- `_sync_search_state` (appelé plus bas dans le flux de recherche) resettra
  pagination/filtre si la requête change ; le re-clic à l'identique est géré par les
  assignations explicites ci-dessus (Q6-A : retour page 0 + filtre vidé).
- Le clic ne déclenche pas `st.rerun()` : la recherche se lance dans le même passage
  (le `text_input` rendu en dessous lit la nouvelle valeur de session).

Dans `render_youtube_page()`, dans la branche vue liste (`selected` est `None`),
juste avant `col_search, col_btn = st.columns([5, 1])` :

```python
    _render_preset_row()
```

Soit le flux final de la vue liste :
1. `_render_preset_row()`
2. `col_search, col_btn` (barre + bouton Rechercher)
3. garde / `build_match_query` / `_sync_search_state` / rendu des résultats

La vue détail (`selected` non vide) ne rend pas les pills (pas de barre de recherche).

### 4. Tests

**`tests/test_search_query.py`** — étendre `TestBuildMatchQuery` avec les nouveaux cas
(listés en §2, « Nouveaux comportements »). Les tests existants de la classe doivent tous
rester verts.

**Nouveau fichier `tests/test_presets.py`** :
- `test_presets_valid_match_queries` : pour chaque `preset` de `PRESETS`,
  `build_match_query(preset.raw_query)` ne lève pas et renvoie une chaîne non vide.
- `test_presets_snapshots` : verrouille les `raw_query` exacts (notamment :
  `"transition écolo"*` présent dans Écologie ; `"centre de rétention administrative"`
  apparaît exactement une fois dans Immigration). Utiliser un dict `{label: raw_query}`
  attendu.
- Test d'intégration FTS5 (reprendre le pattern de `tests/test_search_db.py`) :
  - `libsql.connect(":memory:")` + `init_schema(conn)` ; insérer un corpus français
    couvrant les 6 thèmes (ex. : « l éducation dans les écoles », « la sécurité sociale
    et le samu », « les immigrés sans papier à la frontière », « le budget et l économie »,
    « la transition écologique et le nucléaire », « la défense, la Russie et l Ukraine »).
  - Pour chaque preset : `count_videos(conn, build_match_query(preset.raw_query)) >= 1`.
  - Test de régression ciblé : la requête Écologie matche « la transition écologique »
    (valide la correction `"transition écolo"*`).

### 5. Doc (optionnel, recommandé)

Ajouter `ui/presets.py` au tableau de référence des fichiers dans `AGENTS.md` (§8).
Ajouter éventuellement une ligne dans `AGENTS.md` §11 pour documenter les pills.

## Vérification fonctionnelle

1. `uv run pyright` → zéro erreur.
2. `uv run pytest tests/ -v` → tout vert (anciens + nouveaux tests).
3. Manuel (`uv run streamlit run streamlit_app.py`) :
   - Les 6 pills s'affichent au-dessus de la barre en vue liste ; tooltip au survol
     montrant la requête brute.
   - Clic « Santé » : le champ se remplit avec la requête brute, la recherche se lance,
     le pill Santé passe en `primary`.
   - Clic « Écologie » : résultats contenant « transition écologique » (régression du
     terme corrigé).
   - Recherche manuelle `"sécurité sociale"` → matche (avant : cassée silencieusement).
   - Re-clic « Santé » alors que Santé est actif et page > 0 → retour page 0 / filtre vidé.
   - Vue détail d'une vidéo : pas de pills.
   - Pas de régression sur `build_match_query` (`"immigr* travail*"` etc.).

## Non-fais partie du périmètre

- Presets éditables à l'exécution / en config YAML (rejeté : module code uniquement).
- Page Sondages (sans rapport).
- CSS customs pour styler les pills (boutons natifs secondaires suffisent).