# Plan : Ingestion transcripts YouTube → chunks phrases → Turso (SQLite)

## 1. Objectif

- Conf YAML listant des chaînes YouTube. Défaut : dernière vidéo / chaîne, paramétrable `max_videos` / `since_days`.
- Script `ingest` : discovery via **YouTube Data API v3** (`YOUTUBE_API_KEY` dans `.env`), téléchargement transcript FR via **yt-dlp** (manuel puis auto), format SRT.
- Regroupement cues en paquets phrase(s) : coupure sur `.` ou `;`, max 128 tokens, timestamp **précision seconde** (`start_s`, `end_s`).
- Stockage Turso (libsql) : metadata chaîne/vidéo + chunks.

## 2. Décisions techniques

| Sujet | Recommandation | Alternative écartée |
|---|---|---|
| Discovery chaînes/vidéos | **YouTube Data API v3** (`google-api-python-client`) : handle → channelId, uploads playlist → playlistItems → videos.list. Fallback yt-dlp `extract_flat` si quota. | yt-dlp discovery seul : fragilisé par les changements YouTube, moins de contrôle quota. |
| Sous-titres | **yt-dlp** (lib Python) : `writesubtitles=True, writeautomaticsub=True, sublangs=['fr.*','fr'], subformat='srt/best', convertsubtitles='srt', skip_download=True`. Manuel > auto. Sinon `no_subs`, skip non bloquant. | API v3 captions : nécessite OAuth, pas une API key. |
| Timestamps | **Précision seconde** : `start_s` (floor), `end_s` (ceil) en secondes entières. | Millisecondes : overkill pour V1, pas de perte. |
| Tokens | V1 : `len(text.split())` whitespace. Fonction `count_tokens()` isolée pour `tiktoken` plus tard. | tiktoken dès V1 : lourde, inutile. |
| Client Turso | `libsql-experimental` : `libsql.connect(url, auth_token)`, DB-API sqlite3. | hrana/SQLAlchemy : overkill V1. |
| Config | `pyyaml` + validation manuelle légère. | Pydantic : à envisager V2. |
| CLI | `click` existant : `lucas-v2 ingest -c channels.yaml [--dry-run] [--force]`. | Cron/systemd : hors scope V1. |

## 3. Schéma Turso

```sql
CREATE TABLE IF NOT EXISTS channels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_url TEXT NOT NULL UNIQUE,
  channel_id TEXT,
  title TEXT,
  added_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS videos (
  video_id TEXT PRIMARY KEY,
  channel_id INTEGER REFERENCES channels(id),
  channel_url TEXT NOT NULL,
  video_url TEXT NOT NULL,
  title TEXT,
  upload_date TEXT,
  duration_s INTEGER,
  sub_lang TEXT,
  sub_kind TEXT,
  status TEXT DEFAULT 'ok',
  error TEXT,
  scraped_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transcript_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
  seq_no INTEGER NOT NULL,
  start_s INTEGER NOT NULL,
  end_s INTEGER NOT NULL,
  text TEXT NOT NULL,
  tokens INTEGER NOT NULL,
  UNIQUE(video_id, seq_no)
);
CREATE INDEX IF NOT EXISTS idx_chunks_video ON transcript_chunks(video_id, seq_no);
```

Idempotence : `INSERT OR REPLACE INTO videos`, `DELETE + réinsert` chunks par `video_id`. Skip si `status='ok'` sauf `--force`.

## 4. Fichiers

```
src/lucas_v2/
  __init__.py          # CLI click → groupe ingest
  config.py            # load_channels() → list[ChannelSpec]
  youtube_api.py       # resolve_channel_id(), list_videos() via API v3
  subs.py              # download_srt() via yt-dlp, tmpdir, choix fr manuel/auto
  srt.py               # parse_srt() → cues, strip tags, conversion ms→s
  chunking.py          # chunk_cues(max_tokens=128, coupure . / ;)
  db.py                # connect() env, init_schema(), upserts
channels.yaml.example
.env.example           # 3 clés vides
tests/test_srt_chunk.py
```

### Format `channels.yaml`
```yaml
defaults:
  max_videos: 1
  since_days: null
  lang: fr
channels:
  - url: https://www.youtube.com/@NomChaine1
  - url: https://www.youtube.com/@NomChaine2
    max_videos: 3
  - url: https://www.youtube.com/@NomChaine3
    since_days: 30
```

## 5. Algorithme

### 5.1 Discovery (youtube_api.py)
1. `channels.list(part='snippet,contentDetails', forHandle=@Handle)` → `channelId`, `uploads` playlist id.
2. `playlistItems.list(playlistId, maxResults=min(max_videos,50), part='snippet,contentDetails')` → tri anti-chrono garanti.
3. Filtrer `since_days` sur `publishedAt`.
4. `videos.list(id=','.join(video_ids), part='contentDetails,snippet')` → `duration` ISO8601 → secondes.

### 5.2 Sous-titres (subs.py)
1. `YoutubeDL` avec options §2 dans tmpdir.
2. Lire fichier `.fr*.srt` généré, retourner `(srt_text, sub_lang, sub_kind)`.
3. Si aucun FR → `(None, 'no_subs', None)`.
4. Nettoyer tmpdir.

### 5.3 Parsing SRT (srt.py)
1. Regex blocs `N\nHH:MM:SS,mmm --> HH:MM:SS,mmm\ntexte\n`.
2. Strip tags `<...>`, lignes de position, unescape HTML.
3. Convertir timestamps : `parse("HH:MM:SS,mmm")` → total_secondes = `H*3600 + M*60 + S` (floor), `end_s` = ceil de la fin.
4. Retourner `list[Cue(start_s, end_s, text)]`.

### 5.4 Chunking (chunking.py)
1. Accumuler cues jusqu'à `.` ou `;` **et** non vide.
2. Si ajout prochain cue dépasse 128 tokens → flush au dernier point de coupure, sinon flush forcé 128.
3. `Chunk(start_s, end_s, text, tokens)`.

### 5.5 Orchestration (ingest CLI)
1. Pour chaque chaîne : `upsert channel` → `list_videos` → pour chaque vidéo :
   - Skip si `videos.video_id` existe avec `status='ok'` (sauf `--force`).
   - `download_srt` → `parse_srt` → `chunk_cues` → transaction `upsert video + replace chunks`.
2. Logs par vidéo : ok / no_subs / error, jamais de stop global.
3. `--dry-run` : discovery seule, pas de téléchargement/écriture.

## 6. Secrets

Ne committer ni token Turso ni clé YouTube. `.env` local (gitignoré) :
```
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...
YOUTUBE_API_KEY=...
```

## 7. Dépendances

```bash
uv add yt-dlp pyyaml libsql-experimental python-dotenv google-api-python-client
uv add --dev pytest
```

## 8. Tests

1. Unitaires SRT + chunking : fixture SRT 5-6 cues, assert regroupement, 128 tokens, `start_s`.
2. `--dry-run` 1 chaîne réelle.
3. Ingestion 1 vidéo → SELECT Turso, rejouabilité sans doublon, cas `no_subs`.

## 9. Risques

- Ordre playlist non garanti → tri date obligatoire.
- Auto-subs FR sans ponctuation → flush forcé + log `sub_kind='auto'`.
- `since_days` : `publishedAt` parfois absent en mode flat → fallback non-flat.
- Token Turso en clair dans chat → régénérer après setup.

## 10. Hors scope V1

Embeddings, recherche vectorielle, cron, multi-langues, backfill massif, interface web.
