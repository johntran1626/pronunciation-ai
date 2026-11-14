"""GET /tts/timings = WHEN each word and sound happens in the native (Azure) clip, so the detail card
can play "Native" next to "You" for the same word or sound (backend/native.py + backend/app.py).

No test touches the network: the
"Azure reply" is one of our committed fixture recordings (a real native voice), and the cache folder is temporary.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import tts
from backend.g2p import expected_phonemes
from backend.limits import TTSLimiter

FIXTURES = __import__("pathlib").Path(__file__).with_name("fixtures")
EN = {"file": "cmu_slt_arctic_a0020.wav", "text": "Clubs and balls and cities grew to be only memories.", "lang": "en"}
KO = {"file": "zeroth_126_003_2058.wav", "text": "강아지가 용변을 보도록 유도하는 말을 가르칠 수도 있다", "lang": "ko"}


class FixtureFetch:
    """Fake Azure: answers every request with a real recording's bytes."""
    def __init__(self, name):
        self.audio = (FIXTURES / name).read_bytes()
        self.calls = 0

    def __call__(self, ssml):
        self.calls += 1
        return self.audio


def setup(monkeypatch, tmp_path, fx, limiter=None):
    fetch = FixtureFetch(fx["file"])
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tts, "azure_fetch", fetch)
    monkeypatch.setattr(app_module, "tts_limiter",
                        limiter or TTSLimiter(per_client=100, window_s=60, daily_chars=100_000))
    return fetch


client = TestClient(app_module.app)


def get(fx, **extra):
    return client.get("/tts/timings", params={"text": fx["text"], "lang": fx["lang"], **extra})


# --- the timings line up with what /analyze uses -------------------------------------------------

@pytest.mark.parametrize("fx", [EN, KO], ids=["en", "ko"])
def test_one_entry_per_word_and_sound_in_the_same_order_as_analyze(monkeypatch, tmp_path, fx):
    """The card finds the native part by word number + sound number, so both lists must match /analyze's."""
    setup(monkeypatch, tmp_path, fx)
    r = get(fx)
    assert r.status_code == 200, r.text
    body = r.json()
    expected = expected_phonemes(fx["text"], fx["lang"])       # the same G2P /analyze runs
    assert [w["word"] for w in body["words"]] == [w["word"] for w in expected]
    assert [[p["ipa"] for p in w["phonemes"]] for w in body["words"]] == [w["phonemes"] for w in expected]


@pytest.mark.parametrize("fx", [EN, KO], ids=["en", "ko"])
def test_times_are_inside_the_clip_and_in_order(monkeypatch, tmp_path, fx):
    setup(monkeypatch, tmp_path, fx)
    body = get(fx).json()
    dur = body["duration_s"]
    assert dur > 1
    starts = [w["start"] for w in body["words"]]
    assert starts == sorted(starts)
    for w in body["words"]:
        assert 0 <= w["start"] <= w["end"] <= dur + 1e-6
        assert w["start"] == w["phonemes"][0]["start"] and w["end"] == w["phonemes"][-1]["end"]
        for p in w["phonemes"]:
            assert 0 <= p["start"] <= p["end"] <= dur + 1e-6


def test_a_native_reading_aligns_confidently(monkeypatch, tmp_path):
    """Sanity: the aligner is sure about a clean native clip (the right sentence, said well)."""
    setup(monkeypatch, tmp_path, EN)
    confs = [p["conf"] for w in get(EN).json()["words"] for p in w["phonemes"]]
    assert sum(confs) / len(confs) > 0.5


# --- cache: the JSON sits next to the WAV, and the model runs once per clip ----------------------

def test_timings_are_saved_next_to_the_clip(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, EN)
    get(EN)
    wav = tts.clip_path(EN["text"], "en")
    saved = wav.with_suffix(".json")
    assert wav.exists() and saved.exists()
    assert json.loads(saved.read_text(encoding="utf-8"))["words"][0]["word"] == "Clubs"


def test_second_request_reads_the_saved_json_without_the_model(monkeypatch, tmp_path):
    from backend import native
    setup(monkeypatch, tmp_path, EN)
    first = get(EN).json()

    def boom(*a, **k):
        raise AssertionError("the model ran again")
    monkeypatch.setattr(native, "align_clip", boom)
    second = get(EN)
    assert second.status_code == 200
    assert second.json() == first


def test_broken_or_outdated_saved_json_is_rebuilt(monkeypatch, tmp_path):
    from backend import native
    setup(monkeypatch, tmp_path, EN)
    get(EN)
    saved = tts.clip_path(EN["text"], "en").with_suffix(".json")
    for bad in ["{not json", json.dumps({"version": -1, "words": []})]:
        saved.write_text(bad, encoding="utf-8")
        r = get(EN)
        assert r.status_code == 200
        assert r.json()["version"] == native.TIMINGS_VERSION
        assert len(r.json()["words"]) == 10
        assert json.loads(saved.read_text(encoding="utf-8"))["version"] == native.TIMINGS_VERSION


def test_slower_clip_gets_its_own_timings(monkeypatch, tmp_path):
    """rate=-30 is a different WAV, so it needs its own JSON (the same word happens later)."""
    setup(monkeypatch, tmp_path, EN)
    get(EN)
    get(EN, rate=-30)
    assert tts.clip_path(EN["text"], "en", rate=-30).with_suffix(".json").exists()
    assert len(list(tmp_path.glob("*.json"))) == 2


# --- the clip itself: made on a miss (limits apply), free on a hit ------------------------------

def test_missing_clip_is_made_first(monkeypatch, tmp_path):
    fetch = setup(monkeypatch, tmp_path, EN)
    assert get(EN).status_code == 200
    assert fetch.calls == 1
    get(EN)
    assert fetch.calls == 1                                    # cached WAV, cached JSON: Azure not asked again


def test_a_new_clip_counts_against_the_limit(monkeypatch, tmp_path):
    fetch = setup(monkeypatch, tmp_path, EN, TTSLimiter(per_client=100, window_s=60, daily_chars=5))
    r = get(EN)
    assert r.status_code == 429
    assert fetch.calls == 0


def test_a_cached_clip_needs_no_limit(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, EN)
    get(EN)
    monkeypatch.setattr(app_module, "tts_limiter", TTSLimiter(per_client=0, window_s=60, daily_chars=0))
    tts.clip_path(EN["text"], "en").with_suffix(".json").unlink()   # force a re-align; the WAV is still there
    assert get(EN).status_code == 200


# --- bad input ----------------------------------------------------------------------------------

def test_bad_input(monkeypatch, tmp_path):
    fetch = setup(monkeypatch, tmp_path, EN)
    assert client.get("/tts/timings", params={"text": "   ", "lang": "en"}).status_code == 400
    assert client.get("/tts/timings", params={"text": "?!", "lang": "en"}).status_code == 400   # no words
    assert client.get("/tts/timings", params={"text": "Hi.", "lang": "xx"}).status_code == 422
    assert client.get("/tts/timings", params={"text": "Hi.", "lang": "en", "rate": 10}).status_code == 422
    assert fetch.calls == 0                                    # nothing paid for on bad input


# --- the last sound keeps its tail (live check: 가요 ended 0.11 s before the voice did) --------------

@pytest.mark.parametrize("fx", [EN, KO], ids=["en", "ko"])
def test_last_word_runs_to_where_the_voice_stops(monkeypatch, tmp_path, fx):
    """The aligner ends the final sound at its short CTC spike, which can cut a long last vowel. The native clip
    is clean speech + silence, so the last word must reach the point where the voice actually goes quiet."""
    import numpy as np
    import soundfile as sf
    from backend import native
    setup(monkeypatch, tmp_path, fx)
    last = get(fx).json()["words"][-1]
    x, sr = sf.read(FIXTURES / fx["file"], dtype="float32")
    stop = native.voice_end(x, sr)
    assert abs(last["end"] - stop) <= 0.03
    assert last["phonemes"][-1]["end"] == last["end"]


def test_voice_end_finds_the_end_of_a_tone_and_ignores_quiet_hiss():
    import numpy as np
    from backend import native
    sr = 16000
    t = np.arange(int(0.5 * sr)) / sr
    tone = 0.5 * np.sin(2 * np.pi * 200 * t)
    rng = np.random.default_rng(0)
    x = np.concatenate([np.zeros(int(0.2 * sr)), tone, 0.001 * rng.standard_normal(int(0.6 * sr))]).astype("float32")
    assert abs(native.voice_end(x, sr) - 0.7) <= 0.015
