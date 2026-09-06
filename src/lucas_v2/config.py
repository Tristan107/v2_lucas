from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class ChannelSpec:
    url: str
    max_videos: int
    since_days: int | None
    lang: str
    owner: str | None = None
    orientation: str | None = None


def load_channels(path: str) -> list[ChannelSpec]:
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    defaults: dict[str, Any] = data.get("defaults", {})
    d_max_videos: int = defaults.get("max_videos", 1)
    d_since_days: int | None = defaults.get("since_days")
    d_lang: str = defaults.get("lang", "fr")
    d_owner: str | None = defaults.get("owner")
    d_orientation: str | None = defaults.get("orientation")

    channels: list[ChannelSpec] = []
    for ch in data.get("channels", []):
        url: str | None = ch.get("url")
        if not url:
            continue
        channels.append(ChannelSpec(
            url=url,
            max_videos=ch.get("max_videos", d_max_videos),
            since_days=ch.get("since_days", d_since_days),
            lang=ch.get("lang", d_lang),
            owner=ch.get("owner", d_owner),
            orientation=ch.get("orientation", d_orientation),
        ))
    return channels
