# Plan — yt-dlp anti-429 : 1 seule passe + cookies compte secondaire

## 1. Contexte vérifié

Lucas v2 : `channels.yaml` → `youtube_api.py` (Data API) → `subs.py` (yt-dlp) → `srt.py` → `chunking.py` → Turso.

État actuel dans `src/lucas_v2/ingest/subs.py:do_download()` : 2 hits yt-dlp par vidéo.
1. Pré-vol `extract_info(download=False)` via `base_opts()` → lecture `subtitles` / `automatic_captions`, choix par `choose_track()` : `fr manuel > fr-orig manuel > fr auto > fr-orig auto`. Si aucun FR → retour `(None, None, None, meta)` → statut `no_subs`, 0 hit timedtext.
2. `run_with_retry()` → `extract_info(download=True)` avec `writesubtitles + subtitleslangs=[chosen]` → 1 hit timedtext.

Garde-fous existants à conserver :
- `base_opts()` : `skip_download True, quiet, no_warnings, retries 3, sleep_interval 2, max_sleep_interval 10, sleep_subtitles 5, extractor_retries 2, fragment_retries 2, retry_sleep {extractor:30}`.
- `__init__.py` : `INTER_VIDEO_DELAY_S=10 + jitter 5` via `paced_sleep()`.
- Retry 429 : `RETRY_DELAYS_S=(60,120,300) + jitter 5`, `Retry-After` prioritaire, `record_429 / check_abort`, `RateLimitedError` = skip sans insert, `AbortIngestion` à 6x 429 consécutifs.
- Data API (`youtube_api.py`) hors sujet : 429 = yt-dlp seul (décision Q1).

Fichiers lus : `AGENTS.md`, `ingest/subs.py`, `ingest/config.py`, `ingest/youtube_api.py`, `__init__.py`, `tests/test_subs.py`, `.gitignore`.

## 2. Besoin (décisions grillées R1+R2)

- Q1 : 429 = yt-dlp seul.
- Q2/Q6 : fichier cookies fourni à la main, non commité, chemin via `YOUTUBE_COOKIES_FILE` dans `.env` seul (pas d'option CLI). Absent/invalide → warning + mode anonyme, pas d'échec dur.
- Q3/Q7 : fusion 2 passes → 1 seul appel. Tri post-download en réutilisant `choose_track()` + matching nom de fichier (pas de règle simpliste « premier srt » : même coût 1 appel, meilleure précision).
- Q4 : aucune discrétion supplémentaire (délais / client player / proxy inchangés).
- Q5 : arrêt à 6x 429 conservé.
- Q8 : `cookies.txt` au `.gitignore`, `chmod 600`, doc export.
- Q9 : test réel manuel par Tristan (`--url`), pas d'auto-test réseau.

## 3. Solution proposée (langage humain)

1. **Cookies** : `YOUTUBE_COOKIES_FILE=~/.config/lucas/cookies.txt` (format Netscape, export via extension « Get cookies.txt LOCALLY » depuis compte secondaire). `base_opts()` injecte `cookiefile` si fichier existe, sinon warning mode anonyme. Log `info` « cookies chargés depuis … » sans contenu. Message explicite si 429 persiste : « cookies expirés ? ré-exporter ».
2. **1 seule passe** : unique `extract_info(download=True)` avec `writesubtitles=True, writeautomaticsub=True, subtitleslangs=['fr','fr-orig'], subtitlesformat='srt/best', convertsubtitles='srt'`. On récupère `info + fichiers *.srt` du tmpdir, on applique `choose_track(manuel, auto)` issu du même `info`, puis on lit le fichier correspondant. Aucun fichier → `no_subs` comme aujourd'hui.
3. **429 inchangé** : mêmes compteurs, backoff, abort.

## 4. Scénarios de test fonctionnel (manuel, par Tristan)

- SC1 sans cookies : warning anonyme, `uv run lucas-v2 ingest -c channels.yaml --url <vid FR>` → statut `ok`.
- SC2 avec cookies valides : log cookies chargés, `--url` → `ok`.
- SC3 vidéo sans FR : statut `no_subs`, pas de crash.
- SC4 429 répétés : skip vidéo sans insert, abort à 6x comme aujourd'hui.

## 5. Spécification technique (pour LLM simple)

### 5.1 Contraintes AGENTS.md (obligatoires)

- Package manager `uv` seul, jamais pip.
- `pyright strict` : zéro warning/erreur.
- Complexité ≤ 15 par fonction.
- Python ≥ 3.11.
- Nouveaux comportements couverts par tests.
- `from __future__ import annotations` en tête de tout fichier modifié.
- Annotations obligatoires sur signatures + variables clés.
- Français pour logs, commentaires, messages.
- `logging.getLogger("lucas_v2.subs")`, jamais `print()`.
- Secrets en `.env`, jamais commités.
- Aucun changement DB → pas de script SQL (règle : one-shot manuel uniquement si schéma touché, ici non).

### 5.2 `src/lucas_v2/ingest/subs.py`

#### 5.2.1 Constante + helper cookies

```python
COOKIE_ENV_VAR: str = "YOUTUBE_COOKIES_FILE"

def get_cookie_file() -> str | None:
    """Lit YOUTUBE_COOKIES_FILE, retourne le chemin si fichier valide, sinon None."""
    # - p = os.environ.get(COOKIE_ENV_VAR, "").strip()
    # - si vide → return None (pas de log, mode anonyme silencieux ou debug)
    # - si non vide mais not os.path.isfile(p) → logger.warning("Fichier cookies introuvable (%s) : mode anonyme.", p) + return None
    # - sinon → logger.info("Cookies YouTube chargés depuis %s.", p) + return p
    # - ne jamais logger le contenu du fichier
```

#### 5.2.2 Modifier `base_opts(tmpdir: str) -> dict[str, Any]`

- Garder tout le dict existant à l'identique.
- Ajouter après construction :
```python
cf = get_cookie_file()
if cf is not None:
    opts["cookiefile"] = cf
```
- Conserver type retour `dict[str, Any]`.

#### 5.2.3 Nouveau helper `pick_srt_file(tmpdir: str, chosen: str | None) -> Path | None`

```python
def pick_srt_file(tmpdir: str, chosen: str | None) -> Path | None:
    """Choisit le fichier .srt correspondant à la piste choisie."""
    # - files = sorted(Path(tmpdir).glob("*.srt"))
    # - si vide ou chosen is None → None
    # - si chosen == "fr" : chercher en priorité f.name.endswith(".fr.srt") en excluant ".fr-orig.srt" ; sinon fallback premier fichier avec ".fr" dans le nom
    # - si chosen == "fr-orig" : chercher ".fr-orig.srt" en priorité, sinon fallback contenant "fr-orig"
    # - ne jamais lever, retourner Path ou None
```

Note noms yt-dlp typiques : `<id>.fr.srt`, `<id>.fr-orig.srt` (après conversion depuis vtt). Tri `sorted()` pour déterminisme.

#### 5.2.4 Changer `run_with_retry` pour retourner `info`

Signature actuelle `-> None`. Nouvelle signature :

```python
def run_with_retry(ydl_opts: dict[str, Any], video_url: str, rate_state: RateLimitState) -> dict[str, Any] | None:
    # - boucle len(RETRY_DELAYS_S) tentatives comme aujourd'hui
    # - au lieu de ydl.extract_info(...) sans retour, faire info = ydl.extract_info(video_url, download=True)
    # - succès → reset_rate_limit + return info (possiblement None si yt-dlp retourne None)
    # - DownloadError 429 → record_429 + check_abort + sleep(backoff) comme aujourd'hui
    # - épuisement tentatives → raise RateLimitedError comme aujourd'hui
    # - non-429 → raise tel quel
```

Alternative acceptée : inliner l'appel dans `do_download()` sans changer `run_with_retry`, à condition de ne faire qu'un seul `extract_info`. Préférer le changement de retour car il minimise le diff et garde la logique retry centralisée.

#### 5.2.5 Réécrire `do_download(video_url, tmpdir, rate_state)`

Pseudo-code imposé (1 seul appel) :

```python
def do_download(video_url, tmpdir, rate_state):
    ydl_opts = {**base_opts(tmpdir), "writesubtitles": True, "writeautomaticsub": True,
                "subtitleslangs": ["fr", "fr-orig"], "subtitlesformat": "srt/best", "convertsubtitles": "srt"}
    try:
        info = run_with_retry(ydl_opts, video_url, rate_state)
    except DownloadError as e:
        if is_retryable(e):  # cas où run_with_retry laisserait passer (ne devrait pas)
            record_429(rate_state); check_abort(rate_state, video_url)
            raise RateLimitedError(...) from e
        raise
    if not info:
        return None, None, None, {}
    meta = extract_meta(info)
    manual = set((info.get("subtitles") or {}).keys())
    auto = set((info.get("automatic_captions") or {}).keys())
    chosen, sub_kind = choose_track(manual, auto)
    if chosen is None:
        return None, None, None, meta
    f = pick_srt_file(tmpdir, chosen)
    if f is None:
        return None, None, None, meta
    srt_text = f.read_text(encoding="utf-8")
    return srt_text, chosen, sub_kind, meta
```

- Supprimer l'ancien pré-vol `extract_info(download=False)` + le second bloc `ydl_opts` à `chosen` unique.
- Garder `download_srt()` (mkdtemp + `do_download` + rmtree) inchangée.
- Garder `choose_track(), extract_meta(), is_retryable(), backoff_delay(), record/reset/check` inchangés.

### 5.3 `.gitignore`

Ajouter :

```
# YouTube cookies (compte secondaire, jamais commité)
cookies.txt
*.cookies.txt
.youtube-cookies/
```

### 5.4 `.env` (documentation, non commitée)

Ajouter / documenter :

```
YOUTUBE_COOKIES_FILE=/home/tristan/.config/lucas/cookies.txt
```

Procédure export : compte secondaire → extension « Get cookies.txt LOCALLY » → exporter `youtube.com` → sauver chemin ci-dessus → `chmod 600`.

### 5.5 `tests/test_subs.py`

- `TestBaseOpts` : ajouter cas `YOUTUBE_COOKIES_FILE` absent → pas de clé `cookiefile` ; cas fichier existant (monkeypatch env + tmp_path avec fichier vide) → `cookiefile` présent ; cas chemin inexistant → pas de clé + warning (ne pas faire échouer).
- Nouveau `TestPickSrtFile` : créer faux `a.fr.srt`, `a.fr-orig.srt` en tmp_path → `pick_srt_file(d, "fr")` retourne `.fr.srt`, `"fr-orig"` retourne `.fr-orig.srt`, dossier vide → `None`, `chosen None` → `None`.
- `TestRunWithRetry` : adapter mocks au retour `info` (succès retourne dict, 429 puis succès retourne dict et reset compteur).
- `TestDownloadSrt` : inchangé (mocke `do_download`).

### 5.6 Ordre d'implémentation

1. `get_cookie_file` + `base_opts`.
2. `pick_srt_file`.
3. `run_with_retry -> info`.
4. `do_download` 1-passe.
5. `.gitignore`.
6. Tests.
7. `uv run pytest tests/test_subs.py -v` + `uv run pyright` verts.

### 5.7 Critères d'acceptation

- 1 seul `extract_info` par vidéo (vérifié en mock).
- `cookiefile` injecté si env valide, sinon mode anonyme avec warning.
- Priorité `fr > fr-orig manuel > auto` conservée.
- `no_subs / ok / error / skip-429-sans-insert / abort-6x` inchangés.
- `pytest + pyright` verts, complexité ≤15, logs FR.
