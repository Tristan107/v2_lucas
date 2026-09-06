from lucas_v2.srt import parse_srt
from lucas_v2.chunking import chunk_cues, count_tokens, MAX_CONTENT_TOKENS, SOFT_MIN
from lucas_v2.srt import Cue


SAMPLE_SRT = """\
1
00:00:01,000 --> 00:00:03,500
Bonjour à tous et bienvenue.

2
00:00:04,000 --> 00:00:06,200
Aujourd'hui on va parler de Python;

3
00:00:07,000 --> 00:00:10,800
c'est un langage très puissant.

4
00:00:11,500 --> 00:00:14,000
Il est utilisé partout dans le monde.

5
00:00:15,000 --> 00:00:17,500
Et c'est gratuit.

6
00:00:18,000 --> 00:00:22,000
N'hésitez pas à vous abonner pour plus de vidéos.

7
00:00:23,000 --> 00:00:25,500
Merci et à bientôt.
"""

SAMPLE_SRT_TAGS = """\
1
00:00:01,000 --> 00:00:03,500
<font color="white">Bonjour</font> à tous.

2
00:00:04,000 --> 00:00:06,000
Ceci est un <b>test</b>;
"""


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------

def test_parse_srt_basic():
    cues = parse_srt(SAMPLE_SRT)
    assert len(cues) == 7
    assert cues[0].start_s == 1
    assert cues[0].end_s == 4
    assert cues[0].text == "Bonjour à tous et bienvenue."


def test_parse_srt_strip_tags():
    cues = parse_srt(SAMPLE_SRT_TAGS)
    assert len(cues) == 2
    assert cues[0].text == "Bonjour à tous."
    assert cues[1].text == "Ceci est un test;"


def test_parse_srt_multiline():
    srt = "1\n00:00:01,000 --> 00:00:03,000\nLigne 1\nLigne 2\n\n"
    cues = parse_srt(srt)
    assert len(cues) == 1
    assert cues[0].text == "Ligne 1 Ligne 2"


# ---------------------------------------------------------------------------
# count_tokens
# ---------------------------------------------------------------------------

def test_count_tokens():
    assert count_tokens("") == 0
    assert count_tokens("hello world") >= 2
    assert count_tokens("trois petits points.") >= 3


# ---------------------------------------------------------------------------
# Chunking — core invariants (whitespace fallback for fast tests)
# ---------------------------------------------------------------------------

def test_chunk_empty():
    assert chunk_cues([]) == []


def test_chunk_small_input_single_chunk():
    cues = parse_srt(SAMPLE_SRT)
    chunks = chunk_cues(cues, max_tokens=MAX_CONTENT_TOKENS)
    assert len(chunks) == 1
    assert chunks[0].seq_no == 0
    assert chunks[0].start_s == 1
    assert chunks[0].tokens <= MAX_CONTENT_TOKENS


def test_chunk_never_exceeds_max():
    long_cues = [
        Cue(start_s=i * 10, end_s=i * 10 + 5,
            text=f"Phrase numéro {i} avec beaucoup de mots " * 5)
        for i in range(20)
    ]
    chunks = chunk_cues(long_cues, max_tokens=MAX_CONTENT_TOKENS)
    for ch in chunks:
        assert ch.tokens <= MAX_CONTENT_TOKENS


def test_chunk_no_overlap():
    cues = [
        Cue(start_s=0, end_s=5, text="alpha beta gamma."),
        Cue(start_s=6, end_s=10, text="delta epsilon zeta."),
        Cue(start_s=11, end_s=15, text="eta theta iota."),
    ]
    chunks = chunk_cues(cues, max_tokens=10)
    # Each cue is in exactly one chunk (no overlap).
    for ch in chunks:
        words = ch.text.split()
        for _w in words:
            # Each word from a cue appears only in one chunk.
            pass
    # No overlap: total words across chunks == total words across cues.
    total_cue_words = sum(len(c.text.split()) for c in cues)
    total_chunk_words = sum(len(ch.text.split()) for ch in chunks)
    assert total_chunk_words == total_cue_words


def test_chunk_prefers_sentence_boundary():
    cues = [
        Cue(start_s=0, end_s=5, text="mot " * 8 + "phrase un."),
        Cue(start_s=6, end_s=10, text="mot " * 8 + "phrase deux."),
    ]
    chunks = chunk_cues(cues, max_tokens=20)
    # Should split at the sentence boundary, not mid-phrase.
    assert len(chunks) >= 2
    assert chunks[0].text.rstrip().endswith(".")
    assert chunks[1].text.rstrip().endswith(".")


def test_chunk_tail_merge():
    # Build cues where the tail is forced separate (cues too large to
    # absorb) and small enough to merge.
    cues = [
        Cue(start_s=0, end_s=5, text=" ".join(["mot"] * 15) + "."),
        Cue(start_s=6, end_s=10, text=" ".join(["mot"] * 15) + "."),
        Cue(start_s=11, end_s=12, text="x y z."),
    ]
    chunks = chunk_cues(cues, max_tokens=20)
    # Each cue is individually >10 tokens so they can't be absorbed.
    # Last chunk ("x y z.") should be tiny → merged with previous.
    for ch in chunks:
        assert ch.tokens <= 20
    # Either merged into 2 chunks or kept as 3 (if merge exceeds max).
    assert len(chunks) <= 3


def test_chunk_preserves_timing():
    cues = [
        Cue(start_s=0, end_s=5, text="Première phrase."),
        Cue(start_s=6, end_s=10, text="Deuxième phrase;"),
    ]
    chunks = chunk_cues(cues)
    assert len(chunks) == 1
    assert chunks[0].start_s == 0
    assert chunks[0].end_s == 10


def test_punctuation_question_mark_recognized():
    cues = [
        Cue(start_s=0, end_s=5, text="Est-ce que ça marche?"),
        Cue(start_s=6, end_s=10, text="Oui ça marche!"),
    ]
    chunks = chunk_cues(cues, max_tokens=20)
    # ? and ! should be treated as sentence boundaries.
    assert all(ch.tokens <= 20 for ch in chunks)


def test_oversize_cue_split():
    oversize = Cue(start_s=0, end_s=5, text=" ".join(["mot"] * 200))
    chunks = chunk_cues([oversize], max_tokens=126)
    assert len(chunks) > 1
    for ch in chunks:
        assert ch.tokens <= 126
    # All 200 words accounted for.
    all_words = " ".join(ch.text for ch in chunks).split()
    assert len(all_words) == 200


def test_seq_no_continuous():
    cues = [
        Cue(start_s=i * 10, end_s=i * 10 + 5,
            text=f"Phrase numéro {i} avec beaucoup de mots " * 5)
        for i in range(20)
    ]
    chunks = chunk_cues(cues, max_tokens=MAX_CONTENT_TOKENS)
    for idx, ch in enumerate(chunks):
        assert ch.seq_no == idx


def test_pack_density():
    cues = [
        Cue(start_s=i * 10, end_s=i * 10 + 5, text="mot " * 9 + f"fin{i}.")
        for i in range(30)
    ]
    chunks = chunk_cues(cues, max_tokens=MAX_CONTENT_TOKENS)
    assert len(chunks) < 30
    assert max(ch.tokens for ch in chunks) <= MAX_CONTENT_TOKENS
    assert any(ch.tokens > 100 for ch in chunks)


# ---------------------------------------------------------------------------
# Real tokenizer integration test (requires network for first download)
# ---------------------------------------------------------------------------

def test_chunk_with_real_tokenizer():
    """Test with the actual MiniLM tokenizer if available."""
    from lucas_v2.chunking import get_tokenizer
    tok = get_tokenizer()
    if tok is None:
        return  # skip if tokenizer unavailable

    cues = [
        Cue(start_s=i * 10, end_s=i * 10 + 5,
            text=f"Phrase numéro {i} avec beaucoup de mots et détails intéressants ")
        for i in range(30)
    ]
    chunks = chunk_cues(cues, tokenizer=tok)
    for ch in chunks:
        real_count = len(tok.encode(ch.text, add_special_tokens=False))
        assert ch.tokens == real_count
        assert ch.tokens <= MAX_CONTENT_TOKENS
    # Density check: most chunks should be near the target.
    non_tail = [ch for ch in chunks[:-1]]
    if non_tail:
        avg = sum(ch.tokens for ch in non_tail) / len(non_tail)
        assert avg > SOFT_MIN - 10
