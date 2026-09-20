from __future__ import annotations

import logging
import os
import random
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yt_dlp  # pyright: ignore[reportMissingModuleSource]
from yt_dlp.utils import DownloadError  # pyright: ignore[reportMissingModuleSource]

logger: logging.Logger = logging.getLogger("lucas_v2.subs")

COOKIE_ENV_VAR: str = "YOUTUBE_COOKIES_FILE"

MAX_CONSECUTIVE_429: int = 6


def get_cookie_file() -> str | None:
    """Lit YOUTUBE_COOKIES_FILE, retourne le chemin si fichier valide, sinon None."""
    p: str = os.environ.get(COOKIE_ENV_VAR, "").strip()
    if not p:
        return None
    if not os.path.isfile(p):
        logger.warning("Fichier cookies introuvable (%s) : mode anonyme.", p)
        return None
    logger.info("Cookies YouTube chargés depuis %s.", p)
    return p


class RateLimitedError(Exception):
    """429 YouTube : ne pas insérer en BDD, retry automatique au prochain run."""


class AbortIngestion(Exception):
    """Seuil global de 429 consécutifs atteint, arrêt complet demandé."""


@dataclass(slots=True)
class RateLimitState:
    consecutive_429: int = 0


def record_429(state: RateLimitState) -> None:
    state.consecutive_429 += 1
    logger.warning("429 hit #%d/%d", state.consecutive_429, MAX_CONSECUTIVE_429)


def reset_rate_limit(state: RateLimitState) -> None:
    state.consecutive_429 = 0


def check_abort(state: RateLimitState, video_url: str) -> None:
    if state.consecutive_429 >= MAX_CONSECUTIVE_429:
        raise AbortIngestion(
            f"6x HTTP 429 consécutifs sur {video_url} : "
            "ingestion arrêtée, relancez plus tard."
        )


RETRY_DELAYS_S: tuple[int, ...] = (60, 120, 300)
JITTER_S: float = 5.0
_SLEEP_SUBTITLES_S: int = 5
_RETRY_AFTER_RE: re.Pattern[str] = re.compile(r"Retry-After:\s*(\d+)")


def is_retryable(e: Exception) -> bool:
    return "429" in str(e)


def backoff_delay(attempt: int, exc: Exception) -> float:
    m = _RETRY_AFTER_RE.search(str(exc))
    if m is not None:
        return float(m.group(1))
    return RETRY_DELAYS_S[attempt] + random.uniform(0, JITTER_S)


def download_srt(
    youtube_str_id: str,
    rate_state: RateLimitState,
) -> tuple[str | None, str | None, str | None, dict[str, Any]]:
    """Download SRT subtitles for a video.

    Stratégie anti-429 :
    1. Passe unique : un seul extract_info(download=True) qui récupère
       info + sous-titres fr/fr-orig, puis tri post-download
       (fr manuel > fr-orig manuel > fr auto > fr-orig auto).
    2. Sur 429 : 3 tentatives, sleeps 60/120 + Retry-After, lève RateLimitedError
       (l'ingest skipe sans insérer → retry naturel au prochain run).
    3. Cookies optionnels via YOUTUBE_COOKIES_FILE (compte secondaire) :
       si absent/invalide, mode anonyme avec warning.

    Returns (srt_text, sub_lang, sub_kind, meta).
    Returns (None, None, None, meta) si pas de FR (définitif, 0 hit timedtext).
    """
    video_url = f"https://www.youtube.com/watch?v={youtube_str_id}"
    tmpdir = tempfile.mkdtemp(prefix="ytsubs_")
    try:
        return do_download(video_url, tmpdir, rate_state)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def base_opts(tmpdir: str) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "skip_download": True,
        "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "sleep_interval": 2,
        "max_sleep_interval": 10,
        "sleep_subtitles": _SLEEP_SUBTITLES_S,
        "extractor_retries": 2,
        "fragment_retries": 2,
        "retry_sleep": {"extractor": 30},
    }
    cf: str | None = get_cookie_file()
    if cf is not None:
        opts["cookiefile"] = cf
    return opts


def pick_srt_file(tmpdir: str, chosen: str | None) -> Path | None:
    """Choisit le fichier .srt correspondant à la piste choisie."""
    files: list[Path] = sorted(Path(tmpdir).glob("*.srt"))
    if not files or chosen is None:
        return None
    if chosen == "fr":
        for f in files:
            if f.name.endswith(".fr.srt"):
                return f
        for f in files:
            if ".fr" in f.name and "fr-orig" not in f.name:
                return f
        return None
    if chosen == "fr-orig":
        for f in files:
            if f.name.endswith(".fr-orig.srt"):
                return f
        for f in files:
            if "fr-orig" in f.name:
                return f
        return None
    return None


def extract_meta(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": info.get("title"),
        "upload_date": info.get("upload_date"),
        "duration": info.get("duration"),
        "channel_url": info.get("channel_url"),
        "video_id": info.get("id"),
    }


def do_download(
    video_url: str,
    tmpdir: str,
    rate_state: RateLimitState,
) -> tuple[str | None, str | None, str | None, dict[str, Any]]:
    # Passe unique : 1 seul extract_info(download=True) qui télécharge
    # les sous-titres fr + fr-orig ; tri post-download via choose_track().
    ydl_opts: dict[str, Any] = {
        **base_opts(tmpdir),
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["fr", "fr-orig"],
        "subtitlesformat": "srt/best",
        "convertsubtitles": "srt",
    }
    try:
        info = run_with_retry(ydl_opts, video_url, rate_state)
    except DownloadError as e:
        if is_retryable(e):
            record_429(rate_state)
            check_abort(rate_state, video_url)
            raise RateLimitedError(
                f"429 sur {video_url} : vidéo skippée."
            ) from e
        raise

    if not info:
        return None, None, None, {}

    meta: dict[str, Any] = extract_meta(info)  # pyright: ignore[reportArgumentType]

    manual: set[str] = set((info.get("subtitles") or {}).keys())  # pyright: ignore[reportUnknownArgumentType]
    auto: set[str] = set((info.get("automatic_captions") or {}).keys())  # pyright: ignore[reportUnknownArgumentType]

    chosen: str | None
    sub_kind: str | None
    chosen, sub_kind = choose_track(manual, auto)
    if chosen is None:
        return None, None, None, meta

    srt_file: Path | None = pick_srt_file(tmpdir, chosen)
    if srt_file is None:
        return None, None, None, meta

    srt_text: str = srt_file.read_text(encoding="utf-8")
    return srt_text, chosen, sub_kind, meta


def run_with_retry(
    ydl_opts: dict[str, Any],
    video_url: str,
    rate_state: RateLimitState,
) -> dict[str, Any] | None:
    for attempt in range(len(RETRY_DELAYS_S)):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # pyright: ignore[reportArgumentType]
                info = ydl.extract_info(video_url, download=True)
            reset_rate_limit(rate_state)
            return info  # pyright: ignore[reportReturnType]
        except DownloadError as e:
            if not is_retryable(e):
                raise
            record_429(rate_state)
            check_abort(rate_state, video_url)
            if attempt < len(RETRY_DELAYS_S) - 1:
                time.sleep(backoff_delay(attempt, e))
    raise RateLimitedError(
        f"Rate-limit YouTube persistant sur {video_url} : "
        "vidéo skippée, sera reprise au prochain run. "
        "Si cookies configurés, vérifier leur validité (ré-exporter)."
    )


def choose_track(manual: set[str], auto: set[str]) -> tuple[str | None, str | None]:
    """Ordre : fr manuel > fr-orig manuel > fr auto > fr-orig auto."""
    if "fr" in manual:
        return "fr", "manual"
    if "fr-orig" in manual:
        return "fr-orig", "manual"
    if "fr" in auto:
        return "fr", "auto"
    if "fr-orig" in auto:
        return "fr-orig", "auto"
    return None, None
