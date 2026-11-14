"""Sentence packs (content/packs/*.json) and the API that serves them to the frontend.


"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.g2p import expected_phonemes

client = TestClient(app)
PACKS_DIR = Path(__file__).resolve().parent.parent / "content" / "packs"

ENGLISH_TAGS = {"r_as_l", "l_as_r", "f_as_p", "v_as_b", "th_as_s", "dh_as_d", "ih_as_iy", "iy_as_ih"}
KOREAN_TAGS = {"eo_vs_o", "eu", "ae_vs_e", "tap_r", "p_stops"}


def dev_packs():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PACKS_DIR.glob("dev_*.json"))]


def test_both_dev_packs_exist():
    assert sorted(p["lang"] for p in dev_packs()) == ["en", "ko"]


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_dev_pack_is_well_formed_and_labelled(lang):
    pack = next(p for p in dev_packs() if p["lang"] == lang)
    assert pack["dev_only"] is True and pack["reviewed"] is False  # never pretend it's checked content
    assert pack["source"] and pack["license"]                      # credit where the text came from
    items = pack["items"]
    assert len(items) == 10
    assert len({it["id"] for it in items}) == 10                   # ids unique within the pack
    allowed = ENGLISH_TAGS if lang == "en" else KOREAN_TAGS
    for it in items:
        assert it["text"].strip()
        assert it["translation"] is None or isinstance(it["translation"], str)
        assert set(it["tags"]) <= allowed, it


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_every_sentence_goes_through_g2p(lang):
    # If G2P can't handle a sentence, /analyze can't score it, so it shouldn't be in a pack.
    pack = next(p for p in dev_packs() if p["lang"] == lang)
    for it in pack["items"]:
        words = expected_phonemes(it["text"], lang)
        assert words and all(w["phonemes"] for w in words), it["text"]


def test_every_english_dev_sentence_has_an_r():
    # r_as_l is the one check that can turn red today, so every dev sentence should exercise it.
    pack = next(p for p in dev_packs() if p["lang"] == "en")
    assert all("r_as_l" in it["tags"] for it in pack["items"])


# ---------- the API ----------

def test_list_packs_gives_summaries_without_sentences():
    r = client.get("/packs")
    assert r.status_code == 200
    packs = r.json()
    assert {p["id"] for p in packs} >= {"dev-en", "dev-ko"}
    for p in packs:
        assert "items" not in p                  # the list is small; sentences come from /packs/{id}
        assert p["count"] == 10 or not p["id"].startswith("dev-")
        assert {"id", "lang", "name", "dev_only", "reviewed"} <= set(p)


def test_list_packs_filters_by_language():
    r = client.get("/packs", params={"lang": "ko"})
    assert r.status_code == 200
    assert {p["lang"] for p in r.json()} == {"ko"}


def test_get_one_pack_has_its_sentences():
    r = client.get("/packs/dev-ko")
    assert r.status_code == 200
    assert len(r.json()["items"]) == 10


def test_unknown_pack_is_404():
    assert client.get("/packs/nope").status_code == 404


def test_pack_id_cannot_reach_other_files():
    # Ids are looked up in the loaded packs, never turned into a file path, so this can't read backend files.
    assert client.get("/packs/..%2F..%2Fbackend%2Fthresholds").status_code == 404
