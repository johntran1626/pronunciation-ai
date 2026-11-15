"""The 2 learning-English sample packs (Basics, Casual) (LLM-written sentences and Korean translations, human-reviewed English).

"""
import json
import re
from pathlib import Path

import pytest

from backend.custom import custom_text
from backend.packs import list_packs

PACKS_DIR = Path(__file__).resolve().parent.parent / "content" / "packs"
ENGLISH_TAGS = {"r_as_l", "l_as_r", "f_as_p", "v_as_b", "th_as_s", "dh_as_d", "ih_as_iy", "iy_as_ih"}
PACK_NAMES = ["basics", "casual"]
HANGUL = re.compile(r"[가-힣]")


@pytest.fixture(scope="module")
def built():
    from content.en_packs import build
    return build()  # pack name -> the pack dict (nothing written)


def all_items(built):
    return [it for pack in built.values() for it in pack["items"]]


def test_two_packs_of_ten(built):
    assert list(built) == PACK_NAMES
    for pack in built.values():
        assert len(pack["items"]) == 10


def test_pack_labels_are_honest(built):
    for name, pack in built.items():
        assert pack["id"] == "en-" + name.replace("_", "-")
        assert pack["lang"] == "en"
        assert pack["dev_only"] is False
        assert pack["reviewed"] is True   # every English sentence was read by a human
        assert "LLM" in pack["source"] and "Claude" in pack["source"]   # honest provenance


def test_ids_are_unique(built):
    ids = [it["id"] for it in all_items(built)]
    assert len(ids) == len(set(ids))


def test_sentences_are_short_and_plain(built):
    for it in all_items(built):
        words = it["text"].split()
        assert 3 <= len(words) <= 9, it["text"]
        assert it["text"][-1] in ".?!", it["text"]
        assert not re.search(r"\d", it["text"]), it["text"]


def test_sentences_need_no_rewriting(built):
    # What's shown is exactly what TTS says and /analyze scores: no numbers or short forms to expand.
    for it in all_items(built):
        assert custom_text(it["text"], "en") == it["text"]


def test_every_sentence_has_a_korean_translation(built):
    for it in all_items(built):
        tr = it["translation"]
        assert tr and HANGUL.search(tr), it["id"]
        assert not re.search(r"[A-Za-z\d]", tr), (it["id"], tr)


def test_every_sentence_has_a_polite_and_a_casual_translation(built):
    # Every pack line needs both forms. `translation` = 존댓말 (합니다 / 해요),
    # `translation_informal` = 반말 (해). Our own speech-style rules (content/sources.py) check the endings.
    from content.sources import spoken_style
    for it in all_items(built):
        polite, casual = it["translation"], it["translation_informal"]
        assert spoken_style(polite) in {"formal", "polite"}, (it["id"], polite)
        assert spoken_style(casual) == "casual", (it["id"], casual)
        assert polite != casual
        assert HANGUL.search(casual) and not re.search(r"[A-Za-z\d]", casual), (it["id"], casual)


def test_every_sentence_practices_a_target(built):
    for it in all_items(built):
        assert it["tags"], it["text"]
        assert set(it["tags"]) <= ENGLISH_TAGS


def test_every_target_is_well_covered(built):
    counts = {t: sum(t in it["tags"] for it in all_items(built)) for t in ENGLISH_TAGS}
    assert min(counts.values()) >= 3, counts   # 20 sentences; TH ([θ]) is the rarest, in 3 of them
    for name, pack in built.items():
        covered = {t for it in pack["items"] for t in it["tags"]}
        assert len(covered) >= 6, (name, sorted(ENGLISH_TAGS - covered))


def test_written_files_match_the_source(built):
    # Editing the sentence list without rerunning `python -m content.en_packs` fails here.
    for name, pack in built.items():
        on_disk = json.loads((PACKS_DIR / f"en_{name}.json").read_text(encoding="utf-8"))
        assert on_disk == pack


def test_api_lists_exactly_the_sample_packs():
    ids = {p["id"] for p in list_packs("en") if not p.get("dev_only")}
    assert ids == {"en-" + n for n in PACK_NAMES}
