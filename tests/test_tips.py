"""content/tips.json (built by content/build_tips.py)."""
import json
import re
from pathlib import Path

import pytest

from backend.g2p import expected_phonemes
from backend.scoring import EXTRA_VOWEL, PAIRS

ROOT = Path(__file__).resolve().parent.parent
TIPS = ROOT / "content" / "tips.json"
ARTIC = ROOT / "content" / "articulation.json"

# MVP confusion pairs, learning Korean
KO_PAIRS = {"eo_as_o", "eu_as_u", "ae_as_e", "tap_as_r", "tap_as_l", "pp_as_p", "pp_as_ph", "ph_as_p", "p_as_ph",
            "u_as_eu", "p_as_pp", "t_as_tt", "k_as_kk"}   # the last 4 = the live Korean checks (korean_scoring.py)
EN_PAIRS = set(PAIRS) | {EXTRA_VOWEL, "word_not_heard"}
MAX_TIP_CHARS = 220  # about two short sentences: the card is read on a phone


@pytest.fixture(scope="module")
def tips():
    return json.loads(TIPS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sounds():
    return json.loads(ARTIC.read_text(encoding="utf-8"))["sounds"]


def entries(tips):
    return [(lang, name, e) for lang in ("en", "ko") for name, e in tips["tips"][lang].items()]


def test_every_pair_has_a_tip(tips):
    assert set(tips["tips"]["en"]) == EN_PAIRS
    assert set(tips["tips"]["ko"]) == KO_PAIRS


def test_english_pairs_match_the_scorer(tips):
    for name, pair in PAIRS.items():
        e = tips["tips"]["en"][name]
        assert (e["target"], e["produced"]) == (pair["target"], pair["produced"]), name


def test_sounds_exist_in_the_articulation_table(tips, sounds):
    for lang, name, e in entries(tips):
        for side in ("target", "produced"):
            if e[side] is not None:  # word_not_heard has neither; extra_vowel has no target sound
                assert e[side] in sounds[e[side + "_lang"]], (lang, name, side)


def test_tip_facts_agree_with_the_articulation_table(tips, sounds):
    """Each tip lists the table facts it is written from. If the table changes, this flags the tip."""
    for lang, name, e in entries(tips):
        for side, facts in e["facts"].items():
            entry = sounds[e[side + "_lang"]][e[side]]
            for key, want in facts.items():
                got = entry["svg"][key] if key in entry["svg"] else entry[key]
                assert got == want, (lang, name, side, key, got, want)
        if e["target"] is not None and e["produced"] is not None:
            assert e["facts"], (lang, name)  # a pair tip must rest on at least one table fact


def test_text_is_short_and_has_one_word_slot(tips):
    for lang, name, e in entries(tips):
        assert len(e["tip"]) <= MAX_TIP_CHARS, (lang, name, len(e["tip"]))
        assert re.findall(r"\{(\w*)\}", e["what_happened"]) == ["word"], (lang, name)
        assert e["what_happened"].format(word="x")
        assert e["target_label"] and (e["produced"] is None or e["produced_label"]), (lang, name)


def test_practice_words_really_contain_the_sound(tips):
    for lang, name, e in entries(tips):
        words = e["practice"]
        if name == "word_not_heard":
            assert words == []
            continue
        assert len(words) == 3 and len(set(words)) == 3, (lang, name)
        for w in words:
            assert " " not in w, (lang, name, w)
            phones = expected_phonemes(w, lang)[0]["phonemes"]
            if name == EXTRA_VOWEL:
                assert phones[-1] not in ("ə", "ɪ", "iː", "ʊ", "uː", "ɑː", "æ", "ɛ", "ʌ", "ɔː", "ɚ", "oʊ", "eɪ"), w
            elif e.get("position") == "initial":
                assert phones[0] == e["target"], (lang, name, w, phones)
            else:
                assert e["target"] in phones, (lang, name, w, phones)


def test_korean_practice_words_are_hangul(tips):
    hangul = re.compile(r"^[가-힣]+$")
    for name, e in tips["tips"]["ko"].items():
        assert all(hangul.match(w) for w in e["practice"]), name


# Review status: every English tip is approved; a native speaker approved the Korean
# vowel and ㄹ tips; the tips for the live Korean checks were approved against their cited references.
# The other ㅂ/ㅃ/ㅍ tips were reworded after review, so they stay unreviewed until checked again.
KO_UNREVIEWED = {"pp_as_p", "pp_as_ph", "ph_as_p", "p_as_ph"}
KO_LIVE_CHECK_TIPS = {"u_as_eu", "p_as_pp", "t_as_tt", "k_as_kk"}
KO_STOPS = KO_UNREVIEWED | {"p_as_pp", "t_as_tt", "k_as_kk"}


def test_review_status_matches_the_reviews(tips):
    for name, e in tips["tips"]["en"].items():
        assert e["reviewed"] is True, name
    for name, e in tips["tips"]["ko"].items():
        approved = name not in KO_UNREVIEWED
        assert e["reviewed"] is approved, name
        assert e["needs_native_review"] is (not approved), name


def test_live_korean_check_tips_are_reviewed_and_cited(tips):
    for name in KO_LIVE_CHECK_TIPS:
        e = tips["tips"]["ko"][name]
        assert e["reviewed"] is True, name
        assert e["sources"], name


def test_u_tip_does_not_claim_only_the_lips_differ(tips):
    """Some descriptions place ㅡ more central than ㅜ, so the tip must not say the tongue is identical."""
    tip = tips["tips"]["ko"]["u_as_eu"]["tip"]
    assert "only the lips" not in tip
    assert "the big difference is the lips" in tip


def test_korean_stop_tips_treat_them_as_different_sounds(tips):
    """Native-speaker feedback: Koreans clearly tell ㅂ ㅃ ㅍ apart, so never say one 'sounded like' another.
    Say what the learner produced instead, and what the word needs."""
    for name in KO_STOPS:
        line = tips["tips"]["ko"][name]["what_happened"]
        assert "sounded like" not in line, name
        assert "where the word needs" in line, name


def test_ae_e_tip_mentions_the_seoul_merger(tips):
    assert "merge" in tips["tips"]["ko"]["ae_as_e"]["tip"].lower() or "same" in tips["tips"]["ko"]["ae_as_e"]["tip"].lower()


# ---------- served to the frontend ----------
def test_api_serves_the_tips():
    from fastapi.testclient import TestClient
    from backend.app import app
    r = TestClient(app).get("/tips")
    assert r.status_code == 200
    body = r.json()
    assert body["tips"]["en"]["r_as_l"]["target"] == "ɹ"
    assert body["tips"]["ko"]["tap_as_r"]["produced_lang"] == "en"
