"""Mixed English + Korean sentences ("I really want to eat 떡볶이 tonight.").

The pieces, in the order the app uses them:
  1. backend/mixed_text.py  splits the sentence into language runs (Hangul = Korean, Latin letters = English)
  2. backend/tts.py         one multilingual voice says it, with an SSML <lang> tag around each run
  3. backend/g2p.py         each run's words get their own language's expected sounds, tagged with that language
  4. backend/mixed.py       hybrid timings: one multilingual pass finds where each run sits in the clip, the clip is
                            cut there, and each piece is aligned by its own language's model, then shifted back

No test touches the network. The last test runs the real models on a clip built from two committed fixture
recordings (English, then Korean, then English again), so the true language borders are known exactly.
"""
import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import mixed, mixed_text, native, tts
from backend.custom import custom_text
from backend.g2p import expected_phonemes
from backend.limits import TTSLimiter

FAKE_WAV = b"RIFF" + b"\x00" * 40 + b"fake audio"
FIXTURES = __import__("pathlib").Path(__file__).with_name("fixtures")


class FakeFetch:
    def __init__(self, audio=FAKE_WAV):
        self.audio, self.calls = audio, []

    def __call__(self, ssml):
        self.calls.append(ssml)
        return self.audio


# ---------- 1. language runs ----------

@pytest.mark.parametrize("text, runs", [
    ("I really want to eat 떡볶이 tonight.", [("en", "I really want to eat "), ("ko", "떡볶이 "), ("en", "tonight.")]),
    ("Ben 어제 일찍 잤어?", [("en", "Ben "), ("ko", "어제 일찍 잤어?")]),
    ("Ben이 어제 왔어.", [("en", "Ben"), ("ko", "이 어제 왔어.")]),        # a particle glued to an English name
    ("커피 2잔 and a bagel", [("ko", "커피 2잔 "), ("en", "and a bagel")]),
    ("I want 2개", [("en", "I want "), ("ko", "2개")]),                      # a number glued to Hangul is Korean
    ("I want 2 떡볶이", [("en", "I want 2 "), ("ko", "떡볶이")]),              # a number on its own stays behind
    ("안녕하세요", [("ko", "안녕하세요")]),
])
def test_split_runs(text, runs):
    assert mixed_text.split_runs(text) == runs
    assert "".join(r for _, r in mixed_text.split_runs(text)) == text      # nothing lost or added


def test_is_mixed_needs_both_scripts():
    assert mixed_text.is_mixed("오늘 BTS 콘서트 가요")
    assert not mixed_text.is_mixed("안녕하세요")
    assert not mixed_text.is_mixed("Hello 123!")


# ---------- 2. the voice ----------

def test_mixed_sentences_use_the_multilingual_voice_and_single_language_ones_keep_theirs():
    assert tts.voice_name("mix") == "en-US-AvaMultilingualNeural"
    assert tts.voice_name("en") == "en-US-AvaNeural"
    assert tts.voice_name("ko") == "ko-KR-SunHiNeural"


def test_mixed_ssml_tags_each_run_with_its_language():
    ssml = tts.build_ssml("I want 떡볶이, rice & tea.", "en-US-AvaMultilingualNeural", -30, lang="mix")
    assert 'name="en-US-AvaMultilingualNeural"' in ssml
    assert '<lang xml:lang="en-US"><prosody rate="-30%">I want</prosody></lang> <lang' in ssml
    assert '<lang xml:lang="ko-KR"><prosody rate="-30%">떡볶이,</prosody></lang>' in ssml
    assert '<lang xml:lang="en-US"><prosody rate="-30%">rice &amp; tea.</prosody></lang>' in ssml


def test_no_space_is_added_where_the_sentence_had_none():
    ssml = tts.build_ssml("Ben이 왔어.", "en-US-AvaMultilingualNeural", 0, lang="mix")
    assert "Ben</prosody></lang><lang" in ssml


def test_synthesize_mix_sends_the_tagged_ssml_and_caches_it_apart(tmp_path):
    fetch = FakeFetch()
    path = tts.synthesize("I want 떡볶이.", "mix", cache_dir=tmp_path, fetch=fetch)
    assert path.exists() and 'xml:lang="ko-KR"' in fetch.calls[0]
    assert tts.clip_path("I want 떡볶이.", "en", cache_dir=tmp_path) != path


# ---------- 3. expected sounds, per word language ----------

def test_g2p_mix_tags_every_word_with_its_language():
    words = expected_phonemes("I want 떡볶이 tonight.", "mix")
    assert [(w["word"], w["lang"]) for w in words] == [("I", "en"), ("want", "en"), ("떡볶이", "ko"), ("tonight", "en")]
    assert words[2]["phonemes"] == expected_phonemes("떡볶이", "ko")[0]["phonemes"]
    assert words[1]["phonemes"] == expected_phonemes("want", "en")[0]["phonemes"]


def test_g2p_mix_splits_a_particle_off_an_english_word():
    words = expected_phonemes("Ben이 왔어.", "mix")
    assert [(w["word"], w["lang"]) for w in words] == [("Ben", "en"), ("이", "ko"), ("왔어", "ko")]


def test_g2p_mix_with_nothing_to_say_is_refused():
    with pytest.raises(ValueError):
        expected_phonemes("?!", "mix")


def test_custom_text_mix_writes_numbers_out_in_each_runs_language():
    assert custom_text("커피 2잔 please", "mix") == "커피 두 잔 please"
    assert custom_text("I want 2 떡볶이", "mix") == "I want two 떡볶이"


# ---------- 4. hybrid timings (pure parts) ----------

def w(word, lang, start, end):
    return {"word": word, "lang": lang, "start": start, "end": end,
            "phonemes": [{"ipa": "x", "start": start, "end": end, "conf": 0.5}]}


# one-pass times measured on a real Azure clip of "I really want to eat 떡볶이 tonight."
FIRST = [w("eat", "en", 0.93, 1.03), w("떡볶이", "ko", 1.03, 1.45), w("tonight", "en", 1.50, 1.83)]


def test_pieces_follow_the_language_runs_and_cut_in_the_gap():
    pieces = mixed.plan_pieces(FIRST, duration=2.0, pad=0.1)
    assert [(p.lang, p.words) for p in pieces] == [("en", [0]), ("ko", [1]), ("en", [2])]
    assert [(p.lo, p.hi) for p in pieces] == [(0.0, 1.03), (1.03, 1.475), (1.475, 2.0)]
    assert [(p.a, p.b) for p in pieces] == [(0.0, 1.13), (0.93, 1.575), (1.375, 2.0)]   # padded, inside the clip


def test_piece_times_are_shifted_back_and_kept_inside_their_own_piece():
    piece = mixed.plan_pieces(FIRST, duration=2.0, pad=0.1)[1]                 # 떡볶이: lo 1.03, hi 1.475, a 0.93
    local = [w("떡볶이", "ko", 0.05, 0.60)]                                     # 0.05 s in = 0.98 s: before lo
    out = mixed.place(local, piece)
    assert out[0]["start"] == 1.03 and out[0]["end"] == 1.475                   # 0.93 + 0.60 = 1.53, past hi
    assert out[0]["phonemes"][0]["start"] == 1.03


def test_a_piece_its_model_cannot_align_keeps_the_first_pass_times():
    def refuse(samples, sr, words, lang):
        raise ValueError("recording is too short")
    out = mixed.hybrid(np.zeros(32000, dtype=np.float32), 16000, FIRST, align_piece=refuse)
    assert [(x["start"], x["end"]) for x in out] == [(0.93, 1.03), (1.03, 1.45), (1.50, 1.83)]
    assert [x["lang"] for x in out] == ["en", "ko", "en"]


# ---------- the API ----------

@pytest.fixture
def fake(monkeypatch, tmp_path):
    fetch = FakeFetch()
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tts, "azure_fetch", fetch)
    monkeypatch.setattr(app_module, "tts_limiter", TTSLimiter(per_client=100, window_s=60, daily_chars=100_000))
    return fetch


client = TestClient(app_module.app)


def test_tts_and_custom_accept_mix(fake):
    r = client.get("/tts", params={"text": "I want 떡볶이.", "lang": "mix"})
    assert r.status_code == 200 and 'xml:lang="ko-KR"' in fake.calls[0]
    r = client.get("/custom", params={"text": "커피 2잔 please", "lang": "mix"})
    assert r.status_code == 200 and r.json()["text"] == "커피 두 잔 please"


def test_analyze_refuses_mix():
    """Scoring was never measured on mixed sentences, so the app doesn't offer Practice for them."""
    r = client.post("/analyze", files={"audio": ("rec.wav", FAKE_WAV, "audio/wav")},
                    data={"text": "I want 떡볶이.", "lang": "mix"})
    assert r.status_code == 422


# ---------- 4. hybrid timings on real audio (runs the models: a few seconds) ----------

def _clip(name):
    x, sr = sf.read(FIXTURES / name, dtype="float32")
    assert sr == 16000
    return x


EN_TEXT = "Clubs and balls and cities grew to be only memories."
KO_TEXT = "강아지가 용변을 보도록 유도하는 말을 가르칠 수도 있다"


def test_hybrid_times_put_every_word_in_its_own_language_part(monkeypatch, tmp_path):
    """English, then Korean in the MIDDLE (the case where one model per language over the whole clip failed),
    then English. The true borders are where the recordings were joined."""
    en, ko, en2 = _clip("cmu_slt_arctic_a0020.wav"), _clip("zeroth_126_003_2058.wav"), _clip("cmu_bdl_arctic_a0001.wav")
    gap = np.zeros(int(0.3 * 16000), dtype=np.float32)
    audio = np.concatenate([en, gap, ko * (np.abs(en).max() / np.abs(ko).max()), gap, en2])
    ko_lo = (len(en) + len(gap)) / 16000
    ko_hi = ko_lo + len(ko) / 16000
    en2_text = "Author of the danger trail, Philip Steels, etc."
    text = f"{EN_TEXT} {KO_TEXT} {en2_text}"

    buf = io.BytesIO()
    sf.write(buf, audio, 16000, format="WAV", subtype="PCM_16")
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tts, "azure_fetch", FakeFetch(buf.getvalue()))
    monkeypatch.setattr(app_module, "tts_limiter", TTSLimiter(per_client=100, window_s=60, daily_chars=100_000))

    r = client.get("/tts/timings", params={"text": text, "lang": "mix"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lang"] == "mix"
    words = body["words"]
    assert [x["word"] for x in words] == [x["word"] for x in expected_phonemes(text, "mix")]
    tol = 0.15
    for x in words:
        if x["lang"] == "ko":
            assert ko_lo - tol <= x["start"] and x["end"] <= ko_hi + tol, x
        else:
            assert x["end"] <= ko_lo + tol or x["start"] >= ko_hi - tol, x
    starts = [p["start"] for x in words for p in x["phonemes"]]
    assert starts == sorted(starts)                                             # one clean timeline, no overlap
    assert native.timings_path(tts.clip_path(text, "mix")).exists()            # saved like any other clip
