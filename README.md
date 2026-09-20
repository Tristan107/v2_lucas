# Lucas v2 — Veille politique YouTube

Outil de veille politique pour Lucas et ses amis : collecte automatique
des transcripts de vidéos YouTube de chaînes politiques françaises,
rendus interrogeables via une interface web.

Créé en vue de l'élection présidentielle de 2027, Lucas v2 permet de
suivre et chercher dans le discours politique diffusé sur YouTube.

## Fonctionnement

1. **Chaînes** : un fichier YAML définit les chaînes YouTube à suivre
2. **Collecte** : les vidéos et sous-titres français sont récupérés automatiquement
3. **Indexation** : les transcripts sont découpés en segments et stockés dans une base de données
4. **Recherche** : une interface web permet de chercher dans tous les transcripts avec liens YouTube

## Prérequis

- Python ≥ 3.11, [uv](https://docs.astral.sh/uv/)
- Clé **YouTube Data API v3** (Google Cloud Console → activer l'API → clé)
- Base **Turso** + token (`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`)

## Installation

```bash
uv sync
```

## Configuration

```bash
cp .env.example .env        # puis renseigner les 3 clés
cp channels.yaml.example channels.yaml   # puis lister vos chaînes
```

`.env` (jamais commité) :

```
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...
YOUTUBE_API_KEY=...
# Optionnel : cookies YouTube (compte secondaire) contre les 429 yt-dlp
YOUTUBE_COOKIES_FILE=/home/tristan/.config/lucas/cookies.txt
```

### Cookies YouTube (anti-429, optionnel)

Sans cookies, l'ingestion fonctionne en mode anonyme. En cas de 429
répétés, configurer un fichier cookies depuis un **compte secondaire**
(jamais le compte principal) :

1. Installer l'extension « Get cookies.txt LOCALLY » dans le navigateur
2. Se connecter à YouTube avec le compte secondaire
3. Exporter les cookies de `youtube.com` au format Netscape
4. Sauvegarder le fichier hors repo, ex. `~/.config/lucas/cookies.txt`
5. Protéger : `chmod 600 ~/.config/lucas/cookies.txt`
6. Renseigner `YOUTUBE_COOKIES_FILE` dans `.env` (voir ci-dessus)

Si la variable est absente ou pointe vers un fichier inexistant,
l'ingestion continue en mode anonyme avec un warning. Si les 429
persistent malgré des cookies configurés, ils ont probablement expiré :
ré-exporter le fichier.

`channels.yaml` :

```yaml
defaults:
  max_videos: 1
  since_days: null
channels:
  - url: https://www.youtube.com/@NomChaine
  - url: https://www.youtube.com/@AutreChaine
    max_videos: 3
  - url: https://www.youtube.com/@Troisieme
    since_days: 30
```

## Lancement

```bash
# Lister les vidéos ciblées sans télécharger ni écrire
uv run lucas-v2 ingest -c channels.yaml --dry-run

# Ingestion réelle
uv run lucas-v2 ingest -c channels.yaml

# Forcer le re-scrap des vidéos déjà en base
uv run lucas-v2 ingest -c channels.yaml --force-all

# Re-télécharger une vidéo spécifique par URL
uv run lucas-v2 ingest -c channels.yaml --url "https://www.youtube.com/watch?v=VIDEO_ID"

# Aide
uv run lucas-v2 --help
uv run lucas-v2 ingest --help
```

## Recherche Streamlit (IHM)

Interface web pour rechercher dans les transcripts ingérés.

```bash
uv run streamlit run streamlit_app.py
```

**Fonctionnalités :**
- Champ libre : `travail*`, `immigr* travail*` (AND entre termes, wildcards `*`)
- Liste des vidéos triées par date décroissante avec compteur de mentions
- Panneau dépliant par vidéo : chunks matchés avec gras natif `**...**`
- Timestamp `hh:mm:ss` cliquable → ouvre YouTube au bon moment
- Pagination « Voir plus » (+10 chunks)

## Tests

```bash
uv run pytest tests/ -v
```
