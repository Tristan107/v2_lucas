# Plan : Déployer l'UI Streamlit sur Streamlit Cloud

## Objectif

Publier l'interface Streamlit de Lucas v2 sur Streamlit Community Cloud pour y accéder depuis n'importe quel appareil.

## Contexte

L'application est actuellement lancée en local via `uv run streamlit run streamlit_app.py`. Elle dépend d'une base Turso (managed), et n'a besoin que de l'UI (pas de l'ingestion) côté cloud.

## Blocker identifié

**`libsql-experimental` n'a pas de wheel Python 3.14** (utilisé par défaut sur Streamlit Cloud). Solution : migrer vers le package successeur `libsql` (API identique, wheels cp314 disponibles).

---

## Étapes d'implémentation

### Étape 1 — Migrer `libsql-experimental` → `libsql`

**Fichier : `pyproject.toml`**

Remplacer la ligne 13 :
```
"libsql-experimental>=0.0.55",
```
par :
```
"libsql>=0.1.11",
```

**Fichier : `src/lucas_v2/db/connection.py`**

Remplacer la ligne 7 :
```python
import libsql_experimental as libsql  # pyright: ignore[reportMissingModuleSource]
```
par :
```python
import libsql as libsql  # pyright: ignore[reportMissingModuleSource]
```

> Aucun autre fichier n'importe `libsql_experimental`.

---

### Étape 2 — Créer `requirements.txt` pour Streamlit Cloud

Créer un fichier `requirements.txt` à la racine du repo avec uniquement les dépendances de l'UI (sans `yt-dlp`, `transformers`, `google-api-python-client` qui ne servent que l'ingestion) :

```
click>=8.5.0
libsql>=0.1.11
pandas>=3.0.5
python-dotenv>=1.2.3
pyyaml>=6.0.3
requests>=2.34.2
streamlit>=1.35
```

> Streamlit Cloud utilise ce fichier pour installer les dépendances. `streamlit` est déjà installé par la plateforme, mais l'inclure ne pose pas de problème.

---

### Étape 3 — Adapter le chargement des secrets

**Fichier : `src/lucas_v2/ui/app.py`**

Modifier `_get_conn()` (lignes 28-31) pour gérer l'absence de fichier `.env` (normal sur Streamlit Cloud) :

```python
@st.cache_resource
def _get_conn() -> Any:
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)
    return connect()
```

> Sur Streamlit Cloud, les secrets sont injectés comme variables d'environnement par la plateforme. `os.environ["TURSO_DATABASE_URL"]` dans `connection.py` fonctionnera directement. Le `load_dotenv` n'est nécessaire qu'en local.

---

### Étape 4 — Mettre à jour `uv.lock`

Exécuter :
```bash
uv lock
```

> Pour régénérer le lockfile avec `libsql` au lieu de `libsql-experimental`.

---

### Étape 5 — Vérifications avant push

1. **Tests locaux** : `uv run pytest tests/ -v` — s'assurer que rien ne casse
2. **Type checking** : `uv run pyright` — zéro erreur
3. **Vérifier que `channels.yaml` est dans le repo** (déjà le cas)
4. **Vérifier que `.streamlit/config.toml` est dans le repo** (déjà le cas)

---

### Étape 6 — Déploiement sur Streamlit Cloud

1. Push le code sur GitHub (branche `main`)
2. Aller sur [share.streamlit.io](https://share.streamlit.io)
3. Cliquer "New app" → sélectionner le repo, la branche `main`, le fichier `streamlit_app.py`
4. Cliquer "Advanced settings" → "Secrets" et coller :
   ```toml
   TURSO_DATABASE_URL = "libsql://..."
   TURSO_AUTH_TOKEN = "..."
   YOUTUBE_API_KEY = "..."
   ```
5. Cliquer "Deploy"

---

## Fichiers modifiés

| Fichier | Action |
|---------|--------|
| `pyproject.toml` | Modifier la dépendance `libsql-experimental` → `libsql` |
| `src/lucas_v2/db/connection.py` | Modifier l'import `libsql_experimental` → `libsql` |
| `src/lucas_v2/ui/app.py` | Rendre le `load_dotenv` conditionnel (vérifier `.env` existe) |
| `requirements.txt` | **Créer** — dépendances minimales UI pour Streamlit Cloud |
| `uv.lock` | Régénérer via `uv lock` |

---

## Tests fonctionnels

### Test 1 — Migration libsql
```bash
uv run python -c "import libsql; print(libsql.__version__)"
```
Doit afficher la version sans erreur.

### Test 2 — Connexion Turso
```bash
uv run python -c "from lucas_v2.db.connection import connect; conn = connect(); print('OK')"
```
Doit se connecter à Turso sans erreur.

### Test 3 — Tests unitaires
```bash
uv run pytest tests/ -v
```
Tous les tests doivent passer.

### Test 4 — Streamlit local
```bash
uv run streamlit run streamlit_app.py
```
Vérifier que la page d'accueil s'affiche et que la recherche YouTube fonctionne.

### Test 5 — Déploiement cloud
Après déploiement, vérifier sur l'URL Streamlit Cloud que :
- La page d'accueil s'affiche avec les cartes YouTube et Sondages
- La recherche retourne des résultats
- Les liens YouTube fonctionnent
