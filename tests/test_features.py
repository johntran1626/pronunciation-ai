"""backend/features.py, the ONE shared feature list for every checked sound.

Synthetic recordings: vowel-like buzzes (tests/test_acoustics.py's vowel()), a hiss (white noise = a fricative),
and a stop (near-silence = closed lips, then a loud burst). The features must tell them apart in the right direction.
"""
import math

import numpy as np

from backend.features import MEASURED, sound_features
from tests.test_acoustics import SR, _noise, vowel


def p(ipa, s, e, op="match"):
    return {"ipa": ipa, "start": s, "end": e, "op": op}


def sentence():
    """0.0-1.2: three vowels (F1 450/500/550); 1.2-1.3 hiss; 1.3-1.7 vowel with a HIGH F1 (800);
    1.7-1.78 closure (near-silence), 1.78-1.8 burst; 1.8-2.1 vowel; then 0.2 s of silence."""
    stop = np.concatenate([_noise(0.08, 0.0005), _noise(0.02, 0.2)])
    audio = np.concatenate([vowel(2500, f1=450), vowel(2600, f1=500), vowel(2400, f1=550), _noise(0.1, 0.03),
                            vowel(2500, f1=800), stop, vowel(2500, f1=500, seconds=0.3),
                            np.zeros(int(0.2 * SR), dtype=np.float32)])
    words = [{"word": "x", "phonemes": [p("a", 0.05, 0.35), p("e", 0.45, 0.75), p("o", 0.85, 1.15),
                                         p("θ", 1.2, 1.3), p("ɪ", 1.35, 1.65), p("d", 1.7, 1.8, op="del"),
                                         p("a", 1.82, 2.08), p("s", 2.1, 2.2)]}]
    return audio, words


def test_the_measured_list_is_fixed():
    assert MEASURED == ("heard_nothing", "dur", "f1_z", "f2_z", "f3_z", "voiced", "hiss", "centroid", "closure",
                        "burst", "after_voiced", "no_formants", "no_reference")


def test_only_the_asked_slots_are_measured():
    audio, words = sentence()
    feats = sound_features(audio, SR, words, slots=[(0, 3), (0, 5)])
    assert set(feats) == {(0, 3), (0, 5)}
    assert set(feats[(0, 3)]) == set(MEASURED)


def test_hiss_vs_vowel_vs_stop():
    audio, words = sentence()
    f = sound_features(audio, SR, words, slots=[(0, 3), (0, 4), (0, 5)])
    hiss, vow, stop = f[(0, 3)], f[(0, 4)], f[(0, 5)]
    assert vow["voiced"] > 0.8 and hiss["voiced"] < 0.3          # a buzz is voiced, white noise is not
    assert hiss["hiss"] > stop["hiss"] + 10                       # dB of 3-7.5 kHz noise
    assert hiss["centroid"] > vow["centroid"] + 1.5               # kHz: noise is bright, a vowel is dark
    assert stop["closure"] < hiss["closure"] - 10                 # dB: closed lips = a deep dip
    assert stop["burst"] > hiss["burst"] + 10                     # dB jump in 5 ms when the lips pop open
    assert stop["heard_nothing"] == 1 and hiss["heard_nothing"] == 0


def test_formants_are_relative_to_this_recordings_vowels():
    audio, words = sentence()
    vow = sound_features(audio, SR, words, slots=[(0, 4)])[(0, 4)]
    assert vow["f1_z"] > 2          # F1 800 vs this speaker's ~500: a much lower tongue than usual
    assert vow["no_formants"] == 0 and vow["no_reference"] == 0
    hiss = sound_features(audio, SR, words, slots=[(0, 3)])[(0, 3)]
    assert hiss["no_formants"] == 1 and hiss["f1_z"] is None      # no voiced frame -> no formant, never a guess


def test_duration_is_relative_to_the_median_vowel():
    audio, words = sentence()
    hiss = sound_features(audio, SR, words, slots=[(0, 3)])[(0, 3)]
    assert abs(hiss["dur"] - math.log(0.1 / 0.3)) < 0.01         # 100 ms vs a 300 ms median vowel


def test_after_voiced_sees_what_follows_the_window():
    audio, words = sentence()
    f = sound_features(audio, SR, words, slots=[(0, 5), (0, 7)])
    assert f[(0, 5)]["after_voiced"] > 0.6      # the stop is followed by a vowel
    assert f[(0, 7)]["after_voiced"] == 0.0     # the last sound is followed by silence


def test_no_reference_with_fewer_than_three_vowels():
    audio = np.concatenate([vowel(2500), _noise(0.1, 0.03)])
    words = [{"word": "x", "phonemes": [p("a", 0.05, 0.35), p("θ", 0.4, 0.5)]}]
    f = sound_features(audio, SR, words, slots=[(0, 1)])[(0, 1)]
    assert f["no_reference"] == 1
    assert f["dur"] is None and f["hiss"] is None and f["closure"] is None and f["f1_z"] is None
    assert f["voiced"] is not None and f["centroid"] is not None   # absolute measures still work
