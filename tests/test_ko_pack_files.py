"""The 2 learning-Korean sample packs on disk (Basics, Casual): native lines (source + license per line) with English translations.

The picks themselves come from data/ (git-ignored, rebuilt by `python -m content.ko_packs`), so these tests read
the committed pack files, plus one small fake report for the builder.
"""
import json
import re
from pathlib import Path

import pytest

from backend.packs import get_pack, list_packs
from content import ko_packs as K
from content.ko_translations import TRANSLATIONS
from content.sources import spoken_style

PACKS_DIR = Path(__file__).resolve().parent.parent / "content" / "packs"
PACK_NAMES = ["basics", "casual"]
KOREAN_TAGS = {"eo_vs_o", "eu", "ae_vs_e", "tap_r", "p_stops"}
NATIVE = {"krdict", "chatbot", "tatoeba"}
HANGUL = re.compile(r"[가-힣]")


@pytest.fixture(scope="module")
def on_disk():
    return {n: json.loads((PACKS_DIR / f"ko_{n}.json").read_text(encoding="utf-8")) for n in PACK_NAMES}


def items(packs):
    return [it for p in packs.values() for it in p["items"]]


def test_two_packs_of_ten_polite_and_ten_casual(on_disk):
    for name, pack in on_disk.items():
        speech = [it["speech"] for it in pack["items"]]
        assert speech.count("존댓말") == 10 and speech.count("반말") == 10, name


def test_pack_labels_are_honest(on_disk):
    for name, pack in on_disk.items():
        assert pack["id"] == "ko-" + name.replace("_", "-")
        assert pack["lang"] == "ko"
        assert pack["dev_only"] is False
        assert pack["reviewed"] is False          # nobody native has checked the translations
        assert "Claude" in pack["source"]          # the English translations are LLM-written: say so
        assert "CC BY-SA" in pack["license"]


def test_every_line_is_native_with_its_own_source_and_license(on_disk):
    for it in items(on_disk):
        assert it["source"] in NATIVE, it["id"]
        for key in ("source_id", "source_url", "license", "credit"):
            assert it[key], (it["id"], key)
        if it["source"] == "krdict":
            assert it["license"] == "CC BY-SA 2.0 KR"
            assert it["source_url"].startswith("https://krdict.korean.go.kr/")


def test_speech_level_matches_the_ending(on_disk):
    # The switch filters by `speech`, so it must agree with our own speech-style rules.
    for it in items(on_disk):
        assert it["speech"] == ("반말" if spoken_style(it["text"]) == "casual" else "존댓말"), it["text"]


def test_every_line_has_an_english_translation(on_disk):
    for it in items(on_disk):
        tr = it["translation"]
        assert tr and re.search(r"[A-Za-z]", tr) and not HANGUL.search(tr), (it["id"], tr)
        assert tr[-1] in ".?!", (it["id"], tr)
        assert "translation_informal" not in it    # one English meaning; the switch picks lines, not forms


def test_translations_come_from_the_table(on_disk):
    # Editing a translation without rerunning `python -m content.ko_packs` fails here.
    for it in items(on_disk):
        assert it["translation"] == TRANSLATIONS[it["source_id"]], it["id"]


def test_every_translation_belongs_to_a_shipped_line(on_disk):
    # No leftover English for lines that are no longer in any pack.
    assert set(TRANSLATIONS) == {it["source_id"] for it in items(on_disk)}


def test_only_the_sample_packs_ship():
    learner = {f.stem for f in PACKS_DIR.glob("*.json") if not f.stem.startswith("dev_")}
    assert learner == {f"{lang}_{n}" for lang in ("en", "ko") for n in PACK_NAMES}


def test_every_line_practices_a_target(on_disk):
    for it in items(on_disk):
        assert it["tags"] and set(it["tags"]) <= KOREAN_TAGS, it["id"]


def test_ids_and_lines_are_unique(on_disk):
    all_items = items(on_disk)
    assert len({it["id"] for it in all_items}) == len(all_items)
    assert len({it["text"] for it in all_items}) == len(all_items)


def test_api_serves_the_korean_packs():
    summaries = {p["id"]: p for p in list_packs("ko")}
    for name in PACK_NAMES:
        pid = "ko-" + name.replace("_", "-")
        assert summaries[pid]["count"] == 20
        assert len(get_pack(pid)["items"]) == 20


# ---- the builder, on a tiny fake report (no data/ needed) ----

def _line(text, sid, speech):
    return {"text": text, "source": "krdict", "source_id": sid, "source_url": "https://krdict.korean.go.kr/x",
            "license": "CC BY-SA 2.0 KR", "credit": "C", "speech": speech, "tags": ["eu"],
            "context": "w", "grade": "초급", "style": "polite", "syllables": 5, "topics": [], "pack": "basics"}


def test_build_files_keeps_order_and_only_what_the_app_needs():
    report = {"basics": {"picks": {"존댓말": [_line("가요.", "1#0", "존댓말")], "반말": [_line("가.", "2#0", "반말")]}}}
    packs = K.build_files(report, translations={"1#0": "I'm going (polite).", "2#0": "I'm going."})
    pack = packs["basics"]
    assert pack["id"] == "ko-basics" and pack["name"] == "Basics"
    assert [it["id"] for it in pack["items"]] == ["ko_basics_01", "ko_basics_02"]
    assert [it["speech"] for it in pack["items"]] == ["존댓말", "반말"]
    assert set(pack["items"][0]) == {"id", "text", "translation", "speech", "tags",
                                     "source", "source_id", "source_url", "license", "credit"}


def test_build_files_refuses_a_line_with_no_translation():
    report = {"basics": {"picks": {"존댓말": [_line("가요.", "1#0", "존댓말")], "반말": []}}}
    with pytest.raises(KeyError, match="1#0"):
        K.build_files(report, translations={})
