# Plan : 6x HTTP 429 consécutifs = arrêt complet de l'ingestion

## 1. Compréhension du contexte existant

### 1.1 Code actuel (lu et vérifié)

- `src/lucas_v2/subs.py:16-35` :
  - `RateLimitedError` = 429 persistant, docstring : « ne pas insérer en BDD, retry automatique au prochain run ».
  - `RETRY_DELAYS_S = (60, 120, 300)`, `JITTER_S = 5.0`, `_SLEEP_SUBTITLES_S = 5`.
  - `is_retryable(e)` = `"429" in str(e)`.
  - `backoff_delay(attempt, exc)` = valeur `Retry-After: N` si présente, sinon `RETRY_DELAYS_S[attempt] + uniform(0, 5)`.
- `src/lucas_v2/subs.py:37-55` : `download_srt()` crée un `tmpdir` neuf par vidéo, appelle `do_download()`, `rmtree` en `finally`.
- `src/lucas_v2/subs.py:58-71` : `base_opts()` avec `sleep_interval=2`, `max_sleep_interval=10`, `sleep_subtitles=5`, `retry_sleep={"extractor": 30}`.
- `src/lucas_v2/subs.py:84-118` : `do_download()` :
  - Bloc 1 : `YoutubeDL(base_opts).extract_info(url, download=False)` = pré-vol, liste les pistes, 0 hit `timedtext`. **Non wrappé en retry** : un 429 ici remonte tel quel en `DownloadError`.
  - `choose_track(manual, auto)` : `fr manuel > fr-orig manuel > fr auto > fr-orig auto`, sinon `(None, None)` → retour `(None, None, None, meta)`, 0 hit `timedtext`.
  - Bloc 2 : `run_with_retry(ydl_opts_timedtext, url)` avec `writesubtitles + subtitleslangs=[chosen]` = 1 seul hit `timedtext` par vidéo.
- `src/lucas_v2/subs.py:121-135` : `run_with_retry()` :
  - `for attempt in range(3)` : `extract_info(download=True)`, `return` si OK.
  - Sur `DownloadError` non-429 : `raise` immédiat.
  - Sur 429 : `sleep(backoff_delay)` si `attempt < 2`, sinon sortie de boucle → `raise RateLimitedError`.
  - Effet réel : **3 tentatives, 2 sleeps (60+jitter, 120+jitter)**. Le `300` de `RETRY_DELAYS_S` n'est jamais utilisé. Docstring « 60s, 1 retry » périmée.
- `src/lucas_v2/__init__.py:73-124` : `download_and_store()` :
  - `try: download_srt() / except Exception: upsert_video(..., "error", str(e)); return`.
  - **Bug actuel** : capte aussi `RateLimitedError`, insère `status="error"`, ne propage jamais. Le `except RateLimitedError: break` de `process_videos` est donc du code mort.
- `src/lucas_v2/__init__.py:126-167` : `process_videos()` :
  - `paced_sleep(INTER_VIDEO_DELAY_S=10 + jitter 0-5)` entre vidéos (`i > 0`).
  - `try: download_and_store() / except RateLimitedError: break` (intention anti-ban, inopérant aujourd'hui).
- `src/lucas_v2/__init__.py:185-249` : `ingest()` boucle `for spec in channels`, appelle `resolve_channel → fetch_videos → process_videos`. Un `break` dans `process_videos` n'arrêterait que la chaîne en cours, pas les suivantes. Sortie toujours 0 sauf config manquante / URL invalide.
- `src/lucas_v2/db.py:164-169` : `video_exists()` = `True` quel que soit le statut → une vidéo insérée `error` n'est jamais retentée sauf `--force-all` / `--url`.
- Tests : `tests/test_subs.py:152-211` (3 tentatives, 2 sleeps, `Retry-After`), `tests/test_cli.py:173-189` (`test_break_on_rate_limited` mocke `download_and_store` qui lève directement, ne reproduit pas l'avalement réel).

### 1.2 Pourquoi le skip actuel fait « retomber » le 429

Ce n'est pas le skip, c'est le temps + l'isolation :
- Vidéo en échec = `60 + 120 + jitter (~10s)` ≈ 190s de silence + `paced_sleep` 10-15s avant la suivante ≈ 200s sans hit `timedtext`.
- Chaque vidéo = `tmpdir` neuf + nouvelle instance `YoutubeDL` + 1 seul hit `timedtext`. Pas d'état client cumulé.
- Fenêtre glissante YouTube de quelques minutes → se vide pendant ces ~3min20, la requête isolée suivante passe.

### 1.3 Exigence validée avec l'utilisateur (Q&A)

1. Reset compteur : **seul un succès `timedtext` (SRT téléchargé) remet à 0**. `no_subs` et erreurs non-429 ne resettent pas.
2. BDD si rate-limit : **ne rien insérer** (ni `error`, ni statut dédié). `video_exists` reste `False` → retry naturel au prochain run.
3. Arrêt complet = **stop chaîne en cours ET chaînes suivantes, log clair, `sys.exit(1)`** (pour alerter cron/systemd).
4. Pré-vol `extract_info(download=False)` : **un 429 compte aussi** comme 1 hit dans les 6 consécutifs, même sans retry.

Conséquence mathématique : max 3 hits `timedtext` par vidéo (ou 1 hit pré-vol si échec précoce). Donc **6 hits consécutifs impliquent nécessairement ≥ 2 vidéos**, ce qui satisfait « sur au moins 2 vidéos consécutives » sans compteur de vidéos séparé.

## 2. Solution proposée

### 2.1 Principe

- Compter chaque hit HTTP 429 individuel (pré-vol + chaque tentative `run_with_retry`) dans un état global au run.
- Succès `timedtext` seul reset. Tout le reste (skip `no_subs`, erreur non-429, skip per-video `RateLimitedError`) laisse le compteur inchangé (sauf incrément sur 429).
- À `6` hits consécutifs : lever `AbortIngestion`, ne rien insérer, propager jusqu'à `ingest()` qui stoppe tout et sort en erreur.
- Un seul `RateLimitedError` (3 hits d'une vidéo) sans atteindre 6 = skip silencieux de la vidéo, **sans insert**, passage à la suivante (changement vs aujourd'hui qui insérait `error`).

### 2.2 Nouveaux / modifiés objets

**`src/lucas_v2/subs.py`** (seul fichier métier 429) :

- Constante : `MAX_CONSECUTIVE_429: int = 6`.
- Nouvelle exception : `class AbortIngestion(Exception)` = seuil global atteint, arrêt complet demandé.
- Nouvel état explicite (pas de global mutable caché, testable, typé strict) :
  ```python
  @dataclass(slots=True)
  class RateLimitState:
      consecutive_429: int = 0
  ```
  Helpers à complexité 1 chacun :
  - `record_429(state: RateLimitState) -> None` : `state.consecutive_429 += 1`
  - `reset_rate_limit(state: RateLimitState) -> None` : `state.consecutive_429 = 0`
  - `check_abort(state, video_url) -> None` : `if state.consecutive_429 >= MAX_CONSECUTIVE_429: raise AbortIngestion(...)`
- `do_download(video_url, tmpdir, rate_state)` : signature étendue.
  - Pré-vol wrappé : `try: extract_info(download=False) / except DownloadError as e: if is_retryable(e): record_429(state); check_abort(...); raise RateLimitedError(...) / else: raise`.
  - Si `choose_track` → `(None, None)` : retour `(None, None, None, meta)` **sans toucher au compteur** (ni reset, ni incrément).
  - Sinon `run_with_retry(ydl_opts, video_url, rate_state)`, puis lecture `.srt`. Si fichier lu OK → `reset_rate_limit(state)` avant de retourner (seul point de reset).
- `run_with_retry(ydl_opts, video_url, rate_state)` : signature étendue.
  - Sur chaque `DownloadError` 429 : `record_429(state); check_abort(state, url)` **avant** le sleep. Si abort → propagation immédiate, sans sleep supplémentaire, sans `RateLimitedError`.
  - Sinon comportement inchangé : sleep sauf dernière tentative, puis `raise RateLimitedError` après 3 échecs (le compteur vaut alors +3, conservé pour la vidéo suivante).
  - Sur `DownloadError` non-429 : `raise` sans toucher au compteur.
- `download_srt(youtube_str_id, rate_state)` : passe le `rate_state` à `do_download`. Mettre à jour la docstring périmée (« 60s, 1 retry » → « 3 tentatives, sleeps 60/120 + Retry-After, lève RateLimitedError »).

**`src/lucas_v2/__init__.py`** :

- `download_and_store(vid, channel_row_id, conn, is_new, tok, rate_state)` :
  - `except AbortIngestion: raise` (aucun `upsert`, aucun `commit`).
  - `except RateLimitedError as e: logger.warning("... vidéo skippée sans insertion ..."); return` (aucun `upsert`).
  - `except Exception as e:` inchangé (upsert `error` + commit), **sans toucher au compteur**.
  - Succès : inchangé (`upsert ok + replace_chunks + commit`). Le reset a déjà eu lieu dans `subs` au moment du SRT lu ; ne pas re-resetter ici pour garder une seule source de vérité.
- `process_videos(videos, channel_row_id, conn, force, dry_run, tok, rate_state)` :
  - Ajouter param `rate_state`. En `dry_run` : ne pas toucher au compteur, comportement inchangé.
  - `try: download_and_store(..., rate_state) / except AbortIngestion: logger.warning("Rate-limit global (%d 429 consécutifs) : ingestion arrêtée ..."); raise` (ou retourner un flag `aborted=True`). Préféré : laisser propager `AbortIngestion` pour garder `process_videos` fine et centraliser l'exit dans `ingest` (complexité minimale).
  - Supprimer le `except RateLimitedError: break` devenu obsolète (le skip per-video est géré dans `download_and_store`, on continue la boucle).
  - Changer le type de retour si propagation par exception : inchangé `(new, existing)`. Si flag préféré : `(new, existing, aborted)`. Recommandation : propagation par exception (moins de changements d'appels).
- `ingest()` :
  - Créer `rate_state = RateLimitState()` une fois avant la boucle `for spec in channels`.
  - Passer à chaque `process_videos(...)`.
  - Wrapper boucle chaînes : `try: ... / except AbortIngestion: logger.error("Arrêt complet après 6x429 consécutifs ..."); sys.exit(1)`.
  - Ne pas `commit` partiel supplémentaire sur abort ; les vidéos OK précédentes sont déjà commitées une par une.
- `ingest_single_video()` / `fetch_and_download_single()` (`--url`) :
  - Créer un `RateLimitState` local, passer à `download_and_store`. Sur `AbortIngestion` : `logger.error(...); sys.exit(1)`. Sur `RateLimitedError` : log + sortie 0 (vidéo skippée, sera reprise) — à confirmer en build si on veut exit 0 ou 1 pour ce cas unitaire ; défaut : exit 0 car un seul `--url` avec 3x429 n'atteint pas 6 par définition (sauf pré-vol + 3 ? max 3-4, jamais 6 seul).

### 2.3 Règles AGENTS.md

- Typage fort partout (`RateLimitState`, `str | None`, `dict[str, Any]`), `pyright` zéro warning/erreur après chaque évolution.
- Complexité cognitive ≤ 15 par fonction : découper en `record_429 / reset_rate_limit / check_abort / handle_prewol_429` plutôt qu'un gros bloc try/except.
- Aucun changement de schéma DB → pas de script SQL (exigence « ne rien insérer » évite toute migration).

### 2.4 Non-objectifs

- Pas de circuit-breaker temporel global (ex : pause 30min puis reprise auto dans le même run).
- Pas de persistance du compteur entre runs (compteur mémoire du process uniquement).
- Pas de modification de `RETRY_DELAYS_S` / `300` inutilisé (signaler en commentaire `TODO`, ne pas changer le pacing dans ce ticket pour limiter le risque).
- Pas de retry du pré-vol (on compte 1 hit et on skip la vidéo, comme validé).

## 3. Scénarios de test fonctionnel (langage humain)

1. **2 vidéos en 429 persistant → arrêt complet** : `V1` lève 3x429, `V2` lève 3x429 → au 6e hit, log « arrêt complet », aucune des 2 en BDD (`video_exists == False`), chaînes suivantes non traitées, exit code 1.
2. **1 vidéo 429 puis succès → pas d'arrêt** : `V1` 3x429 (skip sans insert, compteur=3), `V2` OK (compteur reset à 0), `V3` OK → run complet, exit 0, `V1` absente de BDD donc reprise au prochain run.
3. **`no_subs` ne reset pas** : `V1` 3x429 (compteur=3), `V2` sans FR (0 hit, compteur reste 3), `V3` 3x429 → abort au 6e. Vérifie que `no_subs` n'a pas effacé la mémoire.
4. **Erreur non-429 ne reset pas et n'incrémente pas** : `V1` 3x429 (3), `V2` 404 (upsert `error`, compteur toujours 3), `V3` 3x429 → abort. `V2` bien en BDD `error`, `V1/V3` absentes.
5. **Pré-vol 429 compte** : mocker `extract_info(download=False)` en 429 sur `V1` (compteur=1, skip sans insert), puis `V2` 3x429 (compteur=4), puis `V3` 2x429 puis succès 3e tentative → compteur reset à 0, pas d'abort.
6. **Seuil exact** : 5 hits consécutifs puis succès → pas d'abort ; 6e hit → abort immédiat sans sleep supplémentaire ni tentative restante.

## 4. Spécifications techniques pour l'implémenteur

### 4.1 Fichiers à toucher (ordre)

1. `src/lucas_v2/subs.py` — état + exceptions + `do_download` + `run_with_retry` + `download_srt` + docstrings.
2. `src/lucas_v2/__init__.py` — `download_and_store` (re-raise ciblé), `process_videos` (propagation abort, suppression break per-video), `ingest` (création état, try/except → `sys.exit(1)`), `fetch_and_download_single` / `ingest_single_video` (`--url`).
3. `tests/test_subs.py` — nouveaux tests `RateLimitState`, `check_abort`, `run_with_retry` avec état (comptage hits, abort au 6e, reset au succès, pré-vol 429).
4. `tests/test_cli.py` — `download_and_store` n'insère rien sur `RateLimitedError`, propage `AbortIngestion` ; `process_videos`/`ingest` stoppent tout et exit 1 (mocker `sys.exit` ou `pytest.raises(SystemExit)`).

### 4.2 Signatures cibles (pyright-strict)

```python
# subs.py
MAX_CONSECUTIVE_429: int = 6
class RateLimitedError(Exception): ...
class AbortIngestion(Exception): ...
@dataclass(slots=True)
class RateLimitState:
    consecutive_429: int = 0
def record_429(state: RateLimitState) -> None: ...
def reset_rate_limit(state: RateLimitState) -> None: ...
def check_abort(state: RateLimitState, video_url: str) -> None: ...  # raise AbortIngestion si >= 6
def download_srt(youtube_str_id: str, rate_state: RateLimitState) -> tuple[str | None, str | None, str | None, dict[str, Any]]: ...
def do_download(video_url: str, tmpdir: str, rate_state: RateLimitState) -> tuple[str | None, str | None, str | None, dict[str, Any]]: ...
def run_with_retry(ydl_opts: dict[str, Any], video_url: str, rate_state: RateLimitState) -> None: ...

# __init__.py
def download_and_store(vid: dict[str, Any], channel_row_id: int, conn: Any, is_new: bool, tok: Any, rate_state: RateLimitState) -> None: ...
def process_videos(videos: list[dict[str, Any]], channel_row_id: int, conn: Any, force: bool, dry_run: bool, tok: Any, rate_state: RateLimitState, force_id: str | None = None) -> tuple[int, int]: ...  # lève AbortIngestion
def ingest(...)  # crée RateLimitState(), try/except AbortIngestion -> sys.exit(1)
```

Rétro-compat tests : si des tests appellent `download_srt("id")` sans état, ajouter valeur par défaut `rate_state: RateLimitState | None = None` qui crée un état local — ou mettre à jour les appels de tests. Préféré : paramètre obligatoire pour forcer le partage global, et mettre à jour les 2 appels de tests existants.

### 4.3 Pseudo-code `run_with_retry`

```python
for attempt in range(len(RETRY_DELAYS_S)):
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(video_url, download=True)
        reset_rate_limit(rate_state)  # succès timedtext = seul reset
        return
    except DownloadError as e:
        if not is_retryable(e):
            raise
        record_429(rate_state)
        check_abort(rate_state, video_url)  # raise AbortIngestion si >= 6
        if attempt < len(RETRY_DELAYS_S) - 1:
            time.sleep(backoff_delay(attempt, e))
raise RateLimitedError(f"... vidéo skippée ...")
```

### 4.4 Pseudo-code `do_download` (pré-vol)

```python
try:
    with YoutubeDL(base_opts(tmpdir)) as ydl:
        info = ydl.extract_info(video_url, download=False)
except DownloadError as e:
    if is_retryable(e):
        record_429(rate_state)
        check_abort(rate_state, video_url)
        raise RateLimitedError(f"429 pré-vol sur {video_url} : vidéo skippée.") from e
    raise
```

### 4.5 Pseudo-code `download_and_store`

```python
try:
    srt_text, sub_lang, sub_kind, _meta = download_srt(vid_yt_id, rate_state)
except AbortIngestion:
    raise
except RateLimitedError as e:
    logger.warning("429 persistant sur %s : vidéo skippée sans insertion (%s)", vid_yt_id, e)
    return
except Exception as e:
    logger.error("ERREUR téléchargement subs : %s", e)
    upsert_video(..., "error", str(e)); conn.commit(); return
if srt_text is None:
    logger.warning("Aucun sous-titre FR trouvé.")  # ne reset pas, n'incrémente pas
    upsert_video(..., "no_subs", None); conn.commit(); return
... parse/chunk/upsert ok/commit (reset déjà fait en subs)
```

### 4.6 Pseudo-code `ingest`

```python
rate_state = RateLimitState()
try:
    for spec in channels:
        ... resolve/fetch ...
        process_videos(videos, ..., rate_state)
except AbortIngestion as e:
    logger.error("Rate-limit global : arrêt complet de l'ingestion (%s). Relancez plus tard.", e)
    sys.exit(1)
logger.info("Terminé.")
```

### 4.7 Cas limites

- `Retry-After` : compte quand même 1 hit (même si sleep = valeur serveur).
- `dry_run` : ne crée/incrémente rien (pas d'appel réseau subs de toute façon).
- Vidéo déjà en base skippée : n'affecte pas le compteur (pas de hit réseau).
- Concurrence : run mono-processus, état local suffit, pas de lock.
- Logs : sur chaque hit 429 logguer `consecutive_429=N/6` pour observabilité ; sur abort logguer `N vidéo(s) restante(s) + chaînes restantes non traitées`.

### 4.8 Tests unitaires à écrire/adapter

- `test_subs.py` :
  - `record/reset/check_abort` : 5 → pas d'exception, 6 → `AbortIngestion`.
  - `run_with_retry` avec `RateLimitState(consecutive_429=3)` + 3x429 mocké → `AbortIngestion` au 3e hit de la vidéo (total 6), `sleep.call_count == 2` (hits 4 et 5) puis abort sans 3e sleep.
  - `run_with_retry` avec état 0 + 2x429 puis succès → `consecutive_429 == 0` après reset.
  - `do_download` pré-vol 429 → `+1`, `RateLimitedError` (ou `AbortIngestion` si état à 5).
  - `do_download` `no FR` → compteur inchangé.
  - Non-429 → compteur inchangé + `DownloadError` d'origine.
- `test_cli.py` :
  - `download_and_store` sur `RateLimitedError` : `upsert_video` **non appelé**, pas d'exception.
  - `download_and_store` sur `AbortIngestion` : propage, `upsert_video` non appelé.
  - `process_videos` : 1x `RateLimitedError` → continue vidéo suivante (2 appels) ; 1x `AbortIngestion` → propage (2e vidéo non appelée).
  - `ingest` : `AbortIngestion` depuis `process_videos` → `SystemExit(1)`.

### 4.9 Vérifications finales (AGENTS.md)

- `pyright` : zéro erreur/warning sur `src/` + `tests/`.
- Complexité cognitive ≤ 15 par fonction (vérif Sonar) : si `download_and_store` dépasse, extraire `handle_subs_error(...)`.
- Aucune migration DB.

## 5. Validation demandée

Si ce plan te convient, je le considère validé et prêt pour implémentation en mode build. Sinon dis-moi ce à ajuster (ex : exit 0 vs 1, reset sur `no_subs`, retry pré-vol).
