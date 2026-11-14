"""Did the learner actually say this sentence / this word?

Found in manual testing: silence, a beep, nonsense or skipped words all came out GREEN, because forced
alignment always places the expected sounds and scoring only asked 'was this R heard as L?'.
"""
import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from backend.app import app
from backend.match import (finalize, is_not_heard, mark_unchecked, sentence_check, sentence_features,
                           word_features)

client = TestClient(app)

SENTENCE_T = {"enabled": True, "min_heard": 0.4, "min_conf": 0.2}
WORD_T = {"enabled": True, "max_heard": 0.34, "max_conf": 0.3, "min_sounds": 2}
MATCH_T = {"en": {"sentence": SENTENCE_T, "word": WORD_T},
           "ko": {"sentence": SENTENCE_T, "word": {**WORD_T, "enabled": False}}}
SOUND_T = {"pairs": {"r_as_l": {"enabled": True}, "l_as_r": {"enabled": False}}}


def word(name, ops, confs, ipas=None, status="green"):
    ipas = ipas or ["x"] * len(ops)
    return {"word": name, "status": status, "phonemes": [
        {"ipa": i, "op": o, "conf": c, "status": status} for i, o, c in zip(ipas, ops, confs)]}


# ---------- features ----------
def test_word_features_count_what_was_heard():
    f = word_features(word("balls", ["match", "del", "del", "sub"], [0.4, 0.1, 0.1, 0.2]))
    assert f["n"] == 4 and f["heard"] == 0.25 and f["missing"] == 0.5
    assert f["conf"] == pytest.approx(0.2)


def test_sentence_features_pool_all_sounds():
    words = [word("a", ["match", "match"], [0.8, 0.6]), word("b", ["del", "match"], [0.0, 0.6])]
    f = sentence_features(words)
    assert f["heard"] == 0.75 and f["conf"] == pytest.approx(0.5) and f["n"] == 4


# ---------- the sentence check ----------
def test_sentence_passes_when_enough_is_heard():
    words = [word("a", ["match", "match", "sub"], [0.8, 0.7, 0.5])]
    assert sentence_check(words, n_heard=3, t=SENTENCE_T) == (True, None)


def test_nothing_heard_is_no_speech():
    words = [word("a", ["del", "del"], [0.0, 0.0])]
    assert sentence_check(words, n_heard=0, t=SENTENCE_T) == (False, "no_speech")


def test_speech_that_doesnt_fit_is_a_mismatch():
    words = [word("a", ["sub", "del", "match"], [0.1, 0.05, 0.3])]
    assert sentence_check(words, n_heard=5, t=SENTENCE_T) == (False, "mismatch")


def test_disabled_sentence_check_always_passes():
    words = [word("a", ["del"], [0.0])]
    assert sentence_check(words, n_heard=0, t={**SENTENCE_T, "enabled": False}) == (True, None)


# ---------- the word check ----------
def test_not_heard_needs_both_few_sounds_heard_and_low_confidence():
    assert is_not_heard({"n": 4, "heard": 0.25, "conf": 0.2}, WORD_T)
    assert not is_not_heard({"n": 4, "heard": 0.25, "conf": 0.5}, WORD_T)   # confident: probably said, accented
    assert not is_not_heard({"n": 4, "heard": 0.75, "conf": 0.1}, WORD_T)   # most sounds heard
    assert not is_not_heard({"n": 1, "heard": 0.0, "conf": 0.0}, WORD_T)    # too short to judge
    assert not is_not_heard({"n": 4, "heard": 0.0, "conf": 0.0}, {**WORD_T, "enabled": False})


def test_finalize_turns_a_missing_word_red_and_marks_what_was_checked():
    words = [word("Clubs", ["match"] * 5, [0.9] * 5),
             word("balls", ["match", "del", "del", "del"], [0.3, 0.1, 0.1, 0.1])]
    out = finalize(words, "en", SOUND_T, MATCH_T)
    # Passing "was the word heard?" is NOT "sounded right": no sound check looked -> plain
    assert out[0]["status"] == "unchecked" and not any(p["checked"] for p in out[0]["phonemes"])
    assert all(p["status"] == "unchecked" for p in out[0]["phonemes"])
    assert out[1]["status"] == "red" and out[1]["not_heard"] is True
    assert all(p["status"] == "red" and p["pair"] == "word_not_heard" for p in out[1]["phonemes"])
    assert words[1]["status"] == "green"  # input not changed


def test_without_a_live_check_sounds_are_unchecked_not_green():
    # Korean: word check off, no sound checks -> nothing may claim to be green
    out = finalize([word("같이", ["match"] * 4, [0.9] * 4, ipas=["k", "a", "tɕʰ", "i"])], "ko", SOUND_T, MATCH_T)
    assert out[0]["status"] == "unchecked"
    assert all(p["status"] == "unchecked" and p["checked"] is False for p in out[0]["phonemes"])


def test_only_sounds_with_a_live_check_count_as_checked():
    t = {**MATCH_T, "en": {**MATCH_T["en"], "word": {**WORD_T, "enabled": False}}}
    out = finalize([word("from", ["match"] * 4, [0.9] * 4, ipas=["f", "ɹ", "ʌ", "m"])], "en", SOUND_T, t)
    assert [p["checked"] for p in out[0]["phonemes"]] == [False, True, False, False]  # only the R (r_as_l live)
    assert [p["status"] for p in out[0]["phonemes"]] == ["unchecked", "green", "unchecked", "unchecked"]
    assert out[0]["status"] == "green"


def test_word_check_on_still_only_greens_sounds_a_sound_check_passed():
    # (the "Clubs ... memories" sentence): with the word check ON, only the R in "from" is green
    out = finalize([word("from", ["match"] * 4, [0.9] * 4, ipas=["f", "ɹ", "ʌ", "m"])], "en", SOUND_T, MATCH_T)
    assert [p["status"] for p in out[0]["phonemes"]] == ["unchecked", "green", "unchecked", "unchecked"]
    assert [p["checked"] for p in out[0]["phonemes"]] == [False, True, False, False]
    assert out[0]["status"] == "green" and out[0]["not_heard"] is False


def test_mark_unchecked_clears_every_verdict():
    out = mark_unchecked([word("a", ["match"], [0.9], status="red")])
    assert out[0]["status"] == "unchecked" and out[0]["phonemes"][0]["status"] == "unchecked"


# ---------- through the API (uses backend/match_thresholds.json, written by eval/match_tune.py) ----------
def wav_bytes(x, sr=16000):
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="WAV")
    return buf.getvalue()


def post(audio, text, lang):
    return client.post("/analyze", files={"audio": ("a.wav", audio, "audio/wav")}, data={"text": text, "lang": lang})


@pytest.mark.parametrize("lang,text", [("en", "From now on we're pals."), ("ko", "강아지가 용변을 보도록")])
def test_a_beep_is_rejected_not_green(lang, text):
    t = np.arange(48000) / 16000
    body = post(wav_bytes(0.3 * np.sin(2 * np.pi * 440 * t)), text, lang).json()
    assert body["matched"] is False and body["reason"] in ("no_speech", "mismatch")
    assert all(w["status"] == "unchecked" for w in body["words"])
    assert all(d["status"] == "unchecked" for w in body["words"] for d in w["display"])


def test_silence_is_rejected():
    body = post(wav_bytes(np.zeros(32000)), "From now on we're pals.", "en").json()
    assert body["matched"] is False


def test_api_says_which_checks_are_live():
    t = np.arange(48000) / 16000
    body = post(wav_bytes(0.3 * np.sin(2 * np.pi * 440 * t)), "From now on we're pals.", "en").json()
    assert "r_as_l" in body["checks"]
    assert isinstance(body["checks"], list)
