# Plan : Tri alpha par nom de famille du selectbox candidat

## Objectif

Trier la liste de sélection des candidats (`st.selectbox` dans `_render_channel_breakdown`) par nom de famille au format `"Nom (Prénom)"`. Exemples : `"Bardella (Jordan)"`, `"De Villepin (Dominique)"`.

## Contexte

- **Fichier principal** : `src/lucas_v2/ui/app.py`, fonction `_render_channel_breakdown()` (lignes 251-310)
- Les `owner` en BDD sont au format `"Prénom Nom"` (ex. `"Jordan Bardella"`)
- Le `owner_filter` SQL doit utiliser la valeur brute, pas le format d'affichage
- Le graphique à barres reste dans son ordre actuel (tri par ratio `matched/total`)

## Spécifications techniques

### 1. Fonction utilitaire de parsing de nom

Ajouter dans `src/lucas_v2/ui/app.py` une fonction pure :

```python
def _parse_owner_name(raw: str) -> str:
    """Convertit 'Jordan Bardella' en 'Bardella (Jordan)' pour l'affichage."""
    parts = raw.strip().split()
    if len(parts) < 2:
        return raw  # fallback : nom à un seul mot
    last = parts[-1]
    first = " ".join(parts[:-1])
    return f"{last} ({first})"
```

Cas couverts :
- `"Jordan Bardella"` → `"Bardella (Jordan)"`
- `"Dominique de Villepin"` → `"De Villepin (Dominique)"` (la particule reste avec le prénom car `parts[-1]` = `"Villepin"`)
- `"Marine Le Pen"` → `"Le Pen (Marine)"` — **ATTENTION** : avec cette logique, `"Marine Le Pen"` donnerait `"Pen (Marine Le)"`. Il faut un traitement spécifique.

### 2. Gestion des particules nobles

Le cas `"Marine Le Pen"` nécessite une liste de particules connues :

```python
_PARTICLES = {"de", "du", "des", "de la", "du"}
```

**Approche recommandée** : inverser la logique — chercher le dernier espace qui sépare un mot sans particule du reste. Ou plus simplement : pour les noms composés avec particules, extraire le dernier mot significatif comme nom de famille.

Approche finale (couvre tous les cas du fichier `channels.yaml`) :

```python
def _parse_owner_name(raw: str) -> str:
    """Convertit 'Jordan Bardella' en 'Bardella (Jordan)'."""
    particles = {"de", "du", "des"}
    parts = raw.strip().split()
    if len(parts) < 2:
        return raw
    # Reculer au-delà des particules pour trouver le vrai nom de famille
    idx = len(parts) - 1
    while idx > 0 and parts[idx - 1].lower() in particles:
        idx -= 1
    last_name = " ".join(parts[idx:])  # ex. "de Villepin", "Le Pen"
    first_name = " ".join(parts[:idx])  # ex. "Dominique", "Marine"
    return f"{last_name} ({first_name})"
```

Vérification sur tous les `owner` du `channels.yaml` :

| raw | attendu |
|-----|---------|
| `Nathalie Arthaud` | `Arthaud (Nathalie)` |
| `Jean-Luc Mélenchon` | `Mélenchon (Jean-Luc)` |
| `Fabien Roussel` | `Roussel (Fabien)` |
| `Marine Tondelier` | `Tondelier (Marine)` |
| `Olivier Faure` | `Faure (Olivier)` |
| `Raphaël Glucksmann` | `Glucksmann (Raphaël)` |
| `Olivier Faure PS` | `PS Faure (Olivier)` — **problème** |

**Problème détecté** : `"Olivier Faure PS"` → avec la logique ci-dessus, `PS` serait le dernier mot → `"PS (Olivier Faure)"`. Ce n'est pas souhaitable.

**Solution** : pour le cas `"Olivier Faure PS"`, on veut `"Faure PS (Olivier)"`. Il faut que `"PS"` reste avec le nom de famille. La logique actuelle fonctionne : `parts[-1]` = `"PS"`, pas une particule → `last_name = "PS"`, `first_name = "Olivier Faure"` → `"PS (Olivier Faure)"`. Ce n'est pas idéal.

**Solution alternative plus robuste** : ne pas essayer de parser automatiquement. Utiliser un **dictionnaire de display names** défini dans le code, ou (mieux) ajouter un champ `display_name` dans `channels.yaml`.

→ **Recommandation finale** : ajouter un champ optionnel `display_name` dans `channels.yaml` et le utiliser quand présent, sinon fallback sur le parsing automatique. C'est le plus propre et évite les edge cases.

### 3. Modification de `channels.yaml`

Ajouter un champ `display_name` optionnel pour les cas ambigus :

```yaml
  - url: "https://www.youtube.com/@partisocialiste"
    owner: "Olivier Faure PS"
    display_name: "Faure PS (Olivier)"
    orientation: "centre gauche"
```

Pour tous les autres (pas de ambiguïté), le parsing automatique suffit.

### 4. Modification du ChannelSpec (optionnel)

Dans `src/lucas_v2/ingest/config.py`, ajouter `display_name: str | None = None` au dataclass `ChannelSpec` et le parser depuis le YAML. **Mais** : le `display_name` n'est utilisé que dans l'UI, pas dans l'ingestion.

**Alternative plus légère** : ne pas toucher à l'ingestion. Le `display_name` est utilisé uniquement dans `_render_channel_breakdown()` en lisant directement le YAML ou en le stockant dans un dict en session state.

**Décision** : la plus simple est de stocker un mapping `owner → display_name` dans `st.session_state` lors du rendu, construit à partir des données déjà disponibles dans `stats`. On peut ajouter un champ `display_name` dans `ChannelSpec` et le propager jusqu'à `ChannelStats`.

### 5. Plan d'implémentation détaillé

#### Étape 1 : Ajouter `display_name` au dataclass `ChannelSpec`
- Fichier : `src/lucas_v2/ingest/config.py`
- Ajouter `display_name: str | None = None` après `owner`
- Parser `ch.get("display_name", d_display_name)` dans `from_dict()`

#### Étape 2 : Propager `display_name` dans l'upsert SQL
- Fichier : `src/lucas_v2/db/schema.sql`
- Ajouter colonne `display_name TEXT` à la table `channel`
- Fichier : `src/lucas_v2/db/operations.py`
- Ajouter `display_name` dans l'upsert du channel
- Script one-shot SQL pour ajouter la colonne (si DB existante)

#### Étape 3 : Ajouter `display_name` à `ChannelStats`
- Fichier : `src/lucas_v2/ui/db_search.py`
- Ajouter `display_name: str | None` au dataclass `ChannelStats`
- Modifier `search_chunks_by_channel()` pour récupérer `c.display_name`

#### Étape 4 : Modifier `_render_channel_breakdown()` dans `app.py`
- Construire le mapping `owner → display_name` ( depuis `stats` ou `st.session_state`)
- Ajouter la fonction `_parse_owner_name()` (fallback quand `display_name` est None)
- Construire les options avec format `"Nom (Prénom)"` + tri par nom de famille
- Mapper le selectbox value vers le `owner` brut pour le filtre SQL

#### Étape 5 : Script one-shot SQL pour migration DB existante
```sql
ALTER TABLE channel ADD COLUMN display_name TEXT;
```

#### Étape 6 : Mettre à jour `channels.yaml`
- Ajouter `display_name: "Faure PS (Olivier)"` pour la chaîne PS

#### Étape 7 : Tests
- Test unitaire de `_parse_owner_name()` avec tous les cas
- Test que le selectbox est trié (vérifier l'ordre des options)

### 6. Fichiers modifiés

| Fichier | Modification |
|---------|-------------|
| `src/lucas_v2/ingest/config.py` | Ajout `display_name` au ChannelSpec |
| `src/lucas_v2/db/schema.sql` | Ajout colonne `display_name` |
| `src/lucas_v2/db/operations.py` | Upsert avec `display_name` |
| `src/lucas_v2/ui/db_search.py` | `ChannelStats.display_name` + SELECT |
| `src/lucas_v2/ui/app.py` | `_parse_owner_name()`, tri selectbox, mapping |
| `channels.yaml` | Ajout `display_name` pour Olivier Faure PS |
| `tests/` | Tests unitaires parsing + tri |

### 7. Validation fonctionnelle

1. Lancer `uv run streamlit run streamlit_app.py`
2. Faire une recherche (ex. `"immigration"`)
3. Vérifier que le selectbox affiche les candidats triés : `Arthaud (Nathalie)`, `Attal (Gabriel)`, `Bardella (Jordan)`, ...
4. Vérifier que `"Olivier Faure PS"` s'affiche `"Faure PS (Olivier)"`
5. Sélectionner un candidat → les résultats se filtrent correctement
6. Vérifier que le graphique à barres n'est pas affecté par le tri
7. `uv run pytest tests/ -v`
8. `uv run pyright`
