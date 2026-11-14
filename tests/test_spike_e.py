"""The pure parts of spikes/e_korean_model.py.
No model download needed: these test our symbol mapping, threshold picking and AUC."""
import itertools

from backend.g2p import CODA, ONSET, VOWEL, expected_phonemes
from spikes.e_korean_model import MFA_VOCAB, auc, pick_threshold, pooled, to_mfa


def toks(text):
    return [t for t, _ in to_mfa(expected_phonemes(text, "ko"))]


def test_stops_get_their_own_symbols():
    assert toks("빵") == ["BB", "A", "NG"]
    assert toks("피") == ["Ph", "I"]
    assert toks("불") == ["B", "U", "L"]


def test_tap_vowels_and_codas():
    assert toks("뿌리") == ["BB", "U", "R", "I"]        # ㄹ between vowels = tap R
    assert toks("밥") == ["B", "A", "p"]                # final ㅂ = unreleased p (lowercase)
    assert toks("국물") == ["G", "U", "NG", "M", "U", "L"]  # g2pk: 궁물
    assert toks("거기") == ["G", "EO", "G", "I"]
    assert toks("그림") == ["G", "EU", "R", "I", "M"]


def test_glide_and_vowel_become_one_symbol_and_share_both_phones():
    pairs = to_mfa(expected_phonemes("여기", "ko"))
    assert [t for t, _ in pairs] == ["iEO", "G", "I"]
    assert pairs[0][1] == [(0, 0), (0, 1)]             # j and ʌ both point at the iEO token


def test_every_syllable_maps_into_the_model_vocab():
    """Every onset x vowel x coda our G2P can produce lands on a symbol the model knows."""
    seen = set()
    for o, v, c in itertools.product(range(len(ONSET)), range(len(VOWEL)), range(len(CODA))):
        phones = ([ONSET[o]] if ONSET[o] else []) + VOWEL[v] + ([CODA[c]] if CODA[c] else [])
        word = {"word": "x", "pron": "x", "phonemes": phones}
        for t, _ in to_mfa([word]):
            seen.add(t)
    assert seen <= MFA_VOCAB


def test_pooled_names():
    assert pooled("ㅃ_as_ㅂ") == "tense_as_lenis"
    assert pooled("ㄱ_as_ㅋ") == "lenis_as_asp"
    assert pooled("ㅓ_as_ㅗ") == "ㅓ_as_ㅗ"             # vowels stay as they are


def test_pick_threshold_keeps_false_alarms_under_the_cap():
    correct = list(range(1000))                        # margins 0..999
    t = pick_threshold(correct, 0.005)
    assert sum(m > t for m in correct) <= 5
    assert sum(m > t for m in correct) == 5
    assert pick_threshold([], 0.005) is None
    small = [0.1, 0.2, 0.3]
    assert pick_threshold(small, 0.005) == 0.3         # too few to allow any: flag only above the max


def test_auc():
    assert auc([3, 4], [1, 2]) == 1.0
    assert auc([1, 2], [3, 4]) == 0.0
    assert auc([1], [1]) == 0.5
