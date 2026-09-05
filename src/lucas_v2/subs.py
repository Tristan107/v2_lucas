import os
import shutil
import tempfile
import time
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError


class RateLimitedError(Exception):
    """429 YouTube : ne pas insérer en BDD, retry automatique au prochain run."""


# Délai avant chaque téléchargement de sous-titres (anti-429).
_SLEEP_SUBTITLES_S = 5


def download_srt(video_url: str) -> tuple[str | None, str | None, str | None, dict]:
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
    tmpdir = tempfile.mkdtemp(prefix="ytsubs_")
    try:
        return _do_download(video_url, tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _base_opts(tmpdir: str) -> dict:
    return {
        "skip_download": True,
        "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "sleep_interval": 2,
        "max_sleep_interval": 10,
        "sleep_subtitles": _SLEEP_SUBTITLES_S,
    }


def _do_download(video_url: str, tmpdir: str):
    # --- 1. Pré-vol : quelles pistes FR existent ? (pas de hit timedtext) ---
    with yt_dlp.YoutubeDL(_base_opts(tmpdir)) as ydl:
        info = ydl.extract_info(video_url, download=False)

    if not info:
        return None, None, None, {}

    meta = {
        "title": info.get("title"),
        "upload_date": info.get("upload_date"),
        "duration": info.get("duration"),
        "channel_url": info.get("channel_url"),
        "video_id": info.get("id"),
    }

    manual = set((info.get("subtitles") or {}).keys())
    auto = set((info.get("automatic_captions") or {}).keys())

    chosen, sub_kind = _choose_track(manual, auto)
    if chosen is None:
        return None, None, None, meta  # définitif : rien à télécharger

    # --- 2. Télécharge uniquement la piste choisie (1 hit timedtext) ---
    ydl_opts = {
        **_base_opts(tmpdir),
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [chosen],
        "subtitlesformat": "srt/best",
        "convertsubtitles": "srt",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(video_url, download=True)
    except DownloadError as e:
        if "429" in str(e):
            time.sleep(60)
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(video_url, download=True)
            except DownloadError as e2:
                if "429" in str(e2):
                    raise RateLimitedError(
                        f"Rate-limit YouTube persistant sur {video_url} : "
                        "vidéo skippée, sera reprise au prochain run."
                    ) from e2
                raise
        else:
            raise

    srt_files = sorted(Path(tmpdir).glob("*.srt"))
    if not srt_files:
        return None, None, None, meta

    srt_text = srt_files[0].read_text(encoding="utf-8")
    return srt_text, chosen, sub_kind, meta


def _choose_track(manual: set[str], auto: set[str]) -> tuple[str | None, str | None]:
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


def _lang_of(path: Path) -> str:
    stem = path.stem  # ex. mcI40Nu7k94.fr-orig
    parts = stem.split(".")
    return parts[-1] if len(parts) > 1 else "fr"
