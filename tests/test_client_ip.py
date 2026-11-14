"""Which visitor a request comes from, for the per-visitor rate limits (backend/app.py).

On a host like Hugging Face Spaces every request arrives from the host's proxy, so request.client is the proxy and
all visitors would share one limit. The proxy APPENDS the visitor's address to X-Forwarded-For. A visitor can send
their own X-Forwarded-For with any address in it, so only the entries the proxies added can be trusted: with one
proxy, the LAST entry.
"""
import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import tts
from backend.app import client_from, trusted_proxy_hops
from backend.limits import TTSLimiter


def test_without_a_proxy_the_header_is_ignored():
    # Locally (or anywhere without a proxy) anyone can write the header, so it must not count.
    assert client_from("127.0.0.1", ["1.2.3.4"], hops=0) == "127.0.0.1"


def test_one_proxy_uses_the_address_it_added():
    assert client_from("10.16.3.80", ["1.2.3.4"], hops=1) == "1.2.3.4"


def test_a_made_up_address_from_the_visitor_is_skipped():
    # The visitor sent "X-Forwarded-For: 6.6.6.6"; the proxy appended the real address after it.
    assert client_from("10.16.3.80", ["6.6.6.6, 1.2.3.4"], hops=1) == "1.2.3.4"


def test_several_header_lines_count_as_one_list():
    assert client_from("10.16.3.80", ["6.6.6.6", "1.2.3.4"], hops=1) == "1.2.3.4"


def test_two_proxies_use_the_second_last_entry():
    assert client_from("10.0.0.2", ["6.6.6.6, 1.2.3.4, 10.0.0.1"], hops=2) == "1.2.3.4"


def test_no_header_falls_back_to_the_connection():
    assert client_from("10.16.3.80", [], hops=1) == "10.16.3.80"
    assert client_from("10.16.3.80", [" , "], hops=1) == "10.16.3.80"


def test_no_connection_info_is_unknown():
    assert client_from(None, [], hops=0) == "unknown"


def test_setting_parses_a_small_whole_number():
    assert trusted_proxy_hops(None) == 0
    assert trusted_proxy_hops("") == 0
    assert trusted_proxy_hops(" 1 ") == 1
    for bad in ("-1", "abc", "1.5", "11"):
        with pytest.raises(ValueError):
            trusted_proxy_hops(bad)


# --- end to end: two visitors behind the same proxy get their own limits --------------------------

@pytest.fixture
def behind_proxy(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tts, "azure_fetch", lambda ssml: b"RIFF" + b"\x00" * 40)
    monkeypatch.setattr(app_module, "tts_limiter", TTSLimiter(per_client=1, window_s=60, daily_chars=100_000))
    monkeypatch.setattr(app_module, "TRUSTED_PROXY_HOPS", 1)
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test-key")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "eastus")
    return TestClient(app_module.app)


def _new_clip(client, text, visitor):
    return client.get("/tts", params={"text": text, "lang": "en"}, headers={"X-Forwarded-For": visitor})


def test_visitors_behind_one_proxy_have_separate_limits(behind_proxy):
    assert _new_clip(behind_proxy, "One.", "1.1.1.1").status_code == 200
    assert _new_clip(behind_proxy, "Two.", "2.2.2.2").status_code == 200   # a different visitor: not limited
    assert _new_clip(behind_proxy, "Three.", "1.1.1.1").status_code == 429  # the first visitor's limit is used


def test_a_visitor_cannot_dodge_the_limit_with_a_fake_header(behind_proxy):
    assert _new_clip(behind_proxy, "One.", "1.1.1.1").status_code == 200
    # Same visitor (the proxy appends 1.1.1.1 last) pretending to be someone else in front of it.
    assert _new_clip(behind_proxy, "Two.", "9.9.9.9, 1.1.1.1").status_code == 429
