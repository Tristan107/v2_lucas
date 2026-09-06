from __future__ import annotations

import logging
import random
import re
import sys
import time
from pathlib import Path
from typing import Any

import click
from dotenv import load_dotenv

from lucas_v2.config import ChannelSpec

logger: logging.Logger = logging.getLogger("lucas_v2")

INTER_VIDEO_DELAY_S: int = 10
INTER_JITTER_S: float = 5.0
_DONE_MSG: str = "Terminé."


def paced_sleep(base: int | float, jitter: float = INTER_JITTER_S) -> None:
    time.sleep(base + random.uniform(0, jitter))


_VIDEO_URL_RE: re.Pattern[str] = re.compile(
    r"(?:youtube\.com/watch\?.*?v=|youtu\.be/)([\w-]{11})"
)


def extract_video_id(url: str) -> str | None:
    """Extract 11-char video ID from a YouTube URL."""
    m = _VIDEO_URL_RE.search(url)
    return m.group(1) if m else None


def main() -> None:
    load_dotenv()
    cli()


@click.group()
def cli() -> None:
    """Lucas v2 - YouTube transcript ingestion tool."""


def resolve_channel(spec: ChannelSpec, conn: Any) -> tuple[int, str, str] | None:
    from lucas_v2.db import upsert_channel
    from lucas_v2.youtube_api import resolve_channel_id

    try:
        yt_channel_id: str
        channel_title: str
        yt_channel_id, channel_title = resolve_channel_id(spec.url)
        row_id: int = upsert_channel(conn, spec.url, yt_channel_id, channel_title, spec.orientation, spec.owner)
        return row_id, yt_channel_id, channel_title
    except Exception as e:
        logger.error("  ERREUR résolution chaîne : %s", e)
        return None


def fetch_videos(channel_id: str, spec: ChannelSpec) -> list[dict[str, Any]]:
    from lucas_v2.youtube_api import list_videos

    try:
        return list_videos(channel_id, spec.max_videos, spec.since_days)
    except Exception as e:
        logger.error("  ERREUR listing vidéos : %s", e)
        return []


def download_and_store(
    vid: dict[str, Any],
    channel_row_id: int,
    conn: Any,
    is_new: bool,
    tok: Any,
) -> None:
    from lucas_v2.db import upsert_video, replace_chunks
    from lucas_v2.subs import download_srt
    from lucas_v2.srt import parse_srt
    from lucas_v2.chunking import chunk_cues

    vid_yt_id: str = str(vid["youtube_str_id"])

    try:
        srt_text: str | None
        sub_lang: str | None
        sub_kind: str | None
        _meta: dict[str, Any]
        srt_text, sub_lang, sub_kind, _meta = download_srt(vid_yt_id)
    except Exception as e:
        logger.error("     ERREUR téléchargement subs : %s", e)
        upsert_video(
            conn, channel_row_id, vid_yt_id,
            vid.get("title"), vid.get("upload_date"), vid.get("duration_s"),
            None, None, "error", str(e),
        )
        conn.commit()
        return

    if srt_text is None:
        logger.warning("     Aucun sous-titre FR trouvé.")
        upsert_video(
            conn, channel_row_id, vid_yt_id,
            vid.get("title"), vid.get("upload_date"), vid.get("duration_s"),
            None, None, "no_subs", None,
        )
        conn.commit()
        return

    cues = parse_srt(srt_text)
    chunks = chunk_cues(cues, tokenizer=tok)
    logger.info("     %d cues → %d chunks (%s)", len(cues), len(chunks), sub_kind)

    video_row_id: int = upsert_video(
        conn, channel_row_id, vid_yt_id,
        vid.get("title"), vid.get("upload_date"), vid.get("duration_s"),
        sub_lang, sub_kind, "ok", None,
    )
    replace_chunks(conn, video_row_id, chunks, delete_existing=not is_new)
    conn.commit()


def process_videos(
    videos: list[dict[str, Any]], channel_row_id: int,
    conn: Any, force: bool, dry_run: bool, tok: Any,
    force_id: str | None = None,
) -> tuple[int, int]:
    from lucas_v2.db import video_exists
    from lucas_v2.subs import RateLimitedError

    new_count: int = 0
    existing_count: int = 0

    for i, vid in enumerate(videos):
        vid_yt_id: str = str(vid["youtube_str_id"])

        is_new: bool = not video_exists(conn, vid_yt_id)

        if dry_run:
            if is_new or vid_yt_id == force_id:
                new_count += 1
            else:
                existing_count += 1
            continue

        logger.info("  >> %s (%s)", vid["title"], vid_yt_id)
        if not force and not is_new and vid_yt_id != force_id:
            logger.info("     Déjà scrapée, skip (utiliser --force-all ou --url pour re-scraper).")
            continue

        if i > 0:
            paced_sleep(INTER_VIDEO_DELAY_S)

        try:
            download_and_store(vid, channel_row_id, conn, is_new, tok)
        except RateLimitedError:
            logger.warning(
                "Rate-limit persistant : ingestion arrêtée. "
                "%d vidéo(s) restante(s) reprises au prochain lancement.",
                len(videos) - i - 1,
            )
            break

    return new_count, existing_count


def print_dry_run_summary(results: list[tuple[str, str | None, int, int]]) -> None:
    """Affiche un tableau récapitulatif en mode dry-run."""
    logger.info("\n--- dry-run summary ---")
    total_existing: int = 0
    total_new: int = 0
    for url, owner, new_c, exist_c in results:
        label: str = f"{url} ({owner})" if owner else url
        logger.info("  %s", label)
        logger.info("    existing: %d          new: %d", exist_c, new_c)
        total_existing += exist_c
        total_new += new_c
    logger.info("  %-50s %5d          %5d", "Total", total_existing, total_new)
    logger.info("  %d vidéo(s) à scraper.", total_new)


@cli.command()
@click.option("-c", "--config", "config_path", default="channels.yaml",
              help="Chemin vers le fichier YAML de configuration.")
@click.option("--dry-run", is_flag=True, help="Lister les vidéos sans télécharger.")
@click.option("--force-all", is_flag=True,
              help="Re-scrape toutes les vidéos déjà en base (avec confirmation).")
@click.option("--url", "video_url", default=None,
              help="URL YouTube d'une vidéo à re-télécharger.")
def ingest(config_path: str, dry_run: bool, force_all: bool, video_url: str | None) -> None:
    """Ingest transcripts from configured YouTube channels."""
    from lucas_v2.config import load_channels
    from lucas_v2.db import connect
    from lucas_v2.schema import init_schema
    from lucas_v2.chunking import get_tokenizer, MAX_CONTENT_TOKENS
    from lucas_v2.logging_config import setup_logging

    setup_logging()

    config_file: Path = Path(config_path)
    if not config_file.exists():
        logger.error("Config introuvable : %s", config_path)
        sys.exit(1)

    channels: list[ChannelSpec] = load_channels(config_path)
    logger.info("%d chaîne(s) à traiter.", len(channels))

    conn: Any = connect()
    init_schema(conn)
    tok: Any = get_tokenizer()
    tok_name: str = "MiniLM" if tok is not None else "whitespace"
    logger.info("Tokenizer: %s (max=%d)", tok_name, MAX_CONTENT_TOKENS)

    if video_url is not None:
        ingest_single_video(video_url, channels, conn, tok, dry_run)
        return

    if force_all and not dry_run:
        logger.info("Cette option re-téléchargera TOUTES les vidéos de %d chaîne(s) déjà en base.", len(channels))
        if not click.confirm("Voulez-vous vraiment re-télécharger toutes les vidéos listées dans channels.yaml ?"):
            logger.info("Annulé.")
            sys.exit(0)

    dry_run_results: list[tuple[str, str | None, int, int]] = []

    for spec in channels:
        logger.info("--- %s (%s) ---", spec.url, spec.owner)
        result: tuple[int, str, str] | None = resolve_channel(spec, conn)
        if result is None:
            continue
        channel_row_id: int
        yt_channel_id: str
        channel_row_id, yt_channel_id, _ = result

        videos: list[dict[str, Any]] = fetch_videos(yt_channel_id, spec)
        logger.info("          Videos matching the criteria in channel.yaml : %d", len(videos))
        new_count, existing_count = process_videos(
            videos, channel_row_id, conn, force_all, dry_run, tok,
        )
        if dry_run:
            dry_run_results.append((spec.url, spec.owner, new_count, existing_count))

    if dry_run and dry_run_results:
        print_dry_run_summary(dry_run_results)

    logger.info(_DONE_MSG)


def ingest_single_video(
    video_url: str, channels: list[ChannelSpec], conn: Any, tok: Any, dry_run: bool,
) -> None:
    """Handle --url: re-download a specific video by its YouTube URL."""
    from lucas_v2.db import find_video_channel, get_channel_url

    vid_id: str | None = extract_video_id(video_url)
    if vid_id is None:
        logger.error("URL invalide, impossible d'extraire l'ID : %s", video_url)
        sys.exit(1)

    ch_info: tuple[int, str] | None = find_video_channel(conn, vid_id)

    if ch_info is not None:
        channel_row_id_db: int
        _yt_ch_id: str
        channel_row_id_db, _yt_ch_id = ch_info
        channel_url: str | None = get_channel_url(conn, channel_row_id_db)
        logger.info("Vidéo %s trouvée en base (chaîne : %s), re-téléchargement...", vid_id, channel_url)

        fetch_and_download_single(vid_id, channel_row_id_db, conn, tok, dry_run)
        logger.info(_DONE_MSG)
        return

    logger.info("Vidéo %s absente de la base, recherche dans les chaînes configurées...", vid_id)
    for spec in channels:
        logger.info("--- %s ---", spec.url)
        result: tuple[int, str, str] | None = resolve_channel(spec, conn)
        if result is None:
            continue
        channel_row_id_c: int
        yt_channel_id_c: str
        _channel_title_c: str
        channel_row_id_c, yt_channel_id_c, _channel_title_c = result

        videos_c: list[dict[str, Any]] = fetch_videos(yt_channel_id_c, spec)
        match: dict[str, Any] | None = next(
            (v for v in videos_c if str(v["youtube_str_id"]) == vid_id), None,
        )
        if match is not None:
            logger.info("  Trouvée dans %s !", spec.url)
            if dry_run:
                logger.info("     [dry-run] Re-téléchargement de %s", vid_id)
            else:
                download_and_store(match, channel_row_id_c, conn, False, tok)
            logger.info(_DONE_MSG)
            return

    logger.error("Vidéo %s introuvable dans les chaînes configurées.", vid_id)
    sys.exit(1)


def fetch_and_download_single(
    vid_id: str, channel_row_id: int,
    conn: Any, tok: Any, dry_run: bool,
) -> None:
    """Fetch video metadata from YouTube API and download/store it."""
    from lucas_v2.youtube_api import get_client

    youtube: Any = get_client()
    vid_resp: Any = youtube.videos().list(
        part="contentDetails,snippet", id=vid_id,
    ).execute()
    items_v: list[dict[str, Any]] = vid_resp.get("items", [])
    if not items_v:
        logger.error("Vidéo introuvable sur YouTube : %s", vid_id)
        sys.exit(1)

    v_item: dict[str, Any] = items_v[0]
    vid_data: dict[str, Any] = {
        "video_id": vid_id,
        "title": v_item.get("snippet", {}).get("title", ""),
        "upload_date": None,
        "duration_s": None,
        "youtube_str_id": vid_id,
    }

    if dry_run:
        logger.info("     [dry-run] Re-téléchargement de %s", vid_id)
        return

    download_and_store(vid_data, channel_row_id, conn, False, tok)
