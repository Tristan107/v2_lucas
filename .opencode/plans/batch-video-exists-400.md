# Plan : Injection client API + batch existence DB

## Objectif

Accélérer le `--dry-run` (et l'ingest) de ~15 s/chaîne à ~2-4 s/chaîne pour 400 vidéos max, en :
1. Réduisant les `build()` de 2N à 1 par run (injection client).
2. Remplaçant N appels `video_exists()` Turso séquentiels par 1 seule requête `WHERE IN`.

## Contexte (code lu)

- `ingest()` (`__init__.py:230-246`) : boucle par chaîne → `resolve_channel()` → `fetch_videos()` → `process_videos()`.
- Chaque étage recrée son client : `resolve_channel_id():83` et `list_videos():202` appellent `get_client()` → `build("youtube","v3")` sans cache = 2 discovery-doc (~500 Ko, 0,5-1,5 s) par chaîne.
- `process_videos():147` fait `video_exists()` (`db.py:164-169` : `SELECT 1 ... WHERE youtube_str_id=?`) 1x par vidéo, séquentiel, même en `--dry-run`. Via Turso distant = 1 round-trip HTTPS/vidéo = 10-25 s pour 150-400 vidéos.
- Contrainte YouTube : `playlistItems(maxResults=50)` + `videos.list(id=..., max 50)` → impossible en 1 seule requête API. Min 8+8=16 requêtes séquentielles pour 400 vidéos (incompressible).
- `UNIQUE` sur `youtube_str_id` crée déjà un index SQLite (`schema.sql:13`). Pas de migration nécessaire.

## Lot A — Injection client API (rétro-compatible)

### Fichiers : `youtube_api.py`, `__init__.py`

### `youtube_api.py`

- `get_client()` : inchangé, garder tel quel (factory lazy).
- `resolve_channel_id(url_or_handle, youtube=None)` : ajouter param optionnel. Si `None` → `youtube = get_client()`.
- `list_videos(channel_id, max_videos=None, since_days=None, youtube=None)` : idem.
- `fetch_and_download_single()` (`__init__.py:314`) : déjà un param `youtube` implicite via `get_client()` local → propager.
- Ne pas toucher à `_resolve_by_id`, `_resolve_by_handle`, `_resolve_by_search` (restent privés avec `youtube` passé en premier arg).

### `__init__.py`

- `ingest()` : créer `youtube = get_client()` **1x après `connect()`**, passer à `resolve_channel(spec, conn, youtube=youtube)` et `fetch_videos(channel_id, spec, youtube=youtube)`.
- `resolve_channel(spec, conn, youtube=None)` : propager à `resolve_channel_id(spec.url, youtube=youtube)`.
- `fetch_videos(channel_id, spec, youtube=None)` : propager à `list_videos(channel_id, spec.max_videos, spec.since_days, youtube=youtube)`.
- `ingest_single_video()` : créer 1 client local et le propager de même.

### Tests existants

- Les mocks `@patch("lucas_v2.youtube_api.get_client")` restent verts car fallback `None` → `get_client()`.
- Ajouter 1 test par fonction pour vérifier que `youtube` passé = `get_client` non appelé (spy/mock).

## Lot B — Batch existence DB (gros gain)

### Fichier : `db.py`

Nouvelle fonction :

```python
def fetch_existing_ids(conn: Any, ids: list[str]) -> set[str]:
    """Batch lookup : retourne l'ensemble des youtube_str_id déjà en table."""
    if not ids:
        return set()
    seen: set[str] = set()
    unique: list[str] = list(set(ids))  # dedupe
    for start in range(0, len(unique), _CHUNK_BATCH):
        chunk = unique[start:start + _CHUNK_BATCH]
        placeholders = ",".join(["?"] * len(chunk))
        rows = conn.execute(
            f"SELECT youtube_str_id FROM video WHERE youtube_str_id IN ({placeholders})",
            tuple(chunk),
        ).fetchall()
        seen.update(r[0] for r in rows)
    return seen
```

- Reuse `_CHUNK_BATCH = 500` déjà existant (`db.py:136`).
- Typage fort, complexité < 15, passe par `DbConn.execute` (reconnect Turso inchangé).

### `__init__.py` — `process_videos()`

- **Avant la boucle** : `existing_ids = fetch_existing_ids(conn, [str(v["youtube_str_id"]) for v in videos])`.
- Dans la boucle : `is_new = vid_yt_id not in existing_ids` (remplace `video_exists(conn, vid_yt_id)`).
- Supprimer l'import `video_exists` dans la fonction (plus besoin).
- Garder `video_exists()` dans `db.py` (compat, tests, usage externe).

### Tests

- `test_db.py` : tests unitaires `fetch_existing_ids` :
  - `[]` → `set()`
  - 1 id existant → `{id}`
  - 1 id inexistant → `set()`
  - Doublons → dédupliqué
  - 400 ids → 1 chunk, tous retournés
  - Mix existant/inexistant
- `test_cli.py` : tests `process_videos` avec `fetch_existing_ids` mocké.
  - Dry-run new, dry-run existing, force, force_id.

## Résultats attendus

| Scénario | Avant | Après |
|----------|-------|-------|
| `--dry-run`, 400 vidéos, 1 chaîne | ~15 s | ~2-4 s |
| `ingest`, 400 vidéos, 1 chaîne, 100 existantes | ~15 s listing + ~10 s sleep/download | ~2 s listing + ~10 s sleep/download |
| Nombre de builds par chaîne | 2 | 1 |
| Nombre de SELECT Turso pour existence | N (séquentiel) | 1 batch |

## Points de non-régression

- `paced_sleep(i>0)` : ne pas changer l'index de la boucle, garder l'ancien comportement exact.
- Logs `>> titre (id)` + `Déjà scrapée, skip` : identiques.
- `dry-run summary` : identique.
- `yt-dlp` non appelé si vidéo existante : inchangé.
- `AGENTS.md` : pas de migration SQL, `UNIQUE` déjà indexe.

## Fichiers modifiés

| Fichier | Changement |
|---------|------------|
| `src/lucas_v2/youtube_api.py` | Param `youtube=None` sur `resolve_channel_id`, `list_videos` |
| `src/lucas_v2/__init__.py` | Client unique `ingest()`, injection, `fetch_existing_ids` dans `process_videos` |
| `src/lucas_v2/db.py` | +`fetch_existing_ids()` |
| `tests/test_db.py` | +tests `fetch_existing_ids` |
| `tests/test_cli.py` | +tests injection client, batch existence |
| `tests/test_youtube_api.py` | +tests param `youtube` passé |

## Validation

1. `pytest` tous verts.
2. `pyright` zéro warning/erreur.
3. Cognitive complexity ≤ 15 partout.
4. `time ... --dry-run` sur chaîne test 365j : confirmer ~15 s → ~3 s.
