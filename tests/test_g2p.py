"""G2P wrappers. Text -> the phonemes a native speaker would say, word by word.

Expected values come from what g2pk 0.9.4 and g2p_en 2.1.0 actually output (run on
2026-11-12), converted to IPA with our tables. Korean IPA is phonemic (lenis ㅂㄷㄱ stay p t k
even where they sound voiced), except ㄹ: tap [ɾ] before a vowel, [l] at a syllable end and in ㄹㄹ.
Tense = p͈ t͈ k͈ s͈ t͈ɕ, aspirated = pʰ tʰ kʰ tɕʰ.
"""
import pytest

from backend.g2p import expected_phonemes


def phonemes(text, lang):
    """Just the phoneme lists, one per word."""
    return [w["phonemes"] for w in expected_phonemes(text, lang)]


# ---------- Korean: the sound-change rules g2pk applies ----------
@pytest.mark.parametrize("text, pron, ipa", [
    ("같이", "가치", ["k", "a", "tɕʰ", "i"]),                            # palatalization: ㅌ+이 -> 치
    ("국물", "궁물", ["k", "u", "ŋ", "m", "u", "l"]),                      # nasal assimilation: ㄱ+ㅁ -> ㅇㅁ
    ("읽다", "익따", ["i", "k", "t͈", "a"]),                               # cluster simplification + tensing
    ("맛있어요", "마시써요", ["m", "a", "s", "i", "s͈", "ʌ", "j", "o"]),     # liaison: final ㅆ moves to the next syllable
    ("신라", "실라", ["s", "i", "l", "l", "a"]),                          # lateralization: ㄴ+ㄹ -> ㄹㄹ
    ("학생", "학쌩", ["h", "a", "k", "s͈", "ɛ", "ŋ"]),                     # tensing after a final ㄱ
    ("좋아요", "조아요", ["tɕ", "o", "a", "j", "o"]),                      # ㅎ drops before a vowel
])
def test_korean_sound_changes(text, pron, ipa):
    [word] = expected_phonemes(text, "ko")
    assert word["word"] == text
    assert word["pron"] == pron
    assert word["phonemes"] == ipa


def test_korean_r_is_a_tap_before_a_vowel_and_l_elsewhere():
    assert phonemes("라면", "ko") == [["ɾ", "a", "m", "j", "ʌ", "n"]]      # tap
    assert phonemes("몰라요", "ko") == [["m", "o", "l", "l", "a", "j", "o"]]  # ㄹㄹ = [ll]
    assert phonemes("물", "ko") == [["m", "u", "l"]]                       # final ㄹ = [l]


def test_korean_rules_work_across_words():
    # 먹을 것 -> 머글 껃: liaison inside 먹을, tensing of ㄱ after -을 across the space
    words = expected_phonemes("먹을 것", "ko")
    assert [w["word"] for w in words] == ["먹을", "것"]
    assert [w["pron"] for w in words] == ["머글", "껃"]
    assert [w["phonemes"] for w in words] == [["m", "ʌ", "k", "ɯ", "l"], ["k͈", "ʌ", "t"]]


def test_korean_punctuation_is_dropped():
    assert expected_phonemes("안녕하세요.", "ko") == [
        {"word": "안녕하세요", "pron": "안녕하세요",
         "phonemes": ["a", "n", "n", "j", "ʌ", "ŋ", "h", "a", "s", "e", "j", "o"]}]


# ---------- English: g2p_en (ARPAbet) -> IPA ----------
@pytest.mark.parametrize("text, ipa", [
    ("cat", ["k", "æ", "t"]),
    ("knight", ["n", "aɪ", "t"]),                  # silent k
    ("colonel", ["k", "ɚ", "n", "ə", "l"]),        # spelling tells you nothing here
    ("ship", ["ʃ", "ɪ", "p"]),
    ("sheep", ["ʃ", "iː", "p"]),
])
def test_english_words(text, ipa):
    assert phonemes(text, "en") == [ipa]


def test_english_keeps_arpabet_with_stress():
    [word] = expected_phonemes("colonel", "en")
    assert word["pron"] == "K ER1 N AH0 L"   # stress digits kept: useful later for stressed-syllable checks


def test_english_sentence_splits_into_words_and_drops_punctuation():
    words = expected_phonemes("Hello, world!", "en")
    assert [w["word"] for w in words] == ["Hello", "world"]
    assert [w["phonemes"] for w in words] == [["h", "ə", "l", "oʊ"], ["w", "ɚ", "l", "d"]]


# ---------- bad input ----------
@pytest.mark.parametrize("text, lang", [("?!", "ko"), ("...", "en"), ("   ", "en")])
def test_no_words_raises(text, lang):
    with pytest.raises(ValueError):
        expected_phonemes(text, lang)


def test_unknown_language_raises():
    with pytest.raises(ValueError):
        expected_phonemes("hola", "es")
