import os
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build


def _get_client():
    api_key = os.environ["YOUTUBE_API_KEY"]
    return build("youtube", "v3", developerKey=api_key)


def _extract_channel_ref(url_or_handle: str) -> tuple[str, str]:
    """Parse channel URL/handle → (kind, value).

    kind is 'id' (UCxxx), 'handle' (@xxx), or 'query' (fallback search).
    Accepts full URLs, bare @handles, or plain names.
    """
    import re

    s = url_or_handle.strip().rstrip("/")

    m = re.search(r"/channel/(UC[\w-]{20,})", s)
    if m:
        return "id", m.group(1)

    m = re.search(r"youtube\.com/@([^/?#]+)", s)
    if m:
        return "handle", "@" + m.group(1)

    if s.startswith("@"):
        return "handle", s.split("/")[0].split("?")[0]

    m = re.search(r"youtube\.com/(?:c|user)/([^/?#]+)", s)
    if m:
        return "query", m.group(1)

    if "youtube.com" not in s and "/" not in s and " " not in s:
        return "handle", "@" + s.lstrip("@")

    return "query", s


def resolve_channel_id(url_or_handle: str) -> tuple[str, str]:
    """Resolve channel URL or @Handle → (channel_id, title)."""
    youtube = _get_client()
    kind, value = _extract_channel_ref(url_or_handle)

    if kind == "id":
        result = youtube.channels().list(part="snippet", id=value).execute()
        items = result.get("items", [])
        if not items:
            raise ValueError(f"Chaîne introuvable : {url_or_handle}")
        return items[0]["id"], items[0]["snippet"]["title"]

    if kind == "handle":
        candidates = [value, value.lstrip("@")]
        for cand in candidates:
            try:
                result = youtube.channels().list(part="snippet", forHandle=cand).execute()
            except Exception:
                continue
            items = result.get("items", [])
            if items:
                return items[0]["id"], items[0]["snippet"]["title"]

    # Fallback: search by name/handle
    query = value.lstrip("@") if kind == "handle" else value
    result = youtube.search().list(
        part="snippet", q=query, type="channel", maxResults=5
    ).execute()
    for item in result.get("items", []):
        ch_id = item.get("snippet", {}).get("channelId") or item.get("id", {}).get("channelId")
        title = item.get("snippet", {}).get("title", "")
        if ch_id:
            return ch_id, title

    raise ValueError(f"Chaîne introuvable : {url_or_handle}")


def list_videos(channel_id: str, max_videos: int = 1,
                since_days: int | None = None) -> list[dict]:
    """List videos from a channel's uploads playlist.

    Returns list of dicts: {video_id, title, upload_date, duration_s, video_url, published_at}.
    """
    youtube = _get_client()

    ch_resp = youtube.channels().list(
        part="contentDetails", id=channel_id
    ).execute()
    items = ch_resp.get("items", [])
    if not items:
        return []
    uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    video_ids = []
    video_meta = {}
    next_token = None
    fetched = 0
    cutoff = None
    if since_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    batch_size = 50 if since_days else min(max_videos, 50)

    cutoff_reached = False
    while True:
        pl_resp = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_id,
            maxResults=min(batch_size, 50),
            pageToken=next_token,
        ).execute()

        for item in pl_resp.get("items", []):
            snippet = item.get("snippet", {})
            vid = item.get("contentDetails", {}).get("videoId") or snippet.get("resourceId", {}).get("videoId")
            if not vid:
                continue

            published_at = snippet.get("publishedAt", "")

            if cutoff is not None and published_at:
                try:
                    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    if dt < cutoff:
                        # Playlist ordonnée anti-chrono : on arrête tout
                        cutoff_reached = True
                        break
                except Exception:
                    pass

            video_ids.append(vid)
            video_meta[vid] = {
                "title": snippet.get("title", ""),
                "published_at": published_at,
            }
            fetched += 1
            if fetched >= max_videos:
                break

        if fetched >= max_videos or cutoff_reached:
            break
        next_token = pl_resp.get("nextPageToken")
        if not next_token:
            break

    if not video_ids:
        return []

    batch_ids = video_ids[:max_videos]
    results = []
    # videos.list accepte max 50 ids par appel → découper par lots
    for i in range(0, len(batch_ids), 50):
        lot = batch_ids[i:i + 50]
        vid_resp = youtube.videos().list(
            part="contentDetails,snippet",
            id=",".join(lot),
        ).execute()
        for v in vid_resp.get("items", []):
            vid_id = v["id"]
            duration_iso = v.get("contentDetails", {}).get("duration", "")
            duration_s = _parse_iso_duration(duration_iso)
            results.append({
                "video_id": vid_id,
                "title": v.get("snippet", {}).get("title", ""),
                "upload_date": _iso_to_yyyymmdd(video_meta.get(vid_id, {}).get("published_at", "")),
                "duration_s": duration_s,
                "video_url": f"https://www.youtube.com/watch?v={vid_id}",
                "published_at": video_meta.get(vid_id, {}).get("published_at", ""),
            })

    results.sort(key=lambda x: x["published_at"], reverse=True)
    return results[:max_videos]


def _parse_iso_duration(iso: str) -> int | None:
    """PT1H2M3S → 3723 seconds."""
    if not iso or not iso.startswith("PT"):
        return None
    s = iso[2:]
    total = 0
    current = ""
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


def _iso_to_yyyymmdd(iso: str) -> str | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y%m%d")
    except Exception:
        return None
