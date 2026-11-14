"""eval/split_recordings.py cuts a long "word, pause, word, ..." recording into one clip per word.

Synthetic audio only (beeps + silence), so the tests never need private recordings.
"""
import numpy as np
import pytest

from eval.split_recordings import script_words, select, speech_pieces

SR = 16000


def _audio(parts):
    """parts: [("beep" | "quiet", seconds), ...] -> float32 audio. Beeps are a 220 Hz tone at about -26 dB."""
    out = []
    for kind, sec in parts:
        n = int(sec * SR)
        t = np.arange(n) / SR
        out.append(0.07 * np.sin(2 * np.pi * 220 * t) if kind == "beep" else np.zeros(n))
    return np.concatenate(out).astype(np.float32)


def test_three_words_give_three_pieces_with_times():
    x = _audio([("quiet", 1), ("beep", 0.5), ("quiet", 1), ("beep", 0.5), ("quiet", 1), ("beep", 0.5), ("quiet", 1)])
    pieces = speech_pieces(x, SR)
    assert len(pieces) == 3
    assert pieces[0] == pytest.approx((1.0, 1.5), abs=0.02)
    assert pieces[2] == pytest.approx((4.0, 4.5), abs=0.02)


def test_a_click_is_not_a_word():
    x = _audio([("quiet", 1), ("beep", 0.5), ("quiet", 1), ("beep", 0.05), ("quiet", 1), ("beep", 0.5), ("quiet", 1)])
    assert len(speech_pieces(x, SR)) == 2


def test_a_short_gap_inside_a_word_does_not_split_it():
    # e.g. the closure in 뽀뽀: 0.15 s of silence is shorter than a real pause between words
    x = _audio([("quiet", 1), ("beep", 0.3), ("quiet", 0.15), ("beep", 0.3), ("quiet", 1)])
    assert len(speech_pieces(x, SR)) == 1


def test_select_drops_a_known_false_start_and_checks_the_count():
    pieces = [(1.0, 1.5), (3.0, 3.5), (5.0, 5.5)]
    assert select(pieces, expected=2, drop_at=[3.2]) == [(1.0, 1.5), (5.0, 5.5)]
    with pytest.raises(ValueError, match="expected 3 pieces, found 2"):
        select(pieces, expected=3, drop_at=[3.2])


def test_select_refuses_a_drop_time_that_hits_no_piece():
    with pytest.raises(ValueError, match="no piece at 9.0"):
        select([(1.0, 1.5)], expected=1, drop_at=[9.0])


def test_word_list_comes_from_the_recording_script():
    words = script_words()
    assert len(words) == 30
    assert words[0] == "거기" and words[13] == "나라" and words[-1] == "불"
