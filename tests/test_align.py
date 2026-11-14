"""Forced-alignment wrapper. Audio + expected phonemes -> a start/end time per phoneme and word.

Pass bars are frozen from spikes/d_align.py (word starts median 42 ms, max 94 ms on these 3
sentences), set before running the new code: median <= 60 ms and no word off by more than 150 ms.
Data tests skip if data/ isn't there (it's git-ignored). L2-ARCTIC and Zeroth are open corpora,
used locally only; no personal recordings.
"""
import io
import re
import statistics
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from backend.align import align, emissions, model_symbol, vocab
from backend.g2p import ARPA2IPA, CODA, ONSET, VOWEL, expected_phonemes

L2ARCTIC = Path("data/l2arctic/HKK")
ZEROTH = Path("data/zeroth/data/test-00000-of-00001.parquet")


# ---------- symbols (fast: reads the model's vocab.json only) ----------
def test_every_korean_symbol_has_a_model_symbol():
    ko = {x for x in ONSET + CODA if x} | {x for v in VOWEL for x in v}
    assert all(model_symbol(x, "ko") in vocab() for x in ko)


def test_every_english_symbol_has_a_model_symbol():
    en = set(ARPA2IPA.values()) | {"ə"}
    assert all(model_symbol(x, "en") in vocab() for x in en)


def test_korean_uses_the_symbols_the_model_actually_hears():
    # From spikes/a_vowels.py: the model writes ㅓ as ɔ and ㄹ as r; it has no tense or ʰ-aspirated Korean symbols.
    assert model_symbol("ʌ", "ko") == "ɔ"
    assert model_symbol("ɾ", "ko") == "r"
    assert model_symbol("p͈", "ko") == "p"   # ㅃ
    assert model_symbol("a", "ko") == "a"         # unchanged when the model has it


# ---------- alignment on real speech ----------
def _human_words(textgrid):
    text = textgrid.read_text(encoding="utf-8", errors="replace")
    tier = text.split('name = "words"')[1].split("item [")[0]
    rows = re.findall(r'xmin = ([\d.]+)\s*xmax = ([\d.]+)\s*text = "([^"]*)"', tier)
    return [(float(a), float(b)) for a, b, lab in rows if lab.strip() not in ("", "sil", "sp")]


@pytest.mark.skipif(not L2ARCTIC.exists(), reason="L2-ARCTIC not downloaded")
def test_english_word_starts_match_human_times():
    errors_ms = []
    for utt in ["arctic_a0003", "arctic_a0005", "arctic_a0020"]:
        text = (L2ARCTIC / "transcript" / f"{utt}.txt").read_text().strip()
        audio, sr = sf.read(L2ARCTIC / "wav" / f"{utt}.wav", dtype="float32")   # 44.1 kHz: tests resampling
        words = align(emissions(audio, sr), expected_phonemes(text, "en"), "en")
        human = _human_words(L2ARCTIC / "annotation" / f"{utt}.TextGrid")
        assert len(words) == len(human), utt
        errors_ms += [abs(w["start"] - h[0]) * 1000 for w, h in zip(words, human)]
    assert statistics.median(errors_ms) <= 60
    assert max(errors_ms) <= 150


@pytest.mark.skipif(not ZEROTH.exists(), reason="Zeroth not downloaded")
def test_korean_alignment_is_well_formed():
    import pyarrow.parquet as pq
    row = next(pq.ParquetFile(ZEROTH).iter_batches(batch_size=1)).to_pylist()[0]
    audio, sr = sf.read(io.BytesIO(row["audio"]["bytes"]), dtype="float32")
    expected = expected_phonemes(row["text"], "ko")
    words = align(emissions(audio, sr), expected, "ko")
    duration = len(audio) / sr

    assert [w["word"] for w in words] == [w["word"] for w in expected]
    phones = [p for w in words for p in w["phonemes"]]
    assert [p["ipa"] for p in phones] == [p for w in expected for p in w["phonemes"]]   # textbook IPA kept
    starts = [p["start"] for p in phones]
    assert starts == sorted(starts)                                    # in order
    assert all(0 <= p["start"] < p["end"] <= duration + 0.03 for p in phones)
    assert all(0 <= p["conf"] <= 1 for p in phones)
    assert all(w["start"] < w["end"] for w in words)


# ---------- edge cases ----------
def _beep(seconds, sr, channels=1):
    t = np.arange(int(seconds * sr)) / sr
    tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype("float32")
    return np.stack([tone] * channels, axis=1) if channels > 1 else tone


def test_stereo_44k_input_is_accepted():
    words = align(emissions(_beep(1.0, 44100, channels=2), 44100), expected_phonemes("cat", "en"), "en")
    assert [len(w["phonemes"]) for w in words] == [3]


def test_recording_too_short_for_the_sentence_raises():
    long_text = "Please call Stella and ask her to bring these things with her from the store"
    with pytest.raises(ValueError):
        align(emissions(_beep(0.2, 16000), 16000), expected_phonemes(long_text, "en"), "en")
