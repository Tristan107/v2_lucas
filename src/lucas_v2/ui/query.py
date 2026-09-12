from __future__ import annotations


def build_match_query(raw: str) -> str:
    """Build FTS5 match query from user input.

    ``'immigr*  travail*'`` becomes ``'immigr* AND travail*'``.
    Raises ``ValueError`` when input is empty after stripping.
    """
    tokens = [t for t in raw.split() if t]
    if not tokens:
        raise ValueError("Requête vide")
    return " AND ".join(tokens)


def format_hhmmss(total_s: int) -> str:
    """Format seconds to ``hh:mm:ss``.

    ``9260`` becomes ``'02:34:20'``. Negative values raise ``ValueError``.
    """
    if total_s < 0:
        raise ValueError(f"Nombre de secondes négatif : {total_s}")
    hours = total_s // 3600
    remainder = total_s % 3600
    minutes = remainder // 60
    seconds = remainder % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def youtube_url(youtube_str_id: str, start_s: int) -> str:
    """Build a YouTube deep-link that starts playback at ``start_s``."""
    return f"https://www.youtube.com/watch?v={youtube_str_id}&t={start_s}"


def format_date_fr(upload_date: str | None) -> str:
    """Format ``YYYYMMDD`` to ``jj/mm/aaaa``.

    ``20250615`` becomes ``'15/06/2025'``. ``None`` or empty
    returns ``''``. Unexpected formats are returned unchanged.
    """
    if not upload_date:
        return ""
    text = upload_date.strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[6:8]}/{text[4:6]}/{text[0:4]}"
    return text
