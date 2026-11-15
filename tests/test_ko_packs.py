"""Count native 존댓말 / 반말 lines per pack, pick ~10 per level (krdict first), list the gaps.

No g2p here: a fake tagger stands in, so these tests are fast and only test the picking rules.
"""
from content import ko_packs as K


def _c(text, speech="존댓말", source="krdict", sid="1#0", grade="초급", syl=9, word="a", style="polite"):
    return {"text": text, "speech": speech, "source": source, "source_id": sid, "grade": grade,
            "context": word, "style": style,
            "syllables": syl, "license": "L", "credit": "C", "source_url": "u"}


def fake_tags(text):
    """Tags = the letters in a tiny code inside the test sentence; 'X' = G2P can't read it."""
    if "X" in text:
        return None
    return sorted({ch for ch in text if ch in "abcde"})


def test_count_by_speech_and_source():
    cands = [_c("a", sid="1#0"), _c("b", source="chatbot", sid="r1"), _c("c", speech="반말", source="tatoeba")]
    assert K.count(cands) == {"존댓말": {"krdict": 1, "chatbot": 1}, "반말": {"tatoeba": 1}}


def test_krdict_comes_first_then_chatbot_then_tatoeba():
    cands = [_c("a tat", source="tatoeba", sid="t1"), _c("a chat", source="chatbot", sid="c1"),
             _c("a kr", source="krdict", sid="9#0")]
    picked = K.pick(cands, n=3, tag_fn=fake_tags)["존댓말"]
    assert [p["source"] for p in picked] == ["krdict", "chatbot", "tatoeba"]


def test_easier_dictionary_words_first():
    cands = [_c("a hard", sid="1#0", grade="고급"), _c("a mid", sid="2#0", grade="중급"),
             _c("a easy", sid="3#0", grade="초급")]
    assert [p["text"] for p in K.pick(cands, n=3, tag_fn=fake_tags)["존댓말"]] == ["a easy", "a mid", "a hard"]


def test_one_line_per_dictionary_entry():
    # Two lines of the same krdict dialogue (entry 5) are a question + its answer: keep only one, for variety.
    cands = [_c("a q", sid="5#0"), _c("b", sid="5#1"), _c("c", sid="6#0")]
    picked = K.pick(cands, n=3, tag_fn=fake_tags)["존댓말"]
    assert [p["source_id"] for p in picked] == ["5#0", "6#0"]


def test_new_target_sounds_break_ties():
    # Same source and grade: the line that adds sounds we don't have yet wins.
    # (fake tags = the letters a-e in the text)
    cands = [_c("a", sid="1#0"), _c("a b", sid="2#0"), _c("a c d", sid="3#0")]
    picked = K.pick(cands, n=2, tag_fn=fake_tags)["존댓말"]
    assert [p["text"] for p in picked] == ["a c d", "a b"]     # 3 new sounds, then the one still adding b


def test_lines_g2p_cannot_read_or_with_no_target_sound_are_skipped():
    cands = [_c("aX", sid="1#0"), _c("zzz", sid="2#0"), _c("b", sid="3#0")]
    picked = K.pick(cands, n=3, tag_fn=fake_tags)["존댓말"]
    assert [p["text"] for p in picked] == ["b"] and picked[0]["tags"] == ["b"]


def test_levels_are_picked_separately_and_gaps_listed():
    cands = [_c(f"a{i}", sid=f"{i}#0") for i in range(12)] + [_c("b", speech="반말", sid="99#0")]
    picks = K.pick(cands, n=10, tag_fn=fake_tags)
    assert len(picks["존댓말"]) == 10 and len(picks["반말"]) == 1
    assert K.gaps(picks, n=10) == {"존댓말": 0, "반말": 9}


def test_picks_keep_source_and_license():
    p = K.pick([_c("a", sid="1#0")], n=1, tag_fn=fake_tags)["존댓말"][0]
    assert {"text", "speech", "source", "source_id", "source_url", "license", "credit", "tags"} <= set(p)


# ---------- fit the pack, stand alone ----------

def test_uses_headword_handles_verbs_and_hada():
    assert K.uses_headword({"source": "krdict", "context": "배", "text": "우리 배를 좀 깎아 먹을까?"})
    assert not K.uses_headword({"source": "krdict", "context": "물", "text": "공부 방법을 바꿔 보렴."})
    assert K.uses_headword({"source": "krdict", "context": "바꾸다", "text": "엄마 바꿔 봐."}) is False  # 바꿔 != 바꾸
    assert K.uses_headword({"source": "krdict", "context": "끝나다", "text": "오늘 회사 끝나고 뭐 해?"})
    assert K.uses_headword({"source": "krdict", "context": "신선하다", "text": "생선이 신선해요."})
    assert K.uses_headword({"source": "chatbot", "context": "Q", "text": "아무 말"})   # n/a outside krdict


def test_line_that_uses_the_dictionary_word_first():
    # krdict topics belong to the WORD; the dialogue line that actually says the word is the one on topic.
    cands = [_c("a 디자인", sid="1#0", word="물"), _c("a 찬물", sid="2#0", word="물")]
    assert K.pick(cands, n=1, tag_fn=fake_tags)["존댓말"][0]["text"] == "a 찬물"


def test_answers_that_need_the_question_come_last():
    cands = [_c("응. a 좋아.", sid="1#0"), _c("a 좋아.", sid="2#0"), _c("아니, a 몰라.", sid="3#0")]
    assert [p["source_id"] for p in K.pick(cands, n=3, tag_fn=fake_tags)["존댓말"]][0] == "2#0"
    assert K.is_answer("네, 확인해 볼게요.") and K.is_answer("그래. 가자.") and not K.is_answer("네가 먹어.")


def test_casual_pack_prefers_haeyo_over_hamnida():
    cands = [_c("a 합니다", sid="1#0", style="formal"), _c("a 해요", sid="2#0", style="polite")]
    assert K.pick(cands, n=1, tag_fn=fake_tags, pack="casual")["존댓말"][0]["style"] == "polite"
    assert K.pick(cands, n=1, tag_fn=fake_tags, pack="basics")["존댓말"][0]["source_id"] == "1#0"


# ---------- hand-picked misfits out, the next-best native line fills in ----------

def test_excluded_lines_are_skipped_and_the_next_best_fills_in():
    cands = [_c("a b c", sid="1#0"), _c("a", sid="2#0")]
    picked = K.pick(cands, n=1, tag_fn=fake_tags, exclude={"1#0"})["존댓말"]
    assert [p["source_id"] for p in picked] == ["2#0"]


def test_every_excluded_line_names_a_real_pack_and_a_reason():
    from content.sources import PACKS
    assert set(K.EXCLUDE) <= set(PACKS)
    for pack, lines in K.EXCLUDE.items():
        for sid, reason in lines.items():
            assert "#" in sid and reason.strip(), (pack, sid)
