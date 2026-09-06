from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

INTER_VIDEO_DELAY_S = 3

import click
from dotenv import load_dotenv

from lucas_v2.config import ChannelSpec
from lucas_v2.chunking import Chunk


def main() -> None:
    load_dotenv()
    cli()


@click.group()
def cli() -> None:
    """Lucas v2 - YouTube transcript ingestion tool."""


def _resolve_channel(spec: ChannelSpec, conn: Any) -> int | None:
    from lucas_v2.db import upsert_channel
    from lucas_v2.youtube_api import resolve_channel_id

    try:
        yt_channel_id, channel_title = resolve_channel_id(spec.url)
        click.echo(f"  channelId: {yt_channel_id} ({channel_title})")
        return upsert_channel(conn, spec.url, yt_channel_id, channel_title)
    except Exception as e:
        click.echo(f"  ERREUR résolution chaîne : {e}", err=True)
        return None


def _fetch_videos(channel_id: str, spec: ChannelSpec) -> list[dict[str, Any]]:
    from lucas_v2.youtube_api import list_videos

    try:
        return list_videos(channel_id, spec.max_videos, spec.since_days)
    except Exception as e:
        click.echo(f"  ERREUR listing vidéos : {e}", err=True)
        return []


def _download_and_store(
    vid: dict[str, Any],
    channel_row_id: int,
    spec: ChannelSpec,
    conn: Any,
    is_new: bool,
    tok: Any,
) -> None:
    from lucas_v2.db import upsert_video, replace_chunks
    from lucas_v2.subs import RateLimitedError, download_srt
    from lucas_v2.srt import parse_srt
    from lucas_v2.chunking import chunk_cues

    vid_yt_id = str(vid["youtube_str_id"])

    try:
        srt_text, sub_lang, sub_kind, _meta = download_srt(vid_yt_id)
    except RateLimitedError as e:
        click.echo(f"     RATE-LIMIT, vidéo skippée sans insertion : {e}", err=True)
        return
    except Exception as e:
        click.echo(f"     ERREUR téléchargement subs : {e}", err=True)
        upsert_video(
            conn, channel_row_id, vid_yt_id,
            vid.get("title"), vid.get("upload_date"), vid.get("duration_s"),
            None, None, spec.owner, "error", str(e),
        )
        conn.commit()
        return

    if srt_text is None:
        click.echo("     Aucun sous-titre FR trouvé.")
        upsert_video(
            conn, channel_row_id, vid_yt_id,
            vid.get("title"), vid.get("upload_date"), vid.get("duration_s"),
            None, None, spec.owner, "no_subs", None,
        )
        conn.commit()
        return

    cues = parse_srt(srt_text)
    chunks = chunk_cues(cues, tokenizer=tok)
    click.echo(f"     {len(cues)} cues → {len(chunks)} chunks ({sub_kind})")

    video_row_id = upsert_video(
        conn, channel_row_id, vid_yt_id,
        vid.get("title"), vid.get("upload_date"), vid.get("duration_s"),
        sub_lang, sub_kind, spec.owner, "ok", None,
    )
    replace_chunks(conn, video_row_id, chunks, delete_existing=not is_new)
    conn.commit()


def _process_videos(
    videos: list[dict[str, Any]], channel_row_id: int,
    spec: ChannelSpec, conn: Any, force: bool, dry_run: bool, tok: Any,
) -> None:
    from lucas_v2.db import video_exists

    for i, vid in enumerate(videos):
        vid_yt_id = str(vid["youtube_str_id"])
        click.echo(f"\n  >> {vid['title']} ({vid_yt_id})")

        is_new = not video_exists(conn, vid_yt_id)
        if not force and not is_new:
            click.echo("     Déjà scrapée, skip (utiliser --force pour re-scraper).")
            continue

        if dry_run:
            click.echo(f"     [dry-run] Upload: {vid.get('upload_date')}, Durée: {vid.get('duration_s')}s")
            continue

        if i > 0 and not dry_run:
            time.sleep(INTER_VIDEO_DELAY_S)

        _download_and_store(vid, channel_row_id, spec, conn, is_new, tok)


@cli.command()
@click.option("-c", "--config", "config_path", default="channels.yaml",
              help="Chemin vers le fichier YAML de configuration.")
@click.option("--dry-run", is_flag=True, help="Lister les vidéos sans télécharger.")
@click.option("--force", is_flag=True, help="Re-scrape même si déjà en base avec status=ok.")
def ingest(config_path: str, dry_run: bool, force: bool) -> None:
    """Ingest transcripts from configured YouTube channels."""
    from lucas_v2.config import load_channels
    from lucas_v2.db import connect
    from lucas_v2.schema import init_schema
    from lucas_v2.chunking import get_tokenizer, MAX_CONTENT_TOKENS

    config_file = Path(config_path)
    if not config_file.exists():
        click.echo(f"Config introuvable : {config_path}", err=True)
        sys.exit(1)

    channels = load_channels(config_path)
    click.echo(f"{len(channels)} chaîne(s) à traiter.")

    conn = connect()
    init_schema(conn)
    tok = get_tokenizer()
    tok_name = "MiniLM" if tok is not None else "whitespace"
    click.echo(f"Tokenizer: {tok_name} (max={MAX_CONTENT_TOKENS})")

    for spec in channels:
        click.echo(f"\n--- {spec.url} ---")
        channel_row_id = _resolve_channel(spec, conn)
        if channel_row_id is None:
            continue

        videos = _fetch_videos(spec.url, spec)
        click.echo(f"  {len(videos)} vidéo(s) trouvée(s).")
        _process_videos(videos, channel_row_id, spec, conn, force, dry_run, tok)

    click.echo("\nTerminé.")
