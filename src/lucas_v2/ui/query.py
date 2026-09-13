from __future__ import annotations


def build_match_query(raw: str) -> str:
    """Build FTS5 match query from user input.

    Supports explicit ``OR``, ``AND``, ``NOT`` operators (case-insensitive),
    parentheses, and implicit ``AND`` between adjacent terms.
    Apostrophes in terms are escaped for FTS5 (``'`` → ``''``).
    Raises ``ValueError`` when input is empty after processing.
    """
    _OPS: frozenset[str] = frozenset({"OR", "AND", "NOT"})

    tokens = raw.split()
    if not tokens:
        raise ValueError("Requête vide")

    classified: list[tuple[str, str]] = []
    for t in tokens:
        upper = t.upper()
        if upper in _OPS:
            classified.append(("OP", upper))
        elif t in ("(", ")"):
            classified.append(("PAREN", t))
        else:
            classified.append(("TERM", " ".join(t.replace("'", " ").split())))

    while classified and classified[0][0] == "OP":
        classified.pop(0)
    while classified and classified[-1][0] == "OP":
        classified.pop()

    if not classified:
        raise ValueError("Requête vide")

    output = [classified[0][1]]
    for i in range(1, len(classified)):
        prev_kind = classified[i - 1][0]
        curr_kind = classified[i][0]
        if prev_kind != "OP" and curr_kind != "OP":
            output.append("AND")
        output.append(classified[i][1])

    return " ".join(output)


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
