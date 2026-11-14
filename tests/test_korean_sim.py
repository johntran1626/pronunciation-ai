"""Tests for eval/korean_sim.py: simulated Korean learner errors by text swap."""
import random

from backend.g2p import expected_phonemes
from eval.korean_sim import PAIRS, sample_variants, summarize, swap_syllable, variants


def _flat(text):
    return [(wi, pi, p) for wi, w in enumerate(expected_phonemes(text, "ko")) for pi, p in enumerate(w["phonemes"])]


# ---------- swapping one jamo inside a syllable block ----------
def test_swap_onset():
    assert swap_syllable("불", "onset", "ㅂ", "ㅍ") == "풀"


def test_swap_keeps_vowel_and_coda():
    assert swap_syllable("밥", "onset", "ㅂ", "ㅃ") == "빱"


def test_swap_vowel():
    assert swap_syllable("고", "vowel", "ㅗ", "ㅓ") == "거"


def test_swap_wrong_jamo_is_none():
    assert swap_syllable("불", "onset", "ㄷ", "ㅌ") is None
    assert swap_syllable("a", "onset", "ㅂ", "ㅍ") is None  # not Hangul


# ---------- the pair list ----------
def test_pairs_cover_vowels_and_all_stop_directions():
    assert {"ㅓ_as_ㅗ", "ㅗ_as_ㅓ", "ㅡ_as_ㅜ", "ㅜ_as_ㅡ"} <= set(PAIRS)
    for series in ("ㅂㅃㅍ", "ㄷㄸㅌ", "ㄱㄲㅋ"):
        for target in series:
            for said in series:
                if target != said:
                    assert f"{target}_as_{said}" in PAIRS


# ---------- variants: the one-difference rule ----------
def test_variant_example_bap():
    vs = variants("밥을 먹어요")
    hit = [v for v in vs if v["pair"] == "ㅍ_as_ㅂ" and v["word_index"] == 0 and v["phoneme_index"] == 0]
    assert len(hit) == 1
    assert hit[0]["target_text"] == "팝을 먹어요"
    assert (hit[0]["target_ipa"], hit[0]["said_ipa"]) == ("pʰ", "p")


def test_every_variant_differs_in_exactly_one_place():
    text = "밥을 먹어요 그리고 커피도 마셔요"
    original = _flat(text)
    vs = variants(text)
    assert vs, "expected some variants"
    for v in vs:
        swapped = _flat(v["target_text"])
        assert len(swapped) == len(original)
        diffs = [(a[0], a[1]) for a, b in zip(original, swapped) if a[2] != b[2]]
        assert diffs == [(v["word_index"], v["phoneme_index"])], v
        assert original[[i for i, a in enumerate(original) if (a[0], a[1]) == diffs[0]][0]][2] == v["said_ipa"]


def test_tensed_context_is_dropped():
    # 학교 is said 학꾜: the written ㄱ is already tense, so swapping it never gives a clean "ㄱ said as X"
    assert variants("학교") == []


# ---------- sampling ----------
def test_sample_at_most_one_per_pair_and_reproducible():
    vs = [dict(pair="ㅍ_as_ㅂ", n=i) for i in range(5)] + [dict(pair="ㅗ_as_ㅓ", n=i) for i in range(3)]
    a = sample_variants(vs, random.Random(0))
    b = sample_variants(vs, random.Random(0))
    assert a == b
    assert sorted(v["pair"] for v in a) == ["ㅍ_as_ㅂ", "ㅗ_as_ㅓ"]


# ---------- summary ----------
def test_summarize_counts_and_rates():
    rows = [
        dict(group="test", speaker="s1", pair="ㅍ_as_ㅂ", human="error", baseline_flag=1, app_flag=0),
        dict(group="test", speaker="s2", pair="ㅍ_as_ㅂ", human="error", baseline_flag=0, app_flag=0),
        dict(group="test", speaker="s1", pair="ㅍ_as_ㅂ", human="correct", baseline_flag=1, app_flag=0),
        dict(group="test", speaker="s1", pair="ㅍ_as_ㅂ", human="correct", baseline_flag=0, app_flag=0),
        dict(group="test", speaker="s1", pair="ㅍ_as_ㅂ", human="correct", baseline_flag=0, app_flag=0),
        dict(group="test", speaker="s1", pair="ㅍ_as_ㅂ", human="correct", baseline_flag=0, app_flag=0),
        dict(group="tune", speaker="s9", pair="ㅍ_as_ㅂ", human="error", baseline_flag=1, app_flag=0),
    ]
    s = summarize(rows)["test"]["ㅍ_as_ㅂ"]
    assert (s["errors"], s["error_speakers"], s["correct"]) == (2, 2, 4)
    assert s["baseline"]["caught"] == 1 and s["baseline"]["detection"] == 0.5
    assert s["baseline"]["false_alarms"] == 1 and s["baseline"]["false_alarm_rate"] == 0.25
    assert s["app"]["caught"] == 0 and s["app"]["false_alarms"] == 0
    assert summarize(rows)["tune"]["ㅍ_as_ㅂ"]["errors"] == 1
