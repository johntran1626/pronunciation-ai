"""POST /analyze has a per-visitor rate limit (backend/app.py).

Scoring costs no money (it runs on our CPU), but one visitor sending recordings non-stop would slow the app down for
everyone else. A real learner records, listens and reads the result, so 20 a minute is far more than anyone needs.
"""
from fastapi.testclient import TestClient

from backend import app as app_module
from backend.limits import TTSLimiter
from tests.test_analyze import beep_wav

client = TestClient(app_module.app)


def post(headers=None):
    return client.post("/analyze", files={"audio": ("rec.wav", beep_wav(0.5), "audio/wav")},
                       data={"text": "   ", "lang": "ko"}, headers=headers or {})  # empty text: a quick 400


def test_default_limit_is_20_a_minute():
    assert app_module.ANALYZE_PER_MINUTE == 20


def test_over_the_limit_is_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(app_module, "analyze_limiter", TTSLimiter(per_client=2, window_s=60, daily_chars=0))
    assert post().status_code == 400            # counted, then refused for its own reason
    assert post().status_code == 400
    r = post()
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1
    assert "recordings" in r.json()["detail"]   # a sentence the frontend can show as-is


def test_each_visitor_has_their_own_limit(monkeypatch):
    monkeypatch.setattr(app_module, "analyze_limiter", TTSLimiter(per_client=1, window_s=60, daily_chars=0))
    monkeypatch.setattr(app_module, "TRUSTED_PROXY_HOPS", 1)   # as on the Space: trust the proxy's last entry
    assert post({"X-Forwarded-For": "1.1.1.1"}).status_code == 400
    assert post({"X-Forwarded-For": "1.1.1.1"}).status_code == 429
    assert post({"X-Forwarded-For": "2.2.2.2"}).status_code == 400   # a different visitor is not blocked


def test_the_limit_is_checked_before_the_upload_is_read(monkeypatch):
    # A blocked visitor must not cost us the work of decoding their file.
    monkeypatch.setattr(app_module, "analyze_limiter", TTSLimiter(per_client=1, window_s=60, daily_chars=0))
    assert post().status_code == 400            # uses up the limit
    r = client.post("/analyze", files={"audio": ("rec.wav", b"not audio", "audio/wav")},
                    data={"text": "안녕하세요", "lang": "ko"})
    assert r.status_code == 429
