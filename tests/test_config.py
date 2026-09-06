from __future__ import annotations

from pathlib import Path

from lucas_v2.config import ChannelSpec, load_channels


def test_load_channels_basic(tmp_path: Path) -> None:
    yaml_content = """\
defaults:
  max_videos: 5
  since_days: 30
  lang: fr
  owner: test_owner
channels:
  - url: https://youtube.com/@Channel1
  - url: https://youtube.com/@Channel2
    max_videos: 10
"""
    config_file = tmp_path / "channels.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")

    channels = load_channels(str(config_file))
    assert len(channels) == 2
    assert channels[0].url == "https://youtube.com/@Channel1"
    assert channels[0].max_videos == 5
    assert channels[0].since_days == 30
    assert channels[0].lang == "fr"
    assert channels[0].owner == "test_owner"
    assert channels[1].max_videos == 10


def test_load_channels_no_url_skipped(tmp_path: Path) -> None:
    yaml_content = """\
defaults:
  max_videos: 1
channels:
  - url: https://youtube.com/@Good
  - title: No URL here
"""
    config_file = tmp_path / "channels.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")

    channels = load_channels(str(config_file))
    assert len(channels) == 1
    assert channels[0].url == "https://youtube.com/@Good"


def test_load_channels_defaults_applied(tmp_path: Path) -> None:
    yaml_content = """\
defaults:
  max_videos: 3
  since_days: 7
  lang: fr
channels:
  - url: https://youtube.com/@Ch
"""
    config_file = tmp_path / "channels.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")

    channels = load_channels(str(config_file))
    assert len(channels) == 1
    assert channels[0].max_videos == 3
    assert channels[0].since_days == 7


def test_load_channels_owner_orientation(tmp_path: Path) -> None:
    yaml_content = """\
defaults:
  max_videos: 1
channels:
  - url: https://youtube.com/@Ch
    owner: Tristan
    orientation: gauche
"""
    config_file = tmp_path / "channels.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")

    channels = load_channels(str(config_file))
    assert channels[0].owner == "Tristan"
    assert channels[0].orientation == "gauche"


def test_load_channels_empty_list(tmp_path: Path) -> None:
    yaml_content = """\
defaults:
  max_videos: 1
channels: []
"""
    config_file = tmp_path / "channels.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")

    channels = load_channels(str(config_file))
    assert channels == []


def test_channel_spec_frozen() -> None:
    spec = ChannelSpec(url="https://yt.com/ch", max_videos=1, since_days=None, lang="fr")
    assert spec.url == "https://yt.com/ch"
    assert spec.owner is None
    assert spec.orientation is None
