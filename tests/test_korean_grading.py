"""Korean green/red in /analyze (backend/korean_scoring.py): only the Korean checks that passed all four bars.

Unit tests use made-up measurement rows (no model). The live tests run both models on the Zeroth native
recording in tests/fixtures (CC BY 4.0): once with its real text, once with one syllable swapped in the text
(가르칠 -> 가루칠), so the text asks for ㅜ where the speaker said ㅡ.
"""
import io
import json
from pathlib import Path

import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from backend.g2p import TENSE
from backend.korean_scoring import apply_korean, check_names, live_checks, load_korean_thresholds, tip_id

ROOT = Path(__file__).resolve().parent.parent
TIPS = json.loads((ROOT / "content" / "tips.json").read_text(encoding="utf-8"))["tips"]
FIXTURE = ROOT / "tests" / "fixtures" / "zeroth_126_003_2058.wav"
NATIVE_TEXT = "강아지가 용변을 보도록 유도하는 말을 가르칠 수도 있다"

KT = {"checks": {"ㅜ_as_ㅡ": {"enabled": True, "cut": 0.9},
                 "lenis_as_tense": {"enabled": True, "cut": 0.8},
                 "ㅓ_as_ㅗ": {"enabled": False, "cut": 0.5}}}


def word(text, ipas, status="unchecked", not_heard=False):
    """A word as match.finalize() leaves it for Korean: no sound checked yet."""
    return {"word": text, "pron": text, "status": status, "not_heard": not_heard,
            "phonemes": [{"ipa": p, "start": 0.1 * i, "end": 0.1 * i + 0.1, "status": status, "checked": False}
                         for i, p in enumerate(ipas)]}


def row(wi, pi, check, margin, heard_said):
    return {"wi": wi, "pi": pi, "check": check, "position": "initial", "margin": margin, "heard_said": heard_said}


# ---------- which checks are live ----------
def test_only_enabled_checks_are_live():
    assert live_checks(KT) == {"ㅜ_as_ㅡ": 0.9, "lenis_as_tense": 0.8}


def test_the_shipped_file_turns_on_exactly_the_two_checks_that_passed_all_bars():
    assert set(live_checks(load_korean_thresholds())) == {"ㅜ_as_ㅡ", "lenis_as_tense"}


def test_the_honesty_line_names_the_live_korean_checks():
    assert check_names(KT) == ["lenis_as_tense", "u_as_eu"]
    assert check_names({"checks": {}}) == []


# ---------- tip ids ----------
def test_each_red_sound_points_at_a_tip_for_its_own_place():
    assert tip_id("ㅜ_as_ㅡ", "u") == "u_as_eu"
    assert tip_id("lenis_as_tense", "p") == "p_as_pp"
    assert tip_id("lenis_as_tense", "t") == "t_as_tt"
    assert tip_id("lenis_as_tense", "k") == "k_as_kk"


def test_every_tip_the_scorer_can_name_exists_and_matches_it():
    for check, target, produced in [("ㅜ_as_ㅡ", "u", "ɯ"), ("lenis_as_tense", "p", "p" + TENSE),
                                    ("lenis_as_tense", "t", "t" + TENSE), ("lenis_as_tense", "k", "k" + TENSE)]:
        tip = TIPS["ko"][tip_id(check, target)]
        assert (tip["target"], tip["produced"]) == (target, produced), check


def test_new_korean_tips_cite_a_reference():
    for name in ("u_as_eu", "p_as_pp", "t_as_tt", "k_as_kk"):
        assert TIPS["ko"][name]["sources"], name


# ---------- coloring ----------
def test_a_live_check_that_fires_turns_the_sound_and_word_red():
    words = [word("수도", ["s", "u", "t", "o"])]
    out = apply_korean(words, [row(0, 1, "ㅜ_as_ㅡ", 0.99, 1), row(0, 2, "lenis_as_tense", 0.1, 0)], KT)
    u, t = out[0]["phonemes"][1], out[0]["phonemes"][2]
    assert (u["status"], u["pair"], u["produced"], u["checked"]) == ("red", "u_as_eu", "ɯ", True)
    assert (t["status"], t["checked"]) == ("green", True)
    assert out[0]["phonemes"][0]["status"] == "unchecked"   # ㅅ has no live check: plain text, not green
    assert out[0]["status"] == "red"


def test_a_checked_sound_that_passes_is_green_and_the_word_too():
    out = apply_korean([word("보도", ["p", "o", "t", "o"])],
                       [row(0, 0, "lenis_as_tense", 0.5, 1), row(0, 2, "lenis_as_tense", 0.95, 0)], KT)
    assert [p["status"] for p in out[0]["phonemes"]] == ["green", "unchecked", "green", "unchecked"]
    assert out[0]["status"] == "green"


def test_red_needs_both_the_margin_and_the_wrong_sound_heard():
    out = apply_korean([word("바", ["p", "a"])], [row(0, 0, "lenis_as_tense", 0.95, 1)], KT)
    p = out[0]["phonemes"][0]
    assert (p["status"], p["pair"], p["produced"]) == ("red", "p_as_pp", "p" + TENSE)


def test_a_check_that_failed_its_bars_never_colors_anything():
    out = apply_korean([word("거", ["k", "ʌ"])], [row(0, 1, "ㅓ_as_ㅗ", 0.99, 1)], KT)
    assert out[0]["phonemes"][1]["status"] == "unchecked" and out[0]["status"] == "unchecked"


def test_a_word_that_was_not_heard_stays_red_for_that_reason():
    w = word("수", ["s", "u"], status="red", not_heard=True)
    for p in w["phonemes"]:
        p["pair"], p["produced"] = "word_not_heard", None
    out = apply_korean([w], [row(0, 1, "ㅜ_as_ㅡ", 0.1, 0)], KT)
    assert out[0]["phonemes"][1]["pair"] == "word_not_heard" and out[0]["status"] == "red"


def test_rows_that_do_not_line_up_with_the_words_are_ignored():
    out = apply_korean([word("수", ["s", "u"])], [row(0, 0, "ㅜ_as_ㅡ", 0.99, 1), row(3, 0, "ㅜ_as_ㅡ", 0.99, 1)], KT)
    assert [p["status"] for p in out[0]["phonemes"]] == ["unchecked", "unchecked"]


def test_input_words_are_not_changed():
    words = [word("수", ["s", "u"])]
    apply_korean(words, [row(0, 1, "ㅜ_as_ㅡ", 0.99, 1)], KT)
    assert words[0]["phonemes"][1]["status"] == "unchecked"


# ---------- the real models, through /analyze ----------
def _analyze(text):
    from backend.app import app
    return TestClient(app).post("/analyze", files={"audio": ("a.wav", FIXTURE.read_bytes(), "audio/wav")},
                                data={"text": text, "lang": "ko"}).json()


@pytest.fixture(scope="module")
def native_body():
    return _analyze(NATIVE_TEXT)


def test_live_a_native_reading_has_green_checked_sounds_and_no_red(native_body):
    assert native_body["matched"] is True
    assert {"u_as_eu", "lenis_as_tense"} <= set(native_body["checks"])
    phones = [p for w in native_body["words"] for p in w["phonemes"]]
    assert not [p for p in phones if p["status"] == "red"]
    assert sum(p["status"] == "green" for p in phones) >= 5     # 수's ㅜ and the plain ㄱ/ㄷ/ㅂ stops
    assert any(d["status"] == "green" for w in native_body["words"] for d in w["display"])


def test_live_text_asking_for_u_where_the_speaker_said_eu_goes_red_there_only():
    body = _analyze(NATIVE_TEXT.replace("가르칠", "가루칠"))
    red_words = [w["word"] for w in body["words"] if w["status"] == "red"]
    assert red_words == ["가루칠"]
    red = [p for w in body["words"] for p in w["phonemes"] if p["status"] == "red"]
    assert [(p["ipa"], p["pair"], p["produced"]) for p in red] == [("u", "u_as_eu", "ɯ")]
