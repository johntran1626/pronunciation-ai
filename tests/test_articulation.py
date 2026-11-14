"""content/articulation.json (built by content/build_articulation.py)."""
import json
from pathlib import Path

import pytest

from backend.g2p import ARPA2IPA, CODA, ONSET, VOWEL
from backend.scoring import PAIRS

TABLE = Path(__file__).resolve().parent.parent / "content" / "articulation.json"

EN_SOUNDS = set(ARPA2IPA.values()) | {"ə"}
KO_SOUNDS = {s for s in ONSET if s} | {p for v in VOWEL for p in v} | {s for s in CODA if s}

KINDS = {"consonant", "vowel", "diphthong", "glide"}
LIPS = {"closed", "lip_to_teeth", "rounded", "spread", "neutral"}
VOICING = {"voiced", "voiceless"}
LARYNGEAL = {"plain", "aspirated", "tense", None}  # Korean three-way stop/affricate/fricative contrast
TIPS = {"down", "dental", "alveolar", "postalveolar", "palatal", "raised"}


@pytest.fixture(scope="module")
def table():
    return json.loads(TABLE.read_text(encoding="utf-8"))


def entries(table):
    return [(lang, ipa, e) for lang in ("en", "ko") for ipa, e in table["sounds"][lang].items()]


def test_every_sound_our_g2p_can_output_has_an_entry(table):
    assert set(table["sounds"]["en"]) == EN_SOUNDS
    assert set(table["sounds"]["ko"]) == KO_SOUNDS


def test_table_cites_its_sources_and_is_marked_unreviewed(table):
    assert len(table["sources"]) >= 2
    for lang, ipa, e in entries(table):
        assert e["reviewed"] is False, (lang, ipa)  # flips only after a human reviewer checks it


def test_every_entry_has_valid_fields(table):
    for lang, ipa, e in entries(table):
        where = (lang, ipa)
        assert e["kind"] in KINDS, where
        assert e["lips"] in LIPS, where
        assert e["voicing"] in VOICING, where
        assert e["description"], where
        svg = e["svg"]
        for k in ("tongue_x", "tongue_y", "lip_gap", "lip_round"):
            assert 0 <= svg[k] <= 1, (where, k)
        assert svg["tip"] in TIPS and svg["velum"] in ("raised", "lowered") and isinstance(svg["contact"], bool), where
        if e["kind"] in ("vowel", "diphthong"):
            assert e["height"] and e["frontness"] and isinstance(e["rounded"], bool), where
            assert e["voicing"] == "voiced", where
        else:
            assert e["place"] and e["manner"], where
        if e["kind"] == "diphthong":
            assert e["to"] in table["sounds"][lang] or e["to"] in table["sounds"]["en"], where


def test_lips_agree_with_the_sound(table):
    for lang, ipa, e in entries(table):
        where = (lang, ipa)
        if e.get("place") == "bilabial" and e.get("manner") in ("stop", "nasal"):
            assert e["lips"] == "closed" and e["svg"]["lip_gap"] == 0, where
        if e.get("place") == "labiodental":
            assert e["lips"] == "lip_to_teeth", where
        if e["kind"] in ("vowel", "diphthong") and e["rounded"]:
            assert e["lips"] == "rounded" and e["svg"]["lip_round"] > 0.5, where


def test_nasals_lower_the_velum_and_nothing_else_does(table):
    for lang, ipa, e in entries(table):
        assert (e["svg"]["velum"] == "lowered") == (e.get("manner") == "nasal"), (lang, ipa)


def test_korean_stops_have_the_three_way_contrast(table):
    ko = table["sounds"]["ko"]
    for plain, tense, asp in [("p", "p͈", "pʰ"), ("t", "t͈", "tʰ"), ("k", "k͈", "kʰ"), ("tɕ", "t͈ɕ", "tɕʰ")]:
        assert [ko[x]["laryngeal"] for x in (plain, tense, asp)] == ["plain", "tense", "aspirated"]
    assert [ko[x]["laryngeal"] for x in ("s", "s͈")] == ["plain", "tense"]
    for lang, ipa, e in entries(table):
        assert e.get("laryngeal") in LARYNGEAL, (lang, ipa)


def test_every_confusion_pair_has_both_sounds(table):
    en = table["sounds"]["en"]
    for name, pair in PAIRS.items():
        assert pair["target"] in en and pair["produced"] in en, name


def test_the_mvp_contrasts_really_differ(table):
    en, ko = table["sounds"]["en"], table["sounds"]["ko"]
    assert en["ɹ"]["manner"] != en["l"]["manner"]                       # approximant vs lateral
    assert en["f"]["lips"] == "lip_to_teeth" and en["p"]["lips"] == "closed"
    assert en["θ"]["svg"]["tip"] == "dental" and en["s"]["svg"]["tip"] == "alveolar"
    assert en["iː"]["svg"]["tongue_y"] > en["ɪ"]["svg"]["tongue_y"]     # sheep is higher than ship
    assert ko["ʌ"]["rounded"] is False and ko["o"]["rounded"] is True   # ㅓ vs ㅗ: the lips
    assert ko["ɯ"]["rounded"] is False and ko["u"]["rounded"] is True   # ㅡ vs ㅜ: the lips
    assert ko["ɾ"]["manner"] == "tap"


# ---------- served to the frontend ----------
def test_api_serves_the_table():
    from fastapi.testclient import TestClient
    from backend.app import app
    r = TestClient(app).get("/articulation")
    assert r.status_code == 200
    body = r.json()
    assert "ɹ" in body["sounds"]["en"] and "ʌ" in body["sounds"]["ko"]
    assert body["note"].startswith("Textbook TARGET")
