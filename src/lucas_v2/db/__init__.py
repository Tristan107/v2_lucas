from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    seq_no: int
    start_s: int
    end_s: int
    text: str
    tokens: int
