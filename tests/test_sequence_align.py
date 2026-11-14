"""backend/sequence_align.py: line up expected vs heard phonemes.

align_sequences(expected, heard) lines up two lists of phoneme symbols and returns one tuple per step:
    ("match", e, h)   same sound
    ("sub",   e, h)   substitution: expected e, heard h instead
    ("del",   e, None) deletion: e was expected but not heard
    ("ins",   None, h) insertion: h was heard but not expected (e.g. an extra vowel)

Cost rule (pick the line-up with the LOWEST total cost):
    match 0 · deletion 1 · insertion 1
    substitution 1 if both are vowels or both are consonants, 1.5 if a vowel is swapped with a consonant
Why the 1.5: with plain cost 1, "b ɔː l z" vs "b oː z" has TWO equally cheap line-ups, and one of them
says "the L turned into oː", which is phonetically silly. Vowel-for-vowel is the likelier story.
A symbol is a vowel if its FIRST character is one of: a e i o u æ ɑ ɒ ɔ ə ɚ ɛ ɜ ɪ ʊ ʌ ɯ ɤ ø œ y ʏ ɐ ɘ ɵ ɨ ʉ
(so diphthongs like oʊ and long vowels like iː count as vowels; ɹ, l, j, w are consonants).
Every test below has exactly one cheapest line-up (checked by hand), so the answer is unique.
"""
from backend.sequence_align import align_sequences


def s(text):
    return text.split()


def test_identical_sequences_are_all_matches():
    assert align_sequences(s("k æ t"), s("k æ t")) == [("match", "k", "k"), ("match", "æ", "æ"), ("match", "t", "t")]


def test_one_vowel_substitution():  # cat said as "cut"
    assert align_sequences(s("k æ t"), s("k ʌ t")) == [("match", "k", "k"), ("sub", "æ", "ʌ"), ("match", "t", "t")]


def test_r_said_as_l():  # right said as "light": the most common English error for Korean speakers
    assert align_sequences(s("ɹ aɪ t"), s("l aɪ t"))[0] == ("sub", "ɹ", "l")


def test_missing_l_in_balls():  # real L2-ARCTIC case (HKK a0020), human-marked
    assert align_sequences(s("b ɔː l z"), s("b oː z")) == [
        ("match", "b", "b"), ("sub", "ɔː", "oː"), ("del", "l", None), ("match", "z", "z")]


def test_extra_vowel_after_final_consonant():  # "bus-eu"
    assert align_sequences(s("b ʌ s"), s("b ʌ s ɯ")) == [
        ("match", "b", "b"), ("match", "ʌ", "ʌ"), ("match", "s", "s"), ("ins", None, "ɯ")]


def test_nothing_heard_means_every_sound_deleted():
    assert align_sequences(s("k æ t"), []) == [("del", "k", None), ("del", "æ", None), ("del", "t", None)]


def test_nothing_expected_means_every_sound_inserted():
    assert align_sequences([], s("a")) == [("ins", None, "a")]


def test_both_empty():
    assert align_sequences([], []) == []


def test_real_sentence_from_step_12():
    """'Clubs and balls and cities grew to be only memories' (HKK a0020): expected vs what the model heard."""
    expected = s("k l ʌ b z ə n d b ɔː l z ə n d s ɪ t iː z ɡ ɹ uː t uː b iː oʊ n l iː m ɛ m ɚ iː z")
    heard = s("k l ʌ p s æ n b oː z ɪ n s ɪ ɾ i z ɡ ɹ uː t ʊ b iː oː l i m ɛ m ɚ ɹ i z")
    steps = align_sequences(expected, heard)
    assert [e for _, e, _ in steps if e is not None] == expected      # every expected sound appears once, in order
    assert [h for _, _, h in steps if h is not None] == heard         # every heard sound appears once, in order
    assert [x for x in steps if x[0] != "match"] == [
        ("sub", "b", "p"), ("sub", "z", "s"),                          # Clubs
        ("sub", "ə", "æ"), ("del", "d", None),                         # and
        ("sub", "ɔː", "oː"), ("del", "l", None),                       # balls  <- the real error
        ("sub", "ə", "ɪ"), ("del", "d", None),                         # and
        ("sub", "t", "ɾ"), ("sub", "iː", "i"),                         # cities (the t->ɾ flap is CORRECT US speech)
        ("sub", "uː", "ʊ"),                                            # to
        ("sub", "oʊ", "oː"), ("del", "n", None), ("sub", "iː", "i"),   # only
        ("ins", None, "ɹ"), ("sub", "iː", "i"),                        # memories
    ]
