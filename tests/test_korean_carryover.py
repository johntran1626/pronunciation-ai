"""Tests for eval/korean_carryover.py: English sounds carried into Korean as simulated errors."""
from eval.korean_carryover import auc, flap_spot, intervocalic, stop_groups, survives


def test_auc():
    assert auc(neg=[1, 2], pos=[3, 4]) == 1.0      # every error scores above every correct sound
    assert auc(neg=[3, 4], pos=[1, 2]) == 0.0
    assert auc(neg=[1, 1], pos=[1, 1]) == 0.5      # ties = coin flip
    assert auc(neg=[], pos=[1]) is None


def test_flap_spot_is_t_or_d_between_a_vowel_and_an_unstressed_vowel():
    assert flap_spot(["B", "EH1", "T", "ER0"], 2)          # better
    assert flap_spot(["S", "IH1", "T", "IY0"], 2)          # city
    assert not flap_spot(["AH0", "T", "AE1", "K"], 1)      # attack: next vowel is stressed
    assert not flap_spot(["S", "T", "AA1", "P"], 1)        # stop: no vowel before


def test_intervocalic():
    assert intervocalic(["s", "a", "ɾ", "a", "ŋ"], 2)      # 사랑
    assert not intervocalic(["ɾ", "a"], 0)
    assert not intervocalic(["a", "l"], 1)


def test_stop_groups():
    rows = [dict(lang="en", cat="asp", initial="", vot="70"), dict(lang="en", cat="sp", initial="", vot="20"),
            dict(lang="en", cat="vcd", initial="", vot="15"), dict(lang="ko", cat="tense", initial="1", vot="25"),
            dict(lang="ko", cat="tense", initial="0", vot=""), dict(lang="ko", cat="lenis", initial="0", vot="40")]
    g = stop_groups(rows)
    assert g == {"en_asp": [70.0], "en_sp": [20.0], "en_vcd": [15.0], "ko_tense": [25.0]}  # blank VOT dropped


def test_survives_needs_both_aucs():
    assert survives(0.9, 0.85)
    assert not survives(0.9, 0.6)    # also flags the English controls: it's detecting the corpus
    assert not survives(0.7, 0.9)
    assert survives(0.9, None) is None  # no control: can't rule out the corpus confound
