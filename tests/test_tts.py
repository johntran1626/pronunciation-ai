"""Native reference audio from Azure text-to-speech (backend/tts.py), cached on disk.

No test here touches the network:
the Azure call is replaced by a fake `fetch` (or a fake `urlopen` for the Azure function itself).
"""
import os

import pytest

from backend import tts

FAKE_WAV = b"RIFF" + b"\x00" * 40 + b"fake audio"


class FakeFetch:
    """Stands in for the Azure call: records every SSML it was asked for, returns fixed bytes."""

    def __init__(self, audio=FAKE_WAV):
        self.audio = audio
        self.calls = []

    def __call__(self, ssml):
        self.calls.append(ssml)
        return self.audio


# --- voices -------------------------------------------------------------------------------------

def test_default_voice_is_the_womans_voice():
    assert tts.voice_name("ko") == "ko-KR-SunHiNeural"
    assert tts.voice_name("en") == "en-US-AvaNeural"


def test_mans_voice_is_kept_as_an_option():
    assert tts.voice_name("ko", "male") == "ko-KR-InJoonNeural"
    assert tts.voice_name("en", "male") == "en-US-AndrewNeural"


def test_unknown_language_or_voice_is_refused():
    with pytest.raises(ValueError):
        tts.voice_name("ja")
    with pytest.raises(ValueError):
        tts.voice_name("ko", "child")


# --- SSML ---------------------------------------------------------------------------------------

def test_ssml_names_the_voice_and_language():
    ssml = tts.build_ssml("같이 가요.", "ko-KR-SunHiNeural", 0)
    assert 'xml:lang="ko-KR"' in ssml
    assert 'name="ko-KR-SunHiNeural"' in ssml
    assert "같이 가요." in ssml


def test_ssml_escapes_characters_that_would_break_the_markup():
    ssml = tts.build_ssml('Tom & "Jerry" <3', "en-US-AvaNeural", 0)
    assert "&amp;" in ssml and "&lt;3" in ssml
    assert "<3" not in ssml


def test_ssml_slow_rate():
    assert 'rate="-30%"' in tts.build_ssml("hello", "en-US-AvaNeural", -30)
    assert 'rate="0%"' in tts.build_ssml("hello", "en-US-AvaNeural", 0)


# --- cache key ----------------------------------------------------------------------------------

def test_cache_key_ignores_extra_spaces():
    assert tts.cache_key("같이  가요. ", "ko-KR-SunHiNeural", 0) == tts.cache_key("같이 가요.", "ko-KR-SunHiNeural", 0)


def test_cache_key_treats_two_unicode_spellings_of_korean_as_the_same():
    composed = "가요"                                   # one code point per syllable block
    decomposed = "가요"            # same text written as separate jamo
    assert tts.cache_key(composed, "ko-KR-SunHiNeural", 0) == tts.cache_key(decomposed, "ko-KR-SunHiNeural", 0)


def test_cache_key_changes_with_voice_rate_and_text():
    base = tts.cache_key("hello", "en-US-AvaNeural", 0)
    assert base != tts.cache_key("hello", "en-US-AndrewNeural", 0)
    assert base != tts.cache_key("hello", "en-US-AvaNeural", -30)
    assert base != tts.cache_key("hello.", "en-US-AvaNeural", 0)


# --- synthesize (with the cache) ----------------------------------------------------------------

def test_first_call_asks_azure_and_saves_the_file(tmp_path):
    fetch = FakeFetch()
    path = tts.synthesize("같이 가요.", "ko", cache_dir=tmp_path, fetch=fetch)
    assert len(fetch.calls) == 1
    assert 'name="ko-KR-SunHiNeural"' in fetch.calls[0]
    assert path.parent == tmp_path and path.suffix == ".wav"
    assert path.read_bytes() == FAKE_WAV


def test_second_call_uses_the_saved_file_and_never_asks_azure(tmp_path):
    fetch = FakeFetch()
    first = tts.synthesize("같이 가요.", "ko", cache_dir=tmp_path, fetch=fetch)
    second = tts.synthesize("같이  가요. ", "ko", cache_dir=tmp_path, fetch=fetch)
    assert first == second
    assert len(fetch.calls) == 1


def test_slow_and_male_versions_are_separate_files(tmp_path):
    fetch = FakeFetch()
    a = tts.synthesize("hello", "en", cache_dir=tmp_path, fetch=fetch)
    b = tts.synthesize("hello", "en", rate=-30, cache_dir=tmp_path, fetch=fetch)
    c = tts.synthesize("hello", "en", voice="male", cache_dir=tmp_path, fetch=fetch)
    assert len({a, b, c}) == 3
    assert len(fetch.calls) == 3


@pytest.mark.parametrize("text", ["", "   ", "가" * (tts.MAX_CHARS + 1)])
def test_empty_or_too_long_text_is_refused_before_any_azure_call(tmp_path, text):
    fetch = FakeFetch()
    with pytest.raises(ValueError):
        tts.synthesize(text, "ko", cache_dir=tmp_path, fetch=fetch)
    assert fetch.calls == []


@pytest.mark.parametrize("rate", [-60, 10])
def test_rate_out_of_range_is_refused(tmp_path, rate):
    fetch = FakeFetch()
    with pytest.raises(ValueError):
        tts.synthesize("hello", "en", rate=rate, cache_dir=tmp_path, fetch=fetch)
    assert fetch.calls == []


def test_reply_that_is_not_audio_is_refused_and_not_cached(tmp_path):
    fetch = FakeFetch(audio=b"<html>error page</html>")
    with pytest.raises(tts.TTSError):
        tts.synthesize("hello", "en", cache_dir=tmp_path, fetch=fetch)
    assert list(tmp_path.iterdir()) == []


def test_failed_call_leaves_no_half_written_file(tmp_path):
    def broken(ssml):
        raise tts.TTSError("Azure said 500")
    with pytest.raises(tts.TTSError):
        tts.synthesize("hello", "en", cache_dir=tmp_path, fetch=broken)
    assert list(tmp_path.iterdir()) == []


# --- the real Azure function, with a fake network ---------------------------------------------

def test_missing_key_gives_a_clear_error(monkeypatch):
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.setattr(tts, "load_env", lambda path=None: None)    # don't read the real .env
    with pytest.raises(tts.TTSError, match="AZURE_SPEECH_KEY"):
        tts.azure_fetch("<speak/>")


def test_azure_error_message_never_contains_the_key(monkeypatch):
    import urllib.error
    monkeypatch.setenv("AZURE_SPEECH_KEY", "supersecret123")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "eastus")
    monkeypatch.setattr(tts, "load_env", lambda path=None: None)

    def fake_urlopen(req, timeout):
        assert req.full_url == "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1"
        assert req.get_header("Ocp-apim-subscription-key") == "supersecret123"
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    with pytest.raises(tts.TTSError) as err:
        tts.azure_fetch("<speak/>", urlopen=fake_urlopen)
    assert "401" in str(err.value)
    assert "supersecret123" not in str(err.value)


def test_azure_fetch_returns_the_audio_bytes(monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "k")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "eastus")
    monkeypatch.setattr(tts, "load_env", lambda path=None: None)

    class Reply:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return FAKE_WAV

    def fake_urlopen(req, timeout):
        assert req.get_header("X-microsoft-outputformat") == tts.OUTPUT_FORMAT
        assert req.data == "<speak/>".encode("utf-8")
        return Reply()

    assert tts.azure_fetch("<speak/>", urlopen=fake_urlopen) == FAKE_WAV


# --- .env reader --------------------------------------------------------------------------------

def test_load_env_reads_keys_but_never_overrides_existing_ones(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# a comment\n\nAZURE_SPEECH_REGION=westus2\nTTS_TEST_ONLY = abc \n", encoding="utf-8")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "eastus")
    monkeypatch.delenv("TTS_TEST_ONLY", raising=False)
    tts.load_env(env)
    assert os.environ["AZURE_SPEECH_REGION"] == "eastus"
    assert os.environ["TTS_TEST_ONLY"] == "abc"
