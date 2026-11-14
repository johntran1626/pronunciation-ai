"""Scoring v1 (conservative, no soft hints). Hand-made emissions: no model, fast.

Only the MVP confusion pairs can turn red. A pair turns red only if a tuned threshold exists for it AND
it is enabled; with no thresholds file, nothing is ever red (safe default).
"""
import math

import torch

from backend.align import Emissions, vocab
from backend.scoring import candidates, score_words


def fake_em(frames, p=0.9):
    """frames = one symbol per 20 ms frame ('_' = blank) -> Emissions with that symbol at probability p."""
    v = vocab()
    lp = torch.full((len(frames), len(v)), math.log((1 - p) / (len(v) - 1)))
    for i, s in enumerate(frames):
        lp[i, v["<pad>" if s == "_" else s]] = math.log(p)
    return Emissions(lp, 0.02, len(frames) * 0.02)


def phone(ipa, start, end, op="match", heard=None, extra=(), extra_conf=()):
    return {"ipa": ipa, "start": start, "end": end, "conf": 0.5, "target_symbol": ipa, "op": op,
            "heard": ipa if heard is None and op == "match" else heard,
            "extra_after": list(extra), "extra_after_conf": list(extra_conf)}


def right_said_as(first_sym, op, heard):
    """'right' where the first 3 frames contain first_sym; aɪ and t are clean."""
    em = fake_em([first_sym] * 3 + ["aɪ"] * 3 + ["t"] * 2)
    words = [{"word": "right", "pron": "R AY1 T", "start": 0.0, "end": 0.16, "phonemes": [
        phone("ɹ", 0.0, 0.06, op, heard), phone("aɪ", 0.06, 0.12), phone("t", 0.12, 0.16)]}]
    return em, words


R_AS_L_ON = {"pairs": {"r_as_l": {"variant": "A", "margin": 0.5, "enabled": True}}}


# ---------- which sounds are checked ----------
def test_only_mvp_targets_are_candidates():
    em, words = right_said_as("ɹ", "match", "ɹ")
    cands = candidates(em, words, "en")
    # ɹ is an MVP target; aɪ and t are not. The final t is also checked for an extra vowel after it ("right-eu").
    assert [(c["phoneme_index"], c["pair"]) for c in cands] == [(0, "r_as_l"), (2, "extra_vowel")]


def test_flap_t_is_never_checked():
    em = fake_em(["s", "ɪ", "ɾ", "i", "z"])
    words = [{"word": "cities", "pron": "", "start": 0.0, "end": 0.1, "phonemes": [
        phone("s", 0.0, 0.02), phone("ɪ", 0.02, 0.04), phone("t", 0.04, 0.06, "sub", "ɾ"),
        phone("iː", 0.06, 0.08, "sub", "i"), phone("z", 0.08, 0.1)]}]
    assert "t" not in [words[0]["phonemes"][c["phoneme_index"]]["ipa"] for c in candidates(em, words, "en")]


def test_korean_has_no_red_checks_in_v1():
    em = fake_em(["m", "ɔ"])
    words = [{"word": "머", "pron": "머", "start": 0, "end": 0.04, "phonemes": [phone("m", 0, 0.02), phone("ʌ", 0.02, 0.04)]}]
    assert candidates(em, words, "ko") == []


# ---------- the evidence ----------
def test_margin_is_positive_when_the_wrong_sound_dominates():
    em, words = right_said_as("l", "sub", "l")
    [c] = [c for c in candidates(em, words, "en") if c["pair"] == "r_as_l"]
    assert c["margin"] > 0.8 and c["heard_agrees"] is True


def test_margin_is_negative_when_the_target_dominates():
    em, words = right_said_as("ɹ", "match", "ɹ")
    [c] = [c for c in candidates(em, words, "en") if c["pair"] == "r_as_l"]
    assert c["margin"] < -0.8 and c["heard_agrees"] is False


def test_extra_vowel_after_a_final_consonant_is_a_candidate():
    em = fake_em(["b", "ʌ", "s", "ə"])
    words = [{"word": "bus", "pron": "B AH1 S", "start": 0, "end": 0.06, "phonemes": [
        phone("b", 0, 0.02), phone("ʌ", 0.02, 0.04), phone("s", 0.04, 0.06, extra=["ə"], extra_conf=[0.8])]}]
    [c] = [c for c in candidates(em, words, "en") if c["pair"] == "extra_vowel"]
    assert c["phoneme_index"] == 2 and c["margin"] == 0.8 and c["heard_agrees"] is True


# ---------- the verdict ----------
def test_no_thresholds_means_nothing_is_red():
    em, words = right_said_as("l", "sub", "l")
    out = score_words(em, words, "en", thresholds={"pairs": {}})
    assert out[0]["status"] == "green"
    assert all(p["status"] == "green" for p in out[0]["phonemes"])


def test_clear_error_turns_red_and_says_what_was_produced():
    em, words = right_said_as("l", "sub", "l")
    out = score_words(em, words, "en", thresholds=R_AS_L_ON)
    r = out[0]["phonemes"][0]
    assert r["status"] == "red" and r["pair"] == "r_as_l" and r["produced"] == "l"
    assert out[0]["status"] == "red"


def test_correct_r_stays_green():
    em, words = right_said_as("ɹ", "match", "ɹ")
    assert score_words(em, words, "en", thresholds=R_AS_L_ON)[0]["status"] == "green"


def test_variant_b_also_needs_the_recognizer_to_agree():
    em, words = right_said_as("l", "match", "ɹ")   # posteriors say L, but the free recognizer wrote ɹ
    b = {"pairs": {"r_as_l": {"variant": "B", "margin": 0.5, "enabled": True}}}
    assert score_words(em, words, "en", thresholds=b)[0]["status"] == "green"


def test_disabled_pair_is_never_red():
    em, words = right_said_as("l", "sub", "l")
    off = {"pairs": {"r_as_l": {"variant": "A", "margin": 0.5, "enabled": False}}}
    assert score_words(em, words, "en", thresholds=off)[0]["status"] == "green"


def test_input_is_not_changed():
    em, words = right_said_as("l", "sub", "l")
    before = repr(words)
    score_words(em, words, "en", thresholds=R_AS_L_ON)
    assert repr(words) == before


# ---------- variant F (F3 tie-breaker) ----------
from backend.scoring import is_red  # noqa: E402

L_AS_R_F = {"pairs": {"l_as_r": {"variant": "F", "margin": 0.8, "m_lo": 0.0, "dip": -1.0, "enabled": True}}}


def test_variant_f_borderline_needs_low_f3():
    base = dict(pair="l_as_r", heard_agrees=False)
    assert is_red(dict(base, margin=0.3, f3_dip=-2.0), L_AS_R_F)
    assert not is_red(dict(base, margin=0.3, f3_dip=0.5), L_AS_R_F)
    assert not is_red(dict(base, margin=0.3), L_AS_R_F)              # F3 not measured -> only the sure path
    assert is_red(dict(base, margin=0.9), L_AS_R_F)


def test_score_words_without_audio_never_uses_f3():
    em, words = right_said_as("ɹ", "match", "ɹ")
    words[0]["phonemes"][0]["ipa"] = "l"                             # target L, audio frames say ɹ (margin ~ +0.9)
    out = score_words(em, words, "en", thresholds=L_AS_R_F)
    assert out[0]["phonemes"][0]["status"] == "red"                  # sure path works with no audio


# ---------- the tie-breaker can use another feature (frication for V/B) ----------
V_AS_B_F = {"pairs": {"v_as_b": {"variant": "F", "margin": 0.8, "m_lo": 0.0, "dip": -20.0, "feature": "fric",
                                 "enabled": True}}}


def test_variant_f_uses_the_named_feature():
    base = dict(pair="v_as_b", heard_agrees=False, margin=0.3)
    assert is_red(dict(base, fric=-30.0), V_AS_B_F)       # borderline + little hiss: B-like -> red
    assert not is_red(dict(base, fric=-10.0), V_AS_B_F)   # borderline + hiss: V-like -> green
    assert not is_red(dict(base, f3_dip=-30.0), V_AS_B_F)  # the OTHER feature must not be used
