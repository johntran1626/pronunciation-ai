"""A trained detector (variant "D") can go live in backend/thresholds.json.

Variant D = a logistic-regression model (backend/detector.py) + a probability threshold. The app must score a
sound with exactly the numbers the eval scored it with: margin, heard_agrees, and backend/features.py's 13
measurements of the sound's window. Without audio those can't be measured, so D is never red (safe default).
"""
import json

import backend.scoring as scoring
from backend.detector import FEATURE_NAMES
from backend.scoring import is_red, score_words
from tests.test_scoring import fake_em, phone

# A toy model: only the margin counts (weight 10 on a z-scored margin with mean 0, std 1).
TOY = {"names": list(FEATURE_NAMES), "mean": [0.0] * len(FEATURE_NAMES), "std": [1.0] * len(FEATURE_NAMES),
       "w": [10.0] + [0.0] * (len(FEATURE_NAMES) - 1), "b": 0.0}
D_ON = {"pairs": {"extra_vowel": {"variant": "D", "model": TOY, "threshold": 0.9, "enabled": True}}}
NO_X = {n: None for n in FEATURE_NAMES[2:]}


def bus(conf):
    """'bus' with an extra vowel heard after the s at this confidence (none if conf is None)."""
    em = fake_em(["b", "ʌ", "s", "ə"])
    extra = dict(extra=["ə"], extra_conf=[conf]) if conf is not None else {}
    words = [{"word": "bus", "pron": "B AH1 S", "start": 0, "end": 0.08, "phonemes": [
        phone("b", 0, 0.02), phone("ʌ", 0.02, 0.04), phone("s", 0.04, 0.06, **extra)]}]
    return em, words


def fake_features(monkeypatch, calls):
    def sf(audio, sr, words, slots=None):
        calls.append(slots)
        return {s: dict(NO_X, heard_nothing=0) for s in slots}
    monkeypatch.setattr(scoring, "sound_features", sf)


# ---------- is_red ----------
def test_variant_d_red_when_the_model_probability_is_over_the_threshold():
    t = D_ON["pairs"]["extra_vowel"]
    assert is_red(dict(pair="extra_vowel", margin=0.8, heard_agrees=True, **NO_X), D_ON)       # p ~ 1.0
    assert not is_red(dict(pair="extra_vowel", margin=-1.0, heard_agrees=False, **NO_X), D_ON)  # p ~ 0.0
    assert t["threshold"] == 0.9


def test_variant_d_without_measurements_is_never_red():
    # no audio -> the candidate has no feature keys at all -> green, however sure the recognizer is
    assert not is_red(dict(pair="extra_vowel", margin=0.99, heard_agrees=True), D_ON)


def test_disabled_variant_d_is_never_red():
    off = {"pairs": {"extra_vowel": {**D_ON["pairs"]["extra_vowel"], "enabled": False}}}
    assert not is_red(dict(pair="extra_vowel", margin=0.99, heard_agrees=True, **NO_X), off)


# ---------- score_words ----------
def test_score_words_measures_only_detector_slots_and_turns_red(monkeypatch):
    calls = []
    fake_features(monkeypatch, calls)
    em, words = bus(0.8)
    out = score_words(em, words, "en", thresholds=D_ON, audio=[0.0] * 1600, sr=16000)
    s = out[0]["phonemes"][2]
    assert s["status"] == "red" and s["pair"] == "extra_vowel" and s["produced"] == "extra vowel after"
    assert calls == [[(0, 2)]]           # measured once, only the word-final s


def test_score_words_green_when_no_vowel_was_heard(monkeypatch):
    fake_features(monkeypatch, [])
    em, words = bus(None)
    out = score_words(em, words, "en", thresholds=D_ON, audio=[0.0] * 1600, sr=16000)
    assert out[0]["status"] == "green"


def test_score_words_without_audio_never_measures_and_stays_green(monkeypatch):
    calls = []
    fake_features(monkeypatch, calls)
    em, words = bus(0.8)
    assert score_words(em, words, "en", thresholds=D_ON)[0]["status"] == "green"
    assert calls == []


def test_no_detector_pair_live_means_no_measuring(monkeypatch):
    calls = []
    fake_features(monkeypatch, calls)
    em, words = bus(0.8)
    score_words(em, words, "en", thresholds={"pairs": {}}, audio=[0.0] * 1600, sr=16000)
    assert calls == []


# ---------- the eval scores a cached row the same way ----------
def test_eval_flag_t_scores_a_cached_row_with_the_detector():
    from eval.run import flag_t
    t = D_ON["pairs"]["extra_vowel"]
    row = {"margin": "0.8", "heard_agrees": "1", "op": "match", **{f"x_{n}": "" for n in FEATURE_NAMES[3:]}}
    assert flag_t(row, t) is True
    assert flag_t({**row, "margin": "-1.0", "heard_agrees": "0"}, t) is False


# ---------- adopting and keeping it ----------
def test_adopt_copies_the_tuned_model_and_threshold(tmp_path):
    from eval.detectors import adopt
    res = {"pairs": {"extra_vowel": {"cap": 0.005, "model": TOY, "threshold": 0.96, "enabled": True,
                                     "test (korean)": {"precision": 0.53}}}}
    th = tmp_path / "thresholds.json"
    th.write_text(json.dumps({"source": "x", "pairs": {"r_as_l": {"variant": "B", "margin": -1.0, "enabled": True},
                                                       "extra_vowel": {"variant": "B", "margin": 0.5,
                                                                       "enabled": False}}}))
    adopt("extra_vowel", res, th)
    pairs = json.loads(th.read_text())["pairs"]
    ev = pairs["extra_vowel"]
    assert ev["variant"] == "D" and ev["model"] == TOY and ev["threshold"] == 0.96 and ev["enabled"] is True
    assert pairs["r_as_l"] == {"variant": "B", "margin": -1.0, "enabled": True}   # other pairs untouched


def test_adopt_refuses_a_pair_that_failed_d15(tmp_path):
    import pytest
    from eval.detectors import adopt
    res = {"pairs": {"th_as_s": {"model": TOY, "threshold": 0.9, "enabled": False}}}
    th = tmp_path / "thresholds.json"
    th.write_text(json.dumps({"pairs": {}}))
    with pytest.raises(SystemExit):
        adopt("th_as_s", res, th)


def test_eval_run_keeps_adopted_detectors_when_it_rewrites_thresholds():
    from eval.run import thresholds_payload
    app = {"r_as_l": {"cap": 0.005, "variant": "B", "margin": -1.0, "enabled": True, "test (korean)": {}},
           "extra_vowel": {"cap": 0.005, "variant": "B", "margin": 0.497, "enabled": False}}
    old = {"pairs": {"extra_vowel": D_ON["pairs"]["extra_vowel"]}}
    out = thresholds_payload(app, old)["pairs"]
    assert out["extra_vowel"] == D_ON["pairs"]["extra_vowel"]
    assert out["r_as_l"] == {"cap": 0.005, "variant": "B", "margin": -1.0, "enabled": True}
