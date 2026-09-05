from lucas_v2.srt import parse_srt
from lucas_v2.chunking import chunk_cues, count_tokens
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


def test_parse_srt_basic():
    cues = parse_srt(SAMPLE_SRT)
    assert len(cues) == 7
    assert cues[0].start_s == 1
    assert cues[0].end_s == 4  # 3500ms → ceil = 4
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


def test_chunk_cues_sentence_boundary():
    cues = parse_srt(SAMPLE_SRT)
    chunks = chunk_cues(cues, max_tokens=128)

    assert len(chunks) >= 1
    assert chunks[0].seq_no == 0
    assert chunks[0].start_s == 1
    # First chunk should end at cue 2 (semicolons and periods)
    # cues: "Bonjour à tous et bienvenue." → flush at .
    # cue 2: "Aujourd'hui on va parler de Python;" → flush at ;
    # etc.
    assert chunks[0].end_s >= 3


def test_chunk_cues_max_tokens():
    long_cues = [
        Cue(start_s=i * 10, end_s=i * 10 + 5,
            text=f"Phrase numéro {i} avec beaucoup de mots " * 5)
        for i in range(20)
    ]
    chunks = chunk_cues(long_cues, max_tokens=128)
    for ch in chunks:
        assert ch.tokens <= 128


def test_chunk_cues_empty():
    assert chunk_cues([]) == []


def test_count_tokens():
    assert count_tokens("") == 0
    assert count_tokens("hello world") == 2
    assert count_tokens("trois petits points.") == 3


def test_chunk_preserves_timing():
    cues = [
        Cue(start_s=0, end_s=5, text="Première phrase."),
        Cue(start_s=6, end_s=10, text="Deuxième phrase;"),
    ]
    chunks = chunk_cues(cues)
    assert len(chunks) == 2
    assert chunks[0].start_s == 0
    assert chunks[0].end_s == 5
    assert chunks[1].start_s == 6
    assert chunks[1].end_s == 10
