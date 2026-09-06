from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.discovery import build  # pyright: ignore[reportMissingModuleSource, reportUnknownVariableType]


def get_client() -> Any:
    api_key: str = os.environ["YOUTUBE_API_KEY"]
    return build("youtube", "v3", developerKey=api_key)  # pyright: ignore[reportUnknownVariableType]


_CHANNEL_REF_RE: re.Pattern[str] = re.compile(
    r"(?:/channel/(UC[\w-]{20,})"          # 1 – /channel/UC…
    r"|youtube\.com/@([^/?#]*)"             # 2 – youtube.com/@handle
    r"|youtube\.com/(?:c|user)/([^/?#]*)"   # 3 – youtube.com/c/… or /user/…
    r")"
)


def extract_channel_ref(url_or_handle: str) -> tuple[str, str]:
    """Parse channel URL/handle → (kind, value).

    kind is 'id' (UCxxx), 'handle' (@xxx), or 'query' (fallback search).
    Accepts full URLs, bare @handles, or plain names.
    """
    s: str = url_or_handle.strip().rstrip("/")
    m: re.Match[str] | None = _CHANNEL_REF_RE.search(s)
    if m:
        if m.group(1):
            return "id", m.group(1)
        if m.group(2):
            return "handle", "@" + m.group(2)
        return "query", m.group(3)

    if s.startswith("@"):
        return "handle", s.split("/")[0].split("?")[0]

    if "youtube.com" not in s and "/" not in s and " " not in s:
        return "handle", "@" + s.lstrip("@")

    return "query", s


def _resolve_by_id(youtube: Any, value: str, url_or_handle: str) -> tuple[str, str]:
    result = youtube.channels().list(part="snippet", id=value).execute()
    items = result.get("items", [])
    if not items:
        raise ValueError(f"Chaîne introuvable : {url_or_handle}")
    return items[0]["id"], items[0]["snippet"]["title"]


def _resolve_by_handle(youtube: Any, value: str) -> tuple[str, str] | None:
    candidates = [value, value.lstrip("@")]
    for cand in candidates:
        try:
            result = youtube.channels().list(part="snippet", forHandle=cand).execute()
        except Exception:
            continue
        items = result.get("items", [])
        if items:
            return items[0]["id"], items[0]["snippet"]["title"]
    return None


def _resolve_by_search(youtube: Any, query: str) -> tuple[str, str]:
    result = youtube.search().list(
        part="snippet", q=query, type="channel", maxResults=5
    ).execute()
    for item in result.get("items", []):
        ch_id = item.get("snippet", {}).get("channelId") or item.get("id", {}).get("channelId")
        title = item.get("snippet", {}).get("title", "")
        if ch_id:
            return ch_id, title
    raise ValueError(f"Chaîne introuvable : {query}")


def resolve_channel_id(url_or_handle: str) -> tuple[str, str]:
    """Resolve channel URL or @Handle → (channel_id, title)."""
    youtube: Any = get_client()
    kind: str
    value: str
    kind, value = extract_channel_ref(url_or_handle)

    if kind == "id":
        return _resolve_by_id(youtube, value, url_or_handle)

    if kind == "handle":
        result = _resolve_by_handle(youtube, value)
        if result is not None:
            return result

    query = value.lstrip("@") if kind == "handle" else value
    return _resolve_by_search(youtube, query)


def process_playlist_item(
    item: dict[str, Any], cutoff: datetime | None,
    video_ids: list[str], video_meta: dict[str, dict[str, str]],
) -> bool:
    """Process a single playlist item. Returns True if cutoff was reached."""
    snippet = item.get("snippet", {})
    vid = item.get("contentDetails", {}).get("videoId") or snippet.get("resourceId", {}).get("videoId")
    if not vid:
        return False

    published_at = snippet.get("publishedAt", "")
    if cutoff is not None and published_at:
        try:
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            if dt < cutoff:
                return True
        except Exception:
            pass

    video_ids.append(vid)
    video_meta[vid] = {
        "title": snippet.get("title", ""),
        "published_at": published_at,
    }
    return False


def _reached_limit(fetched: int, max_videos: int | None) -> bool:
    return max_videos is not None and fetched >= max_videos


def _fetch_next_page(
    youtube: Any, uploads_id: str, batch_size: int,
    next_token: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    pl_resp = youtube.playlistItems().list(
        part="snippet,contentDetails",
        playlistId=uploads_id,
        maxResults=min(batch_size, 50),
        pageToken=next_token,
    ).execute()
    return pl_resp.get("items", []), pl_resp.get("nextPageToken")


def _fetch_playlist_videos(
    youtube: Any, uploads_id: str, max_videos: int | None, cutoff: datetime | None,
) -> tuple[list[str], dict[str, dict[str, str]]]:
    video_ids: list[str] = []
    video_meta: dict[str, dict[str, str]] = {}
    next_token: str | None = None
    fetched = 0
    batch_size = 50 if cutoff is not None or max_videos is None else min(max_videos, 50)

    while not _reached_limit(fetched, max_videos):
        items, next_token = _fetch_next_page(youtube, uploads_id, batch_size, next_token)
        cutoff_reached = False
        for item in items:
            if process_playlist_item(item, cutoff, video_ids, video_meta):
                cutoff_reached = True
                break
            fetched += 1
            if _reached_limit(fetched, max_videos):
                break
        if cutoff_reached:
            break
        if next_token is None:
            break

    return video_ids, video_meta


def _fetch_video_details(
    youtube: Any, video_ids: list[str], video_meta: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        lot = video_ids[i:i + 50]
        vid_resp = youtube.videos().list(
            part="contentDetails,snippet",
            id=",".join(lot),
        ).execute()
        for v in vid_resp.get("items", []):
            vid_id = v["id"]
            duration_iso = v.get("contentDetails", {}).get("duration", "")
            duration_s = parse_iso_duration(duration_iso)
            results.append({
                "video_id": vid_id,
                "title": v.get("snippet", {}).get("title", ""),
                "upload_date": iso_to_yyyymmdd(video_meta.get(vid_id, {}).get("published_at", "")),
                "duration_s": duration_s,
                "youtube_str_id": vid_id,
                "published_at": video_meta.get(vid_id, {}).get("published_at", ""),
            })
    return results


def list_videos(channel_id: str, max_videos: int | None = 1,
                since_days: int | None = None) -> list[dict[str, Any]]:
    """List videos from a channel's uploads playlist.

    Returns list of dicts: {video_id, title, upload_date, duration_s, youtube_str_id, published_at}.
    """
    youtube: Any = get_client()

    ch_resp: dict[str, Any] = youtube.channels().list(
        part="contentDetails", id=channel_id
    ).execute()
    items: list[dict[str, Any]] = ch_resp.get("items", [])
    if not items:
        return []
    uploads_id: str = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    cutoff: datetime | None = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    video_ids: list[str]
    video_meta: dict[str, dict[str, str]]
    video_ids, video_meta = _fetch_playlist_videos(youtube, uploads_id, max_videos, cutoff)
    if not video_ids:
        return []

    results: list[dict[str, Any]] = _fetch_video_details(youtube, video_ids[:max_videos], video_meta)
    results.sort(key=lambda x: x["published_at"], reverse=True)
    return results[:max_videos]


def parse_iso_duration(iso: str) -> int | None:
    """PT1H2M3S → 3723 seconds."""
    if not iso or not iso.startswith("PT"):
        return None
    s: str = iso[2:]
    total: int = 0
    current: str = ""
    for c in s:
        if c.isdigit():
            current += c
        elif c == "H":
            total += int(current) * 3600
            current = ""
        elif c == "M":
            total += int(current) * 60
            current = ""
        elif c == "S":
            total += int(current)
            current = ""
    return total if total > 0 else None


def iso_to_yyyymmdd(iso: str) -> str | None:
    if not iso:
        return None
    try:
        dt: datetime = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y%m%d")
    except Exception:
        return None
