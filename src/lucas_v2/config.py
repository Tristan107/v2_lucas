from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ChannelSpec:
    url: str
    max_videos: int
    since_days: int | None
    lang: str


def load_channels(path: str) -> list[ChannelSpec]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    defaults = data.get("defaults", {})
    d_max_videos = defaults.get("max_videos", 1)
    d_since_days = defaults.get("since_days")
    d_lang = defaults.get("lang", "fr")

    channels = []
    for ch in data.get("channels", []):
        url = ch.get("url")
        if not url:
            continue
        channels.append(ChannelSpec(
            url=url,
            max_videos=ch.get("max_videos", d_max_videos),
            since_days=ch.get("since_days", d_since_days),
            lang=ch.get("lang", d_lang),
        ))
    return channels
