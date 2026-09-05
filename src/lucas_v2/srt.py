import re
import html
from dataclasses import dataclass


@dataclass
class Cue:
    start_s: int
    end_s: int
    text: str


_SRT_BLOCK = re.compile(
    r"(\d+)\s*\n"
    r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n"
    r"((?:(?!\n\n|\Z).)*)",
    re.DOTALL,
)

_TAG_RE = re.compile(r"<[^>]+>")
_POSITION_RE = re.compile(r"(?:align|position|line):\s*\S+", re.IGNORECASE)


def parse_srt(text: str) -> list[Cue]:
    """Parse SRT text into list of Cue(start_s, end_s, text).

    Timestamps converted to seconds (floor start, ceil end).
    HTML entities unescaped, tags stripped, multi-lines joined.
    """
    cues = []
    for match in _SRT_BLOCK.finditer(text):
        start_str = match.group(2)
        end_str = match.group(3)
        raw_text = match.group(4)

        lines = []
        for line in raw_text.strip().split("\n"):
            line = _TAG_RE.sub("", line)
            line = _POSITION_RE.sub("", line)
            line = html.unescape(line)
            line = line.strip()
            if line:
                lines.append(line)

        combined = " ".join(lines)
        if not combined:
            continue

        cues.append(Cue(
            start_s=_time_to_s(start_str),
            end_s=_time_to_s_ceil(end_str),
            text=combined,
        ))

    return cues


def _time_to_s(ts: str) -> int:
    """HH:MM:SS,mmm → floor seconds."""
    parts = ts.replace(",", ":").split(":")
    h, m, s, ms = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
    return h * 3600 + m * 60 + s


def _time_to_s_ceil(ts: str) -> int:
    """HH:MM:SS,mmm → ceil seconds (0ms stays same)."""
    parts = ts.replace(",", ":").split(":")
    h, m, s, ms = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
    total = h * 3600 + m * 60 + s
    return total + (1 if ms > 0 else 0)
