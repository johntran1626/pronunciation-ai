"""Map each Korean SPOKEN sound back to the WRITTEN syllable block and jamo it comes from."""
from backend.g2p import expected_phonemes
from backend.text_map import korean_sources


def mapped(text):
    """-> [(char_index, jamo, slot), ...] for the first word, one per expected phoneme."""
    w = expected_phonemes(text, "ko")[0]
    return [(s["char_index"], s["jamo"], s["slot"]) for s in korean_sources(w["word"], w["pron"])]


def test_gachi_palatalization_points_back_to_the_written_t():
    # 같이 is said 가치: the ㅊ sound comes from the written ㅌ at the end of 같
    assert mapped("같이") == [(0, "ㄱ", "onset"), (0, "ㅏ", "vowel"), (0, "ㅌ", "coda"), (1, "ㅣ", "vowel")]


def test_gungmul_nasal_assimilation():
    # 국물 is said 궁물: the ŋ is the written ㄱ
    assert mapped("국물")[2] == (0, "ㄱ", "coda")


def test_ikda_double_final_and_tensing():
    # 읽다 is said 익따: k = the written ㄺ, tense t͈ = the written ㄷ
    assert mapped("읽다") == [(0, "ㅣ", "vowel"), (0, "ㄺ", "coda"), (1, "ㄷ", "onset"), (1, "ㅏ", "vowel")]


def test_liaison_across_two_syllables():
    # 맛있어요 is said 마시써요: ㅅ from 맛, ㅆ from 있; 요 has a silent ㅇ and no sound of its own
    assert mapped("맛있어요") == [
        (0, "ㅁ", "onset"), (0, "ㅏ", "vowel"), (0, "ㅅ", "coda"), (1, "ㅣ", "vowel"),
        (1, "ㅆ", "coda"), (2, "ㅓ", "vowel"), (3, "ㅛ", "vowel"), (3, "ㅛ", "vowel")]


def test_double_final_split_by_liaison():
    # 읽어 is said 일거: both l and k come from the written ㄺ
    assert mapped("읽어")[1:3] == [(0, "ㄺ", "coda"), (0, "ㄺ", "coda")]


def test_numbers_fall_back_to_the_whole_word():
    # 3개 is said 세개: 1 written Hangul block vs 2 spoken, so don't guess
    assert all(ci is None for ci, _, _ in mapped("3개"))


def test_every_phoneme_gets_exactly_one_source():
    text = "몬터규는 자녀들이 사랑을 제대로 못 받고 크면 매우 심각한 결과가 초래된다는 결론을 내렸습니다"
    for w in expected_phonemes(text, "ko"):
        assert len(korean_sources(w["word"], w["pron"])) == len(w["phonemes"]), w


# ---------- English sound -> letters ----------
from backend.text_map import english_sources  # noqa: E402


def letters(text):
    """-> the letters each phoneme of the first word comes from ('' if none)."""
    w = expected_phonemes(text, "en")[0]
    return [w["word"][s["start"]:s["end"]] if s["start"] is not None else ""
            for s in english_sources(w["word"], w["pron"])]


def test_knight_silent_k_and_gh():
    assert letters("knight") == ["kn", "igh", "t"]


def test_colonel():
    assert letters("colonel") == ["c", "olo", "n", "e", "l"]


def test_ph_and_silent_final_e():
    assert letters("phone") == ["ph", "o", "n"]


def test_x_makes_two_sounds():
    assert letters("box") == ["b", "o", "x", "x"]


def test_digraphs():
    assert letters("church") == ["ch", "ur", "ch"]
    assert letters("ship") == ["sh", "i", "p"]
    assert letters("sheep") == ["sh", "ee", "p"]
    assert letters("think") == ["th", "i", "n", "k"]


def test_people_le_ending():
    assert letters("people") == ["p", "eo", "p", "le", "le"]


def test_capitals_are_kept():
    assert letters("Right") == ["R", "igh", "t"]


def test_every_phoneme_gets_a_span_in_order():
    text = "Author of the danger trail, Philip Steels, etc."
    for w in expected_phonemes(text, "en"):
        spans = english_sources(w["word"], w["pron"])
        assert len(spans) == len(w["phonemes"])
        starts = [s["start"] for s in spans if s["start"] is not None]
        assert starts == sorted(starts)


def test_no_letters_falls_back_to_the_whole_word():
    assert all(s["start"] is None for s in english_sources("42", "F AO1 R T IY0 T UW1"))


# ---------- display segments for the UI ----------
from backend.text_map import attach_display  # noqa: E402


def scored(word, pron, phonemes, red=(), times=None):
    """A fake scored word: phonemes with status (red at the given indexes) and times."""
    times = times or [(round(0.1 * i, 3), round(0.1 * (i + 1), 3)) for i in range(len(phonemes))]  # like align.py
    return {"word": word, "pron": pron, "status": "red" if red else "green", "phonemes": [
        {"ipa": p, "status": "red" if i in red else "green", "start": times[i][0], "end": times[i][1]}
        for i, p in enumerate(phonemes)]}


def test_english_red_letters():
    [w] = attach_display([scored("knight", "N AY1 T", ["n", "aɪ", "t"], red={1})], "en")
    assert w["display"] == [{"text": "kn", "status": "green"}, {"text": "igh", "status": "red"},
                            {"text": "t", "status": "green"}]
    assert w["phonemes"][1]["source"] == {"start": 2, "end": 5}


def test_english_red_sound_without_letters_colors_the_whole_word():
    [w] = attach_display([scored("42", "F AO1 R T IY0 T UW1", ["f", "ɔː", "ɹ", "t", "iː", "t", "uː"], red={0})], "en")
    assert w["display"] == [{"text": "42", "status": "red"}]


def test_korean_red_syllable_with_its_jamo_and_times():
    [w] = attach_display([scored("같이", "가치", ["k", "a", "tɕʰ", "i"], red={2})], "ko")
    assert w["display"][0] == {"text": "같", "status": "red", "red_jamo": ["ㅌ"], "red_slots": ["coda"],
                               "start": 0.0, "end": 0.3}
    assert w["display"][1] == {"text": "이", "status": "green", "red_jamo": [], "red_slots": [],
                               "start": 0.3, "end": 0.4}


def test_korean_red_slot_tells_apart_the_same_jamo_twice():
    # 각 has ㄱ at the start AND the end. red_jamo alone can't say which one was wrong.
    [w] = attach_display([scored("각", "각", ["k", "a", "k"], red={2})], "ko")
    assert w["display"][0]["red_jamo"] == ["ㄱ"]
    assert w["display"][0]["red_slots"] == ["coda"]


def test_korean_fallback_colors_the_whole_word():
    [w] = attach_display([scored("3개", "세개", ["s", "e", "k", "ɛ"], red={0})], "ko")
    assert [d["status"] for d in w["display"]] == ["red", "red"]


def test_all_green_display_spells_the_word():
    for text, lang in [("Author of the danger trail, Philip Steels.", "en"), ("맛있어요 같이 먹을 것", "ko")]:
        words = [scored(w["word"], w["pron"], w["phonemes"]) for w in expected_phonemes(text, lang)]
        for w in attach_display(words, lang):
            assert "".join(d["text"] for d in w["display"]) == w["word"]
            assert all(d["status"] == "green" for d in w["display"])


def test_input_is_not_changed():
    words = [scored("knight", "N AY1 T", ["n", "aɪ", "t"], red={1})]
    before = repr(words)
    attach_display(words, "en")
    assert repr(words) == before


# ---------- "unchecked" (no live check looked at it) ----------
def with_statuses(w, statuses):
    for p, s in zip(w["phonemes"], statuses):
        p["status"] = s
    w["status"] = "red" if "red" in statuses else "green" if "green" in statuses else "unchecked"
    return w


def test_english_unchecked_letters_are_kept_apart_from_checked_ones():
    w = with_statuses(scored("from", "F R AH1 M", ["f", "ɹ", "ʌ", "m"]), ["unchecked", "green", "unchecked", "unchecked"])
    [w] = attach_display([w], "en")
    assert w["display"] == [{"text": "f", "status": "unchecked"}, {"text": "r", "status": "green"},
                            {"text": "om", "status": "unchecked"}]


def test_silent_letters_follow_their_neighbour():
    w = with_statuses(scored("knight", "N AY1 T", ["n", "aɪ", "t"]), ["unchecked", "unchecked", "unchecked"])
    [w] = attach_display([w], "en")
    assert w["display"] == [{"text": "knight", "status": "unchecked"}]


def test_korean_unchecked_blocks():
    w = with_statuses(scored("같이", "가치", ["k", "a", "tɕʰ", "i"]), ["unchecked"] * 4)
    [w] = attach_display([w], "ko")
    assert [d["status"] for d in w["display"]] == ["unchecked", "unchecked"]
