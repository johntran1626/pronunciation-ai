"""'what was said'. Read the same Emissions WITHOUT forcing the expected text:
the most likely symbol per frame -> merge repeats -> drop blanks (greedy CTC decoding).
Bars set before running the new code.
"""
import io
import math
import re
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import torch

from backend.align import Emissions, emissions, vocab
from backend.g2p import expected_phonemes
from backend.recognize import recognize

BDL = Path("data/cmu_arctic/cmu_us_bdl_arctic")   # native US English speaker (CMU ARCTIC)
ZEROTH = Path("data/zeroth/data/test-00000-of-00001.parquet")


# ---------- the decoding rule, on hand-made emissions (exact, fast) ----------
def fake_emissions(frames, p=0.9):
    """frames = symbols per 20 ms frame ('_' = blank) -> Emissions where that symbol has probability p."""
    v = vocab()
    lp = torch.full((len(frames), len(v)), math.log((1 - p) / (len(v) - 1)))
    for i, s in enumerate(frames):
        lp[i, v["<pad>" if s == "_" else s]] = math.log(p)
    return Emissions(lp, 0.02, len(frames) * 0.02)


def test_repeats_merge_and_blanks_drop():
    got = recognize(fake_emissions(["_", "k", "k", "_", "æ", "t", "t", "_"]))
    assert [r["symbol"] for r in got] == ["k", "æ", "t"]
    assert [(r["start"], r["end"]) for r in got] == [(0.02, 0.06), (0.08, 0.10), (0.10, 0.14)]
    assert all(r["conf"] == pytest.approx(0.9, abs=1e-3) for r in got)


def test_a_blank_between_two_same_symbols_keeps_both():
    # 'n _ n' is two n's (안녕 has n n); 'n n' with no blank is one n
    assert [r["symbol"] for r in recognize(fake_emissions(["n", "_", "n"]))] == ["n", "n"]
    assert [r["symbol"] for r in recognize(fake_emissions(["n", "n"]))] == ["n"]


def test_special_tokens_are_not_phonemes():
    assert recognize(fake_emissions(["<s>", "a", "</s>", "<unk>"])) == [
        {"symbol": "a", "start": 0.02, "end": 0.04, "conf": pytest.approx(0.9, abs=1e-3)}]


# ---------- real audio ----------
def test_silence_gives_no_phonemes():
    assert recognize(emissions(np.zeros(16000, dtype="float32"), 16000)) == []


def _well_formed(heard, duration):
    assert heard, "heard nothing"
    assert all(s["symbol"] in vocab() for s in heard)
    assert all(0 <= s["start"] < s["end"] <= duration + 0.03 for s in heard)
    assert [s["start"] for s in heard] == sorted(s["start"] for s in heard)
    assert all(0 <= s["conf"] <= 1 for s in heard)


@pytest.mark.skipif(not BDL.exists(), reason="CMU ARCTIC not downloaded")
def test_native_english_hears_about_the_right_number_of_sounds():
    """A native speaker reading the prompt: the recognizer should hear roughly as many sounds as G2P expects
    (within 30%). Accuracy per sound is measured later, with your sequence_align.py and the eval."""
    prompts = dict(re.findall(r'\( (arctic_a\d+) "(.*)" \)', (BDL / "etc" / "txt.done.data").read_text()))
    for utt in ["arctic_a0001", "arctic_a0002", "arctic_a0003", "arctic_a0004", "arctic_a0005"]:
        audio, sr = sf.read(BDL / "wav" / f"{utt}.wav", dtype="float32")
        heard = recognize(emissions(audio, sr))
        _well_formed(heard, len(audio) / sr)
        n_expected = sum(len(w["phonemes"]) for w in expected_phonemes(prompts[utt], "en"))
        assert 0.7 * n_expected <= len(heard) <= 1.3 * n_expected, (utt, len(heard), n_expected)


@pytest.mark.skipif(not ZEROTH.exists(), reason="Zeroth not downloaded")
def test_korean_recognition_is_well_formed():
    import pyarrow.parquet as pq
    row = next(pq.ParquetFile(ZEROTH).iter_batches(batch_size=1)).to_pylist()[0]
    audio, sr = sf.read(io.BytesIO(row["audio"]["bytes"]), dtype="float32")
    _well_formed(recognize(emissions(audio, sr)), len(audio) / sr)
