"""Korean "did you say it?" in /analyze: the sentence check and the word check read the Korean-trained listener.

Measured in eval/korean_match.py (results/korean_match.json): with the Korean-trained listener both checks passed
their native bars; the main listener's word check caught almost nothing. Both checks grade.

Unit tests use made-up evidence (no model). The live tests run the models on the Zeroth native recording in
tests/fixtures (CC BY 4.0).
"""
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.match import finalize, korean_listener_on, sentence_check

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "zeroth_126_003_2058.wav"
NATIVE_TEXT = "강아지가 용변을 보도록 유도하는 말을 가르칠 수도 있다"
OTHER_TEXT = "오늘은 날씨가 맑고 바람이 시원해서 공원에 사람이 많았다"

KO_SENTENCE = {"enabled": True, "listener": "ko", "min_heard": 0.58, "min_conf": 0.0}
KO_WORD = {"enabled": True, "listener": "ko", "min_sounds": 3, "max_heard": 0.2, "max_conf": 0.14}
MATCH_T = {"ko": {"sentence": KO_SENTENCE, "word": KO_WORD}}


def word(name, ops, confs):
    """A word as the MAIN listener sees it (its ops / confs are what match.py reads for English)."""
    return {"word": name, "status": "green", "phonemes": [
        {"ipa": "x", "op": o, "conf": c, "status": "green"} for o, c in zip(ops, confs)]}


def ev(n, heard, conf):
    return {"n": n, "heard": heard, "missing": 0.0, "conf": conf}


HEARD_BY_MAIN = [word("가", ["match"] * 3, [0.9] * 3), word("나", ["match"] * 3, [0.9] * 3)]


# ---------- which listener ----------
def test_korean_rules_marked_ko_use_the_korean_listener():
    assert korean_listener_on(MATCH_T, "ko")
    assert not korean_listener_on(MATCH_T, "en")
    assert not korean_listener_on({"ko": {"sentence": {"enabled": True, "min_heard": 0.0, "min_conf": 0.0},
                                          "word": {"enabled": False}}}, "ko")


def test_the_shipped_korean_rules_are_the_measured_ones():
    shipped = json.loads((ROOT / "backend" / "match_thresholds.json").read_text())["ko"]
    measured = json.loads((ROOT / "results" / "korean_match.json").read_text(encoding="utf-8"))
    s, w = shipped["sentence"], shipped["word"]
    assert s["enabled"] and s["listener"] == "ko" and w["enabled"] and w["listener"] == "ko"
    picked = measured["listeners"]["ko"]
    assert {k: s[k] for k in ("min_heard", "min_conf")} == picked["sentence"]["thresholds"]
    assert {k: w[k] for k in ("min_sounds", "max_heard", "max_conf")} == picked["word"]["thresholds"]


# ---------- 1. the sentence: the Korean listener's evidence decides, not the main listener's ----------
def test_sentence_is_rejected_on_the_korean_listeners_evidence():
    evidence = {"per": [ev(3, 0.3, 0.5), ev(3, 0.4, 0.5)], "n_heard": 12}
    assert sentence_check(HEARD_BY_MAIN, 20, KO_SENTENCE, evidence) == (False, "mismatch")


def test_sentence_passes_on_the_korean_listeners_evidence():
    evidence = {"per": [ev(3, 0.9, 0.5), ev(3, 0.6, 0.5)], "n_heard": 12}
    assert sentence_check(HEARD_BY_MAIN, 20, KO_SENTENCE, evidence) == (True, None)


def test_the_korean_listener_hearing_nothing_is_no_speech():
    evidence = {"per": [ev(3, 0.0, 0.0), ev(3, 0.0, 0.0)], "n_heard": 0}
    assert sentence_check(HEARD_BY_MAIN, 20, KO_SENTENCE, evidence) == (False, "no_speech")


def test_no_korean_evidence_means_no_verdict_against_the_learner():
    assert sentence_check(HEARD_BY_MAIN, 20, KO_SENTENCE, None) == (True, None)


# ---------- 2. each word ----------
def test_a_word_the_korean_listener_did_not_hear_turns_red():
    per = [ev(3, 0.9, 0.6), ev(4, 0.0, 0.1)]
    out = finalize(HEARD_BY_MAIN, "ko", {}, MATCH_T, word_evidence=per)
    assert [w["not_heard"] for w in out] == [False, True]
    assert out[1]["status"] == "red" and {p["pair"] for p in out[1]["phonemes"]} == {"word_not_heard"}
    assert out[0]["status"] == "unchecked"            # passing the word check never makes a word green


def test_the_main_listeners_features_do_not_flag_korean_words():
    missed_by_main = [word("가", ["del"] * 3, [0.0] * 3)]
    out = finalize(missed_by_main, "ko", {}, MATCH_T, word_evidence=[ev(3, 0.9, 0.6)])
    assert out[0]["not_heard"] is False


def test_a_short_word_is_never_flagged():
    out = finalize(HEARD_BY_MAIN, "ko", {}, MATCH_T, word_evidence=[ev(2, 0.0, 0.0), ev(3, 0.0, 0.0)])
    assert [w["not_heard"] for w in out] == [False, True]


def test_no_korean_evidence_flags_no_word():
    out = finalize(HEARD_BY_MAIN, "ko", {}, MATCH_T, word_evidence=None)
    assert not any(w["not_heard"] for w in out)


def test_evidence_that_does_not_line_up_with_the_words_is_ignored():
    out = finalize(HEARD_BY_MAIN, "ko", {}, MATCH_T, word_evidence=[ev(3, 0.0, 0.0)])
    assert not any(w["not_heard"] for w in out)


# ---------- the tuning script for the main listener keeps the Korean-listener rules ----------
def test_match_tune_keeps_korean_rules_that_use_the_korean_listener():
    from eval.match_tune import keep_korean_listener_rules
    old = {"en": {}, "ko": {"sentence": KO_SENTENCE, "word": KO_WORD}}
    new = {"en": {"x": 1}, "ko": {"sentence": {"enabled": True, "min_heard": 0.0, "min_conf": 0.0},
                                  "word": {"enabled": False}}}
    assert keep_korean_listener_rules(old, new) == {"en": {"x": 1}, "ko": old["ko"]}
    plain_old = {"ko": {"sentence": {"enabled": True, "min_heard": 0.0}, "word": {"enabled": False}}}
    assert keep_korean_listener_rules(plain_old, new) == new


# ---------- the real models, through /analyze ----------
def _analyze(text):
    from backend.app import app
    return TestClient(app).post("/analyze", files={"audio": ("a.wav", FIXTURE.read_bytes(), "audio/wav")},
                                data={"text": text, "lang": "ko"}).json()


def test_live_a_native_reading_matches_with_no_word_flagged():
    body = _analyze(NATIVE_TEXT)
    assert body["matched"] is True
    assert {"sentence_match", "word_heard"} <= set(body["checks"])
    assert not any(w["not_heard"] for w in body["words"])


def test_live_a_different_sentence_is_rejected():
    body = _analyze(OTHER_TEXT)
    assert body["matched"] is False and body["reason"] == "mismatch"
    assert all(w["status"] == "unchecked" for w in body["words"])


def test_live_a_word_that_was_not_said_turns_red():
    # The word check catches about half of swapped words (results/korean_match.json: 230/457), so this swap was
    # picked because it is caught here; 용변을 -> 자동차를 on this recording, for one, is not.
    body = _analyze(NATIVE_TEXT.replace("유도하는", "시원해서"))
    assert body["matched"] is True
    flagged = [w for w in body["words"] if w["not_heard"]]
    assert [w["word"] for w in flagged] == ["시원해서"]
    assert flagged[0]["status"] == "red" and {p["pair"] for p in flagged[0]["phonemes"]} == {"word_not_heard"}
