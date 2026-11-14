"""backend/acoustics.py, F3 (third formant) for the R/L tie-breaker.

Synthetic vowels: a 120 Hz buzz (like vocal folds) passed through three resonators (like the mouth) at
known F1/F2/F3. Praat should find the F3 we put in.
"""
import math

import numpy as np

from backend.acoustics import Formants, f3_dip, f3_reference

SR = 16000


def _resonator(x, freq, bw=100.0):
    """Klatt-style 2nd-order resonator (a 'ringing' filter at freq Hz)."""
    c = -math.exp(-2 * math.pi * bw / SR)
    b = 2 * math.exp(-math.pi * bw / SR) * math.cos(2 * math.pi * freq / SR)
    a = 1 - b - c
    y = np.zeros_like(x)
    for n in range(len(x)):
        y[n] = a * x[n] + b * (y[n - 1] if n else 0) + c * (y[n - 2] if n > 1 else 0)
    return y


def vowel(f3, seconds=0.4, f1=500, f2=1500):
    """F4/F5 are included because Praat looks for 5 formants below 5000 Hz; with only 3 real ones it
    invents extra ones (a 3-formant test vowel measured F3 = 1806 Hz for a true 2500)."""
    buzz = np.zeros(int(seconds * SR))
    buzz[:: SR // 120] = 1.0
    y = buzz
    for f in (f1, f2, f3, 3500, 4500):
        y = _resonator(y, f)
    return (0.3 * y / np.abs(y).max()).astype(np.float32)


def test_f3_of_a_synthetic_vowel():
    fm = Formants(vowel(2500), SR)
    assert abs(fm.f3(0.1, 0.3) - 2500) < 150


def test_low_f3_like_english_r_is_lower():
    audio = np.concatenate([vowel(2600), vowel(1700)])   # "L-like" then "R-like"
    fm = Formants(audio, SR)
    assert fm.f3(0.45, 0.7) < fm.f3(0.1, 0.35) - 500


def test_silence_returns_none():
    fm = Formants(np.zeros(SR // 2, dtype=np.float32), SR)
    assert fm.f3(0.1, 0.3) is None


def test_reference_is_median_and_robust_spread():
    med, spread = f3_reference([2500, 2600, 2700, None])
    assert med == 2600 and abs(spread - 148.26) < 0.01       # 1.4826 x median absolute deviation (100 Hz)


def test_reference_needs_three_vowels():
    assert f3_reference([2500, 2600, None]) is None


def test_dip_math():
    assert f3_dip(1800, (2600, 200)) == -4.0
    assert f3_dip(None, (2600, 200)) is None
    assert f3_dip(1800, None) is None


# ---------- rl_f3: the R/L windows of a sentence (shared by the app and the eval) ----------
from backend.acoustics import rl_f3  # noqa: E402


def test_rl_f3_gives_an_r_like_dip_where_f3_drops():
    audio = np.concatenate([vowel(2500), vowel(2600), vowel(2400), vowel(1700)])
    p = lambda ipa, s, e: {"ipa": ipa, "start": s, "end": e}
    words = [{"word": "x", "phonemes": [p("a", 0.05, 0.35), p("e", 0.45, 0.75), p("o", 0.85, 1.15),
                                         p("l", 1.25, 1.55)]}]
    f3_of, ref = rl_f3(audio, SR, words)
    assert set(f3_of) == {(0, 3)}
    assert f3_dip(f3_of[(0, 3)], ref) < -2


# ---------- frication for V vs B ----------
from backend.acoustics import vb_features  # noqa: E402


def _noise(seconds, level):
    rng = np.random.default_rng(0)
    return (level * rng.standard_normal(int(seconds * SR))).astype(np.float32)


def test_vb_features_fricative_is_noisier_and_has_no_closure():
    # three vowels, then a V-like hiss, a vowel, then a B-like stop: 80 ms near-silence + a 5 ms burst
    stop = np.concatenate([_noise(0.08, 0.0005), _noise(0.005, 0.2)])
    audio = np.concatenate([vowel(2500), vowel(2500), vowel(2500), _noise(0.1, 0.03), vowel(2500), stop])
    p = lambda ipa, s, e: {"ipa": ipa, "start": s, "end": e}
    words = [{"word": "x", "phonemes": [p("a", 0.05, 0.35), p("e", 0.45, 0.75), p("o", 0.85, 1.15),
                                         p("v", 1.2, 1.3), p("a", 1.35, 1.65), p("v", 1.7, 1.785)]}]
    feats = vb_features(audio, SR, words)
    hiss, closed = feats[(0, 3)], feats[(0, 5)]
    assert hiss["fric"] > closed["fric"] + 10      # dB: noise above 3 kHz all through the hiss
    assert closed["closure"] < hiss["closure"] - 10  # dB: the closed lips make a deep dip
    assert set(feats) == {(0, 3), (0, 5)}          # only [v] windows are measured


def test_vb_features_need_vowels_for_the_reference():
    p = lambda ipa, s, e: {"ipa": ipa, "start": s, "end": e}
    words = [{"word": "x", "phonemes": [p("v", 0.0, 0.1)]}]
    assert vb_features(_noise(0.2, 0.03), SR, words) == {(0, 0): {"fric": None, "closure": None}}


# ---------- the same hiss/closure numbers for TH, DH and F too ----------
def test_vb_features_can_measure_other_fricatives():
    stop = np.concatenate([_noise(0.08, 0.0005), _noise(0.005, 0.2)])
    audio = np.concatenate([vowel(2500), vowel(2500), vowel(2500), _noise(0.1, 0.03), vowel(2500), stop])
    p = lambda ipa, s, e: {"ipa": ipa, "start": s, "end": e}
    words = [{"word": "x", "phonemes": [p("a", 0.05, 0.35), p("e", 0.45, 0.75), p("o", 0.85, 1.15),
                                         p("ð", 1.2, 1.3), p("a", 1.35, 1.65), p("v", 1.7, 1.785)]}]
    assert set(vb_features(audio, SR, words)) == {(0, 5)}  # default unchanged: only [v]
    feats = vb_features(audio, SR, words, targets=("v", "ð", "θ", "f"))
    assert set(feats) == {(0, 3), (0, 5)}
    assert feats[(0, 3)]["fric"] > feats[(0, 5)]["fric"] + 10
