# Lucas v2 — Ingestion transcripts YouTube → Turso

Outil d'ingestion de transcripts de vidéos YouTube : découverte des vidéos via
l'API YouTube Data v3, téléchargement des sous-titres FR via `yt-dlp`,
regroupement en paquets phrase(s) et stockage dans une base SQLite hébergée
sur Turso (libSQL).

## Fonctionnement

1. **Configuration** : fichier YAML listant les chaînes YouTube à scraper
   (`max_videos`, `since_days` paramétrables par chaîne, défaut = dernière vidéo).
2. **Discovery** (`youtube_api.py`) : résolution `@Handle` → `channelId`,
   lecture de la playlist `uploads`, récupération des métadonnées
   (`title`, `publishedAt`, `duration`).
3. **Sous-titres** (`subs.py`) : téléchargement SRT via `yt-dlp`
   (`sublangs fr.*`, manuels puis auto-générés, `skip_download`).
4. **Parsing** (`srt.py`) : cues SRT → texte nettoyé (tags/positions supprimés),
   timestamps convertis en **secondes** (`start_s`, `end_s`).
5. **Chunking** (`chunking.py`) : regroupement jusqu'à ponctuation `.` ou `;`,
   sans dépasser **128 tokens** (compteur whitespace V1, `count_tokens()` isolée
   pour brancher `tiktoken` plus tard).
6. **Stockage** (`db.py`) : 3 tables Turso — `channels`, `videos`
   (avec `status`: `ok` / `no_subs` / `error`), `transcript_chunks`
   (`video_id`, `seq_no`, `start_s`, `end_s`, `text`, `tokens`).
   Upserts idempotents, rejeu sans doublon.

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
```

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
uv run lucas-v2 ingest -c channels.yaml --force

# Aide
uv run lucas-v2 --help
uv run lucas-v2 ingest --help
```

## Tests

```bash
uv run pytest tests/ -v
```

## Structure

```
src/lucas_v2/
  __init__.py      # CLI click (ingest)
  config.py        # load_channels()
  youtube_api.py   # discovery API v3
  subs.py          # download SRT via yt-dlp
  srt.py           # parsing SRT → secondes
  chunking.py      # regroupement phrases, 128 tokens max
  db.py            # connexion Turso, schéma, upserts
tests/test_srt_chunk.py
```

Plan détaillé : `.opencode/plans/yt-dlp-transcripts-turso.md`
