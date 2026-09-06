from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass
from typing import Any

from lucas_v2.srt import Cue

MAX_CONTENT_TOKENS: int = 126  # +2 [CLS]/[SEP] = 128 total for MiniLM
SOFT_MIN: int = 110
MIN_TAIL: int = 30

_MODEL_NAME: str = os.environ.get(
    "LUCAS_TOKENIZER",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

_tokenizer: Any = None


def get_tokenizer() -> Any:
    global _tokenizer
    if _tokenizer is None:
        try:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from transformers import AutoTokenizer
            _tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        except Exception as exc:
            warnings.warn(
                f"Tokenizer HF indisponible ({exc}), fallback whitespace.", stacklevel=2
            )
            _tokenizer = None
    return _tokenizer  # pyright: ignore[reportUnknownVariableType]


def count_tokens(text: str, tokenizer: Any = None) -> int:
    tok: Any = tokenizer or get_tokenizer()
    if tok is None:
        return len(text.split())
    return len(tok.encode(text, add_special_tokens=False))


@dataclass
class Chunk:
    seq_no: int
    start_s: int
    end_s: int
    text: str
    tokens: int


def _ends_sentence(text: str) -> bool:
    return bool(re.search(r"([.;?!:\u2026])|(\.{3}$)", text.rstrip()))


def _split_oversize(cue: Cue, max_tokens: int, tokenizer: Any = None) -> list[Chunk]:
    """Split a single oversize cue into sub-chunks (the only case where
    intra-cue splitting occurs)."""
    words = cue.text.split()
    chunks: list[Chunk] = []
    part_text = ""

    for word in words:
        candidate = f"{part_text} {word}".strip() if part_text else word
        if count_tokens(candidate, tokenizer) > max_tokens:
            if part_text:
                chunks.append(Chunk(
                    seq_no=len(chunks),
                    start_s=cue.start_s,
                    end_s=cue.end_s,
                    text=part_text,
                    tokens=count_tokens(part_text, tokenizer),
                ))
            part_text = word
        else:
            part_text = candidate

    if part_text:
        chunks.append(Chunk(
            seq_no=len(chunks),
            start_s=cue.start_s,
            end_s=cue.end_s,
            text=part_text,
            tokens=count_tokens(part_text, tokenizer),
        ))

    return chunks


def _flush_sentence_boundary(
    cues: list[Cue], i: int, end: int, tokenizer: Any = None,
) -> int | None:
    """Search for a sentence boundary in the window and return its index, or None."""
    for idx in range(i, end + 1):
        prefix = " ".join(c.text for c in cues[i:idx + 1])
        if _ends_sentence(prefix) and count_tokens(prefix, tokenizer) >= SOFT_MIN:
            return idx
    return None


def _flush_chunk(
    chunks: list[Chunk], seq_no: int,
    cues: list[Cue], i: int, end: int, tokenizer: Any = None,
) -> int:
    """Append a chunk from cues[i..end] and return next seq_no."""
    text = " ".join(c.text for c in cues[i:end + 1])
    chunks.append(Chunk(
        seq_no=seq_no,
        start_s=cues[i].start_s,
        end_s=cues[end].end_s,
        text=text,
        tokens=count_tokens(text, tokenizer),
    ))
    return seq_no + 1


def _handle_oversize_cue(
    cue: Cue, max_tokens: int, chunks: list[Chunk], seq_no: int, tokenizer: Any = None,
) -> int:
    """Handle an oversize cue by splitting it. Returns next seq_no."""
    oversize = _split_oversize(cue, max_tokens, tokenizer)
    for ch in oversize:
        chunks.append(Chunk(
            seq_no=seq_no,
            start_s=ch.start_s,
            end_s=ch.end_s,
            text=ch.text,
            tokens=ch.tokens,
        ))
        seq_no += 1
    return seq_no


def _accumulate_until_limit(
    cues: list[Cue], i: int, max_tokens: int, tokenizer: Any = None,
) -> tuple[str, int]:
    """Accumulate cues starting from i until token limit. Returns (text, end_index)."""
    j = i
    text = ""
    n = len(cues)
    while j < n:
        candidate = f"{text} {cues[j].text}".strip() if text else cues[j].text
        if count_tokens(candidate, tokenizer) > max_tokens:
            break
        text = candidate
        j += 1
    return text, j - 1


def chunk_cues(
    cues: list[Cue],
    max_tokens: int = MAX_CONTENT_TOKENS,
    soft_min: int = SOFT_MIN,
    tokenizer: Any = None,
) -> list[Chunk]:
    """Pack cues into chunks of at most ``max_tokens`` WordPiece tokens.

    No overlap between chunks. Greedy accumulation:
    cues are added one by one until the token limit is reached, then the
    window is flushed. When a sentence boundary (``.;?!:…`` or ``...``)
    falls within the window near the limit, the flush happens at that
    boundary. Oversize single cues are split at word boundaries.

    The final chunk is merged with the previous one if it is smaller than
    ``MIN_TAIL`` tokens and the combined total does not exceed ``max_tokens``.
    """
    if not cues:
        return []

    chunks: list[Chunk] = []
    seq_no = 0
    i = 0
    n = len(cues)

    while i < n:
        cue_tok = count_tokens(cues[i].text, tokenizer)
        if cue_tok > max_tokens:
            seq_no = _handle_oversize_cue(cues[i], max_tokens, chunks, seq_no, tokenizer)
            i += 1
            continue

        text, end = _accumulate_until_limit(cues, i, max_tokens, tokenizer)

        # Search for a sentence boundary in the window so we can flush
        # at a natural break when close to the limit.
        if end < n - 1 and count_tokens(text, tokenizer) >= soft_min:
            k = _flush_sentence_boundary(cues, i, end, tokenizer)
            if k is not None:
                seq_no = _flush_chunk(chunks, seq_no, cues, i, k, tokenizer)
                i = k + 1
                continue

        # No suitable sentence boundary — flush the whole window.
        seq_no = _flush_chunk(chunks, seq_no, cues, i, end, tokenizer)
        i = end + 1

    # Merge tiny tail with previous chunk if possible.
    if len(chunks) >= 2:
        last = chunks[-1]
        prev = chunks[-2]
        if last.tokens < MIN_TAIL and prev.tokens + last.tokens <= max_tokens:
            merged_text = f"{prev.text} {last.text}"
            chunks[-2] = Chunk(
                seq_no=prev.seq_no,
                start_s=prev.start_s,
                end_s=last.end_s,
                text=merged_text,
                tokens=count_tokens(merged_text, tokenizer),
            )
            chunks.pop()

    # Re-sequence after potential merge.
    for idx, ch in enumerate(chunks):
        ch.seq_no = idx

    return chunks
