from __future__ import annotations

from pathlib import Path

from lucas_v2.ingest.config import ChannelSpec, load_channels


def test_load_channels(tmp_path: Path) -> None:
    config = tmp_path / "channels.yaml"
    config.write_text("""\
defaults:
  max_videos: 3
  since_days: 7
  lang: fr
channels:
  - url: https://www.youtube.com/@TestChannel1
  - url: https://www.youtube.com/@TestChannel2
    max_videos: 5
""")
    channels = load_channels(str(config))
    assert len(channels) == 2
    assert channels[0] == ChannelSpec(
        url="https://www.youtube.com/@TestChannel1",
        max_videos=3,
        since_days=7,
        lang="fr",
    )
    assert channels[1] == ChannelSpec(
        url="https://www.youtube.com/@TestChannel2",
        max_videos=5,
        since_days=7,
        lang="fr",
    )


def test_load_channels_with_owner_and_orientation(tmp_path: Path) -> None:
    config = tmp_path / "channels.yaml"
    config.write_text("""\
defaults:
  owner: Alice
  orientation: gauche
channels:
  - url: https://www.youtube.com/@TestChannel
""")
    channels = load_channels(str(config))
    assert channels[0].owner == "Alice"
    assert channels[0].orientation == "gauche"
