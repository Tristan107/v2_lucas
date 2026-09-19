# Fix : recherche affiche l'ancienne requête après retour d'une vidéo

## Problème

Quand l'utilisateur charge la page, lance une recherche puis tape une **nouvelle** recherche et appuie sur Entrée, le champ se réinitialise à l'ancienne requête et les résultats précédents sont réaffichés (texte et résultats).

**Scénario de repro** :
1. Charger la page.
2. Saisir une recherche (ex: "immigration"), Entrée → résultats affichés.
3. Saisir une autre recherche (ex: "économie"), Entrée.
4. Le champ revient à "immigration" et les résultats "immigration" s'affichent.

## Cause racine (confirmée dans le source Streamlit 1.63)

Le widget `st.text_input` est **sans clé explicite** (`key=None`) et son `value` est **re-computé depuis le session state à chaque rerun**.

Sans `key`, l'identité du widget est un hash de **tous ses paramètres**, y compris `value`
(`streamlit/elements/widgets/text_widgets.py:668` → `compute_and_register_element_id("text_input", ..., value=value, ...)`).

Mécanisme exact :
1. Chargement → `value=""` → **ID_A**. L'utilisateur tape "immigration", Entrée → l'état utilisateur est associé à `ID_A`.
2. Au rerun suivant, `value=` passe de `""` à `"immigration"` → Streamlit calcule un **ID_B** (nouveau widget).
3. L'état utilisateur (attaché à `ID_A`) est **jeté** → le champ affiche la nouvelle valeur par défaut, qui est l'ancienne recherche.

👉 Le reset ne dépend **pas** de la sémantique stockée (requête FTS vs saisie brute) : avec `last_raw_query` ou `last_match_query`, le bug se reproduit à l'identique. La distinction brut/FTS est donc **insuffisante**.

(Références source 1.63 : `elements/lib/utils.py:161-268` — sans `user_key`, tous les kwargs entrent dans le hash ; docstring `text_widgets.py:308-318` — *« Assigning a key stabilizes the widget's identity and preserves its state across reruns even when other parameters change »*.)

## Solution

Donner une **clé explicite** au widget et **supprimer le param `value`**.

Avec `key="search_input"`, l'ID est dérivé de la clé seule (hors `max_chars`/`validate`) → l'identité et l'état persistent à travers les reruns, quelle que soit la valeur d'affichage. `value` est ignoré dès que la clé existe dans le session state. En conséquence, `last_raw_query` et `previous_query` ne servent plus et sont supprimés.

## Fichier modifié

`src/lucas_v2/ui/app.py` (seul fichier touché)

## Changements

### 1. `_sync_search_state()` (ligne 139) — revenir à un seul paramètre

Retirer le paramètre `raw_query` (ajouté par une tentative précédente) et la ligne `last_raw_query` :

```python
def _sync_search_state(match_query: str) -> None:
    if st.session_state.get("last_match_query") != match_query:
        st.session_state["last_match_query"] = match_query
        st.session_state["video_page"] = 0
        st.session_state["selected_video_id"] = None
        st.session_state["chunk_page"] = 0
        st.session_state["owner_filter"] = None
```

### 2. Widget de recherche (lignes 469-478) — clé explicite, sans `value`

Supprimer la ligne `previous_query` et le param `value=previous_query`, ajouter `key="search_input"` :

```python
col_search, col_btn = st.columns([5, 1])
with col_search:
    raw_query = st.text_input(
        "Rechercher",
        key="search_input",
        placeholder="immigr* OR travail*",
        label_visibility="collapsed",
    )
```

### 3. Appel à `_sync_search_state` (ligne 493)

```python
_sync_search_state(match_query)
```

### Inchangé

- Ligne 464 : `match_query = str(st.session_state.get("last_match_query", ""))` — toujours utilisé pour la requête FTS de la vue détail.
- Ligne 482 : porte `if not search_clicked and not raw_query: return` — inchangée (Entrée active la recherche car `raw_query` non vide).

## Comportement après fix (trace du scénario)

1. Chargement : `search_input` absent → champ vide, pas de recherche.
2. "immigration" + Entrée → `raw_query="immigration"` → résultats + `_sync_search_state("immigration*")`. Le widget garde "immigration" (état clé).
3. "économie" + Entrée → le widget rapporte "économie" (la clé fige l'identité, plus de `value=` re-computé) → `_sync_search_state("économie*")` reset pagination -> résultats "économie".
4. Vue détail puis « Retour à la liste » → le champ réaffiche la dernière saisie brute ("immigration"), pas la FTS transformée.

## Tests

Test manuel uniquement (choix de l'utilisateur) :
1. Charger la page, rechercher "immigration" → Entrée → résultats.
2. Rechercher "économie" → Entrée → résultats "économie" s'affichent (plus "immigration").
3. Pagination et retour de vue détail conservent la saisie brute.
4. `uv run pyright` → 0 erreur.

## Risque

Très faible. Changement localisé à un seul fichier, quelques lignes. Pas de schéma, pas d'impact sur l'ingestion. Le comportement de recherche (Entrée ou clic « Rechercher », relance idempotente au rerun) est conservé.