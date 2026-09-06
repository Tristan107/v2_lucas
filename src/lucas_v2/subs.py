from __future__ import annotations

import os
import random
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import yt_dlp  # pyright: ignore[reportMissingModuleSource]
from yt_dlp.utils import DownloadError  # pyright: ignore[reportMissingModuleSource]


class RateLimitedError(Exception):
    """429 YouTube : ne pas insérer en BDD, retry automatique au prochain run."""


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


def download_srt(youtube_str_id: str) -> tuple[str | None, str | None, str | None, dict[str, Any]]:
    """Download SRT subtitles for a video (1 seule requête timedtext).

    Stratégie anti-429 :
    1. Pré-vol sans téléchargement : liste les pistes dispo, choisit LA meilleure
       (fr manuel > fr-orig manuel > fr auto > fr-orig auto). Aucun hit timedtext.
    2. Télécharge uniquement cette piste (1 seul hit timedtext).
    3. Sur 429 : attend 60 s, 1 retry, sinon lève RateLimitedError
       (l'ingest skipe sans insérer → retry naturel au prochain run).

    Returns (srt_text, sub_lang, sub_kind, meta).
    Returns (None, None, None, meta) si pas de FR (définitif, 0 hit timedtext).
    """
    video_url = f"https://www.youtube.com/watch?v={youtube_str_id}"
    tmpdir = tempfile.mkdtemp(prefix="ytsubs_")
    try:
        return do_download(video_url, tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def base_opts(tmpdir: str) -> dict[str, Any]:
    return {
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


def extract_meta(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": info.get("title"),
        "upload_date": info.get("upload_date"),
        "duration": info.get("duration"),
        "channel_url": info.get("channel_url"),
        "video_id": info.get("id"),
    }


def do_download(video_url: str, tmpdir: str) -> tuple[str | None, str | None, str | None, dict[str, Any]]:
    with yt_dlp.YoutubeDL(base_opts(tmpdir)) as ydl:  # pyright: ignore[reportArgumentType]
        info = ydl.extract_info(video_url, download=False)  # pyright: ignore[reportAssignmentType]

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

    ydl_opts: dict[str, Any] = {
        **base_opts(tmpdir),
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [chosen],
        "subtitlesformat": "srt/best",
        "convertsubtitles": "srt",
    }

    run_with_retry(ydl_opts, video_url)

    srt_files: list[Path] = sorted(Path(tmpdir).glob("*.srt"))
    if not srt_files:
        return None, None, None, meta

    srt_text: str = srt_files[0].read_text(encoding="utf-8")
    return srt_text, chosen, sub_kind, meta


def run_with_retry(ydl_opts: dict[str, Any], video_url: str) -> None:
    for attempt in range(len(RETRY_DELAYS_S)):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # pyright: ignore[reportArgumentType]
                ydl.extract_info(video_url, download=True)
            return
        except DownloadError as e:
            if not is_retryable(e):
                raise
            if attempt < len(RETRY_DELAYS_S) - 1:
                time.sleep(backoff_delay(attempt, e))
    raise RateLimitedError(
        f"Rate-limit YouTube persistant sur {video_url} : "
        "vidéo skippée, sera reprise au prochain run."
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



