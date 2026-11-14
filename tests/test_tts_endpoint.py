"""GET /tts serves native reference audio to the browser (backend/app.py + backend/limits.py).

 No test touches the network:
backend.tts.azure_fetch is replaced by a fake, and the cache folder is a temporary one.
"""
import urllib.error

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import tts
from backend.limits import TTSLimiter

FAKE_WAV = b"RIFF" + b"\x00" * 40 + b"fake audio"
SECRET = "secret-test-key-123"


class FakeFetch:
    def __init__(self):
        self.calls = 0

    def __call__(self, ssml):
        self.calls += 1
        return FAKE_WAV


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """Temporary cache, fake Azure, a fresh roomy limiter, and a key in the environment."""
    fetch = FakeFetch()
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tts, "azure_fetch", fetch)
    monkeypatch.setattr(app_module, "tts_limiter", TTSLimiter(per_client=100, window_s=60, daily_chars=100_000))
    monkeypatch.setenv("AZURE_SPEECH_KEY", SECRET)
    monkeypatch.setenv("AZURE_SPEECH_REGION", "eastus")
    return fetch


client = TestClient(app_module.app)


def get(text="같이 가요.", lang="ko", **extra):
    return client.get("/tts", params={"text": text, "lang": lang, **extra})


# --- serving + cache ----------------------------------------------------------------------------

def test_first_request_makes_the_clip_and_returns_wav(fake):
    r = get()
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content == FAKE_WAV
    assert r.headers["x-tts-cache"] == "miss"
    assert fake.calls == 1


def test_second_request_is_served_from_the_cache(fake):
    get()
    r = get()
    assert r.status_code == 200 and r.content == FAKE_WAV
    assert r.headers["x-tts-cache"] == "hit"
    assert fake.calls == 1                      # Azure was called once, not twice


def test_browser_may_keep_the_clip_for_a_day(fake):
    assert "max-age=86400" in get().headers["cache-control"]


def test_slow_and_male_versions_are_separate_clips(fake):
    get()
    get(rate=-30)
    get(voice="male")
    assert fake.calls == 3


def test_frontend_origin_may_read_the_audio(fake):
    r = client.get("/tts", params={"text": "Hi.", "lang": "en"}, headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


# --- input checks (before any Azure call) -------------------------------------------------------

@pytest.mark.parametrize("params", [
    {"text": "   ", "lang": "ko"},                  # empty after trimming
    {"text": "a" * 201, "lang": "en"},              # over the 200-character limit
])
def test_bad_text_is_refused_with_400(fake, params):
    r = client.get("/tts", params=params)
    assert r.status_code == 400
    assert fake.calls == 0


@pytest.mark.parametrize("params", [
    {"text": "Hi.", "lang": "ja"},                  # unknown language
    {"text": "Hi.", "lang": "en", "voice": "child"},  # unknown voice
    {"text": "Hi.", "lang": "en", "rate": -80},     # slower than half speed
    {"text": "Hi.", "lang": "en", "rate": 20},      # faster than normal
    {"lang": "en"},                                 # no text at all
])
def test_bad_options_are_refused_with_422(fake, params):
    assert client.get("/tts", params=params).status_code == 422
    assert fake.calls == 0


# --- the key stays on the server ----------------------------------------------------------------

def test_azure_failure_is_503_and_never_shows_the_key(monkeypatch, fake):
    def refused(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
    monkeypatch.setattr(tts, "azure_fetch", lambda ssml: _real_azure_fetch(ssml, urlopen=refused))
    r = get()
    assert r.status_code == 503
    assert "401" in r.json()["detail"]
    assert SECRET not in r.text
    assert SECRET not in str(r.headers)


def test_missing_key_is_503_with_a_readable_message(monkeypatch, fake):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "")
    monkeypatch.setattr(tts, "load_env", lambda path=None: None)   # don't read the real .env
    monkeypatch.setattr(tts, "azure_fetch", _real_azure_fetch)
    r = get()
    assert r.status_code == 503
    assert "AZURE_SPEECH_KEY" in r.json()["detail"]


def test_a_failed_call_leaves_no_cache_file(monkeypatch, fake, tmp_path):
    def broken(ssml):
        raise tts.TTSError("Azure TTS unreachable: offline")
    monkeypatch.setattr(tts, "azure_fetch", broken)
    assert get().status_code == 503
    assert list(tmp_path.iterdir()) == []


# --- rate limits (only NEW clips count: a cached clip costs nothing) -----------------------------

def test_too_many_new_clips_from_one_client_is_429(monkeypatch, fake):
    monkeypatch.setattr(app_module, "tts_limiter", TTSLimiter(per_client=2, window_s=60, daily_chars=100_000))
    assert get("하나.").status_code == 200
    assert get("둘.").status_code == 200
    r = get("셋.")
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert fake.calls == 2


def test_cached_clips_are_still_served_while_limited(monkeypatch, fake):
    monkeypatch.setattr(app_module, "tts_limiter", TTSLimiter(per_client=1, window_s=60, daily_chars=100_000))
    assert get("하나.").status_code == 200
    assert get("둘.").status_code == 429
    r = get("하나.")
    assert r.status_code == 200 and r.headers["x-tts-cache"] == "hit"


def test_daily_character_budget_is_429(monkeypatch, fake):
    monkeypatch.setattr(app_module, "tts_limiter", TTSLimiter(per_client=100, window_s=60, daily_chars=10))
    assert get("Hello.", "en").status_code == 200          # 6 characters
    r = get("Thanks.", "en")                                # 7 more would pass 10
    assert r.status_code == 429
    assert "daily" in r.json()["detail"].lower()
    assert fake.calls == 1


def _real_azure_fetch(ssml, urlopen=None):
    """The real Azure function (saved before any monkeypatch), with a swappable urlopen."""
    return _ORIGINAL_AZURE_FETCH(ssml, urlopen=urlopen) if urlopen else _ORIGINAL_AZURE_FETCH(ssml)


_ORIGINAL_AZURE_FETCH = tts.azure_fetch
