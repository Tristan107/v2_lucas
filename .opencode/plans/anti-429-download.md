# Plan anti-429 download (base 10s)

## Contexte

Rate-limit YouTube `timedtext` throttlé par IP. Un run complet (~130 vidéos) tape le serveur en rafale toutes les 3-5s, déclenchant des 429. L'API officielle à clé (`youtube_api.py`) est négligeable (~50 appels / 10 000 unités/jour) — pas concernée.

L'objectif est d'espacer les requêtes yt-dlp et de gérer le backoff proprement pour réduire drastiquement les 429, avec un surcoût acceptable (~+25 min/run).

## Périmètre

- `src/lucas_v2/subs.py` : pacing + backoff
- `src/lucas_v2/__init__.py` : inter-vidéo 10s + inter-chaîne
- `tests/test_subs.py`, `tests/test_cli.py` : tests update
- Pas de DB, pas de SQL, pas de `youtube_api.py`

## 1. `subs.py` — pacing + backoff

### Constantes

```python
RETRY_DELAYS_S: tuple[int, ...] = (60, 120, 300)
JITTER_S: float = 5.0
```

### Nouveaux helpers (complexité ≤ 15, typés strict)

- `_is_retryable(e: Exception) -> bool` : `"429" in str(e)` uniquement. Tout le reste → raise immédiat (404, privé, quota).
- `_backoff_delay(attempt: int, exc: Exception) -> float` : parse `Retry-After: Ns` dans le message si présent, sinon `RETRY_DELAYS_S[attempt] + random.uniform(0, JITTER_S)`.

### Modifications `_base_opts()`

Ajouter :
- `extractor_retries: 2`
- `fragment_retries: 2`
- `retry_sleep: {"extractor": 30}`

Inchangés : `sleep_interval=2`, `max_sleep_interval=10`, `sleep_subtitles=5`.

### Réécrire `_run_with_retry()`

Boucle 3 tentatives :
1. `ydl.extract_info(video_url, download=True)`
2. `DownloadError` → `_is_retryable(e)` ? sinon raise immédiat
3. `time.sleep(_backoff_delay(attempt, e))`
4. Échec final (3e tentative) → `RateLimitedError` (message inchangé)

Supprimer `_retry_download()` séparé (fusionner dans la boucle). Mettre à jour les tests existants.

## 2. `__init__.py` — inter-vidéo 10s + inter-chaîne

### Constantes

```python
INTER_VIDEO_DELAY_S: int = 10  # au lieu de 3
INTER_CHANNEL_DELAY_S: int = 20
INTER_JITTER_S: float = 5.0
```

### Helper

`paced_sleep(base: int | float, jitter: float = INTER_JITTER_S) -> None` : `time.sleep(base + random.uniform(0, jitter))`.

### Modifications

- `_process_videos()` : remplacer `time.sleep(3)` par `paced_sleep(10)`.
- `ingest()` : `paced_sleep(20)` entre chaque chaîne (sauf la 1re).
- Sémantique `RateLimitedError → break` inchangée, log existant conservé.

## 3. Tests

- `tests/test_subs.py` : 429 → 3 sleeps aux bons ordres de grandeur (mock `time.sleep` + `random.uniform` → 0), `Retry-After: 45` respecté, non-429 non-retryé, persistance → `RateLimitedError`.
- `tests/test_cli.py` : pause 10s appelée entre vidéos, pause 20s entre chaînes, `break` sur `RateLimitedError` toujours OK.
- Vérif : `uv run pytest`, `uv run pyright` (mode strict), complexité ≤ 15 par fonction.

## 4. Coût validé

Run complet ~130 vidéos : **~53 min** (21,5 inter-vidéo + 5,4 jitter + 4 inter-chaîne + 15 yt-dlp + 7 réseau) vs ~28 min avant. Backoff 60/120/300 uniquement sur incident.

## Décisions ouvertes

- `_retry_download()` : fusionner dans `_run_with_retry()` (recommandé) ou garder séparé ? → Trancher en build.
