"""Attach what was heard to each expected phoneme (hand-made inputs: no model, fast)."""
from backend.compare import attach_heard


def words_of(*specs):
    """words_of(("balls", "b ɔː l z")) -> the shape align() returns (times left out: not needed here)."""
    return [{"word": w, "pron": "", "phonemes": [{"ipa": p} for p in ps.split()]} for w, ps in specs]


def heard_of(symbols):
    return [{"symbol": s, "start": 0.0, "end": 0.02, "conf": 0.9} for s in symbols.split()]


def ops(words):
    return [[(p["ipa"], p["op"], p["heard"]) for p in w["phonemes"]] for w in words]


def test_missing_l_in_balls():
    words, _ = attach_heard(words_of(("balls", "b ɔː l z")), heard_of("b oː z"), "en")
    assert ops(words) == [[("b", "match", "b"), ("ɔː", "sub", "oː"), ("l", "del", None), ("z", "match", "z")]]


def test_korean_compares_in_the_models_symbols():
    # 머 = [m ʌ]; the model writes ㅓ as ɔ (spikes/a_vowels.py). Heard "m ɔ" is CORRECT, not an error.
    words, _ = attach_heard(words_of(("머", "m ʌ")), heard_of("m ɔ"), "ko")
    assert ops(words) == [[("m", "match", "m"), ("ʌ", "match", "ɔ")]]
    assert words[0]["phonemes"][1]["target_symbol"] == "ɔ"


def test_extra_vowel_is_attached_after_the_sound_it_follows():
    words, start = attach_heard(words_of(("bus", "b ʌ s")), heard_of("b ʌ s ɯ"), "en")
    assert [p["extra_after"] for p in words[0]["phonemes"]] == [[], [], ["ɯ"]]
    assert start == []


def test_extra_sounds_before_the_first_word_are_kept_apart():
    words, start = attach_heard(words_of(("cat", "k æ t")), heard_of("h k æ t"), "en")
    assert start == ["h"]
    assert ops(words) == [[("k", "match", "k"), ("æ", "match", "æ"), ("t", "match", "t")]]


def test_errors_land_in_the_right_word():
    words, _ = attach_heard(words_of(("right", "ɹ aɪ t"), ("now", "n aʊ")), heard_of("ɹ aɪ t n"), "en")
    assert ops(words) == [[("ɹ", "match", "ɹ"), ("aɪ", "match", "aɪ"), ("t", "match", "t")],
                          [("n", "match", "n"), ("aʊ", "del", None)]]


def test_input_is_not_changed():
    words = words_of(("cat", "k æ t"))
    attach_heard(words, heard_of("k æ t"), "en")
    assert words == words_of(("cat", "k æ t"))
