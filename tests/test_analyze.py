"""POST /analyze accepts a recording + the sentence and checks the input.
 Test audio is a made-up beep (no personal recordings)."""
import io

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def beep_wav(seconds, sr=16000):
    """A 440 Hz tone as WAV bytes, like a file the browser would upload."""
    t = np.arange(int(seconds * sr)) / sr
    buf = io.BytesIO()
    sf.write(buf, 0.3 * np.sin(2 * np.pi * 440 * t), sr, format="WAV")
    return buf.getvalue()


def post(audio_bytes, text="안녕하세요", lang="ko"):
    return client.post("/analyze", files={"audio": ("rec.wav", audio_bytes, "audio/wav")},
                       data={"text": text, "lang": lang})


def test_good_upload_returns_text_lang_and_duration():
    r = post(beep_wav(1.0))
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "안녕하세요"
    assert body["lang"] == "ko"
    assert abs(body["duration_s"] - 1.0) < 0.01


def test_too_long_recording_is_rejected():
    r = post(beep_wav(16.0))  # limit is 15 s (hosting limits)
    assert r.status_code == 400
    assert "15" in r.json()["detail"]


def test_unreadable_audio_is_rejected():
    r = post(b"this is not audio")
    assert r.status_code == 400


def test_empty_text_is_rejected():
    r = post(beep_wav(1.0), text="   ")
    assert r.status_code == 400


def test_unknown_language_is_rejected():
    r = post(beep_wav(1.0), lang="fr")
    assert r.status_code == 422  # FastAPI's own "input doesn't match the allowed values"


# ---------- /analyze runs G2P + alignment + recognition ----------
from pathlib import Path

import pytest

HKK = Path("data/l2arctic/HKK")


def test_good_upload_returns_words_with_times_and_what_was_heard():
    body = post(beep_wav(1.0)).json()           # 안녕하세요 on a beep: content is nonsense, the SHAPE is what we test
    [word] = body["words"]
    assert word["word"] == "안녕하세요" and word["pron"] == "안녕하세요"
    assert [p["ipa"] for p in word["phonemes"]] == ["a", "n", "n", "j", "ʌ", "ŋ", "h", "a", "s", "e", "j", "o"]
    assert all({"start", "end", "conf"} <= p.keys() for p in word["phonemes"])
    assert isinstance(body["heard"], list)       # a beep may be heard as nothing or as noise symbols


def test_text_with_no_words_is_rejected():
    r = post(beep_wav(1.0), text="?!")
    assert r.status_code == 400


def test_recording_too_short_for_the_sentence_is_rejected():
    r = post(beep_wav(0.2), text="Please call Stella and ask her to bring these things with her", lang="en")
    assert r.status_code == 400
    assert "too short" in r.json()["detail"]


@pytest.mark.skipif(not HKK.exists(), reason="L2-ARCTIC not downloaded")
def test_real_recording_end_to_end():
    text = (HKK / "transcript" / "arctic_a0020.txt").read_text().strip()
    r = post((HKK / "wav" / "arctic_a0020.wav").read_bytes(), text=text, lang="en")
    assert r.status_code == 200
    body = r.json()
    assert [w["word"] for w in body["words"]] == text.split()
    assert all(w["start"] < w["end"] for w in body["words"])
    assert len(body["heard"]) > 20


# ---------- each expected sound says what was heard ----------
def test_every_expected_sound_has_an_op():
    body = post(beep_wav(1.0)).json()
    assert all(p["op"] in ("match", "sub", "del") for w in body["words"] for p in w["phonemes"])
    assert isinstance(body["extra_at_start"], list)


@pytest.mark.skipif(not HKK.exists(), reason="L2-ARCTIC not downloaded")
def test_real_recording_shows_the_missing_l_in_balls():
    text = (HKK / "transcript" / "arctic_a0020.txt").read_text().strip()
    body = post((HKK / "wav" / "arctic_a0020.wav").read_bytes(), text=text, lang="en").json()
    balls = next(w for w in body["words"] if w["word"] == "balls")
    assert [(p["ipa"], p["op"]) for p in balls["phonemes"]] == [("b", "match"), ("ɔː", "sub"), ("l", "del"), ("z", "match")]


# ---------- the verdict ----------
def test_every_word_and_sound_has_a_verdict():
    # "unchecked" joined green/red (no live check looked at it, or the sentence didn't match)
    body = post(beep_wav(1.0)).json()
    assert all(w["status"] in ("green", "red", "unchecked") for w in body["words"])
    assert all(p["status"] in ("green", "red", "unchecked") for w in body["words"] for p in w["phonemes"])


def test_korean_is_never_red_in_v1():
    # Korean sound/word checks aren't validated on learners yet: never red. (This test once
    # expected GREEN on a beep, which was a flaw; a beep now isn't graded at all.)
    body = post(beep_wav(1.0)).json()
    assert all(w["status"] != "red" for w in body["words"])


# ---------- display segments ----------
def test_every_word_has_display_segments_that_spell_it():
    body = post(beep_wav(1.0)).json()
    for w in body["words"]:
        assert "".join(d["text"] for d in w["display"]) == w["word"]
        assert all(d["status"] in ("green", "red", "unchecked") for d in w["display"])
