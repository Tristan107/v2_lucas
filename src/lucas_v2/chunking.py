from dataclasses import dataclass

from lucas_v2.srt import Cue


@dataclass
class Chunk:
    seq_no: int
    start_s: int
    end_s: int
    text: str
    tokens: int


def count_tokens(text: str) -> int:
    return len(text.split())


def chunk_cues(cues: list[Cue], max_tokens: int = 128) -> list[Chunk]:
    """Group cues into chunks.

    Rules:
    - Accumulate cues until text ends with '.' or ';' AND is non-empty → flush.
    - If adding next cue would exceed max_tokens → flush at last sentence boundary,
      or force flush at max_tokens if no boundary found.
    - Each chunk: start_s = first cue, end_s = last cue, text joined by spaces.
    """
    if not cues:
        return []

    chunks = []
    seq_no = 0
    pending_cues: list[Cue] = []
    pending_text = ""
    pending_tokens = 0

    for cue in cues:
        candidate_text = f"{pending_text} {cue.text}".strip() if pending_text else cue.text
        candidate_tokens = count_tokens(candidate_text)

        if candidate_tokens > max_tokens and pending_cues:
            # Flush at last sentence boundary
            chunk = _flush(pending_cues, pending_text, seq_no)
            chunks.append(chunk)
            seq_no += 1
            pending_cues = []
            pending_text = ""
            pending_tokens = 0
            # Re-add current cue to fresh buffer
            candidate_text = cue.text
            candidate_tokens = count_tokens(candidate_text)

        pending_cues.append(cue)
        pending_text = candidate_text
        pending_tokens = candidate_tokens

        # Flush on sentence boundary
        if _ends_sentence(pending_text) and pending_tokens > 0:
            chunk = _flush(pending_cues, pending_text, seq_no)
            chunks.append(chunk)
            seq_no += 1
            pending_cues = []
            pending_text = ""
            pending_tokens = 0

    # Remaining
    if pending_cues:
        chunk = _flush(pending_cues, pending_text, seq_no)
        chunks.append(chunk)

    return chunks


def _ends_sentence(text: str) -> bool:
    stripped = text.rstrip()
    return stripped.endswith(".") or stripped.endswith(";")


def _flush(cues: list[Cue], text: str, seq_no: int) -> Chunk:
    return Chunk(
        seq_no=seq_no,
        start_s=cues[0].start_s,
        end_s=cues[-1].end_s,
        text=text,
        tokens=count_tokens(text),
    )
