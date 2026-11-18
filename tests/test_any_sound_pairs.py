"""Per-pair cut-offs for the every-sound English check (eval/any_sound.py pair_cuts / choose_safety)."""
import pytest

from eval.any_sound import FLOOR, MIN_N, pair_cuts


def ok(target, other, margin, speaker="bdl", utt="a1", accepted_variant=False):
    """A CORRECT tune sound whose best other sound is `other` (accepted_variant: a native variant, never red)."""
    return dict(target=target, other=other, margin=margin, speaker=speaker, utt=utt, weak=accepted_variant,
                func=False, next="", alts=set(), between_consonants=False, op="match", right=0.5, skip=False,
                cond="correct", group="tune", human="")


def test_settings_fixed_before_tuning():
    assert FLOOR == 0.25 and MIN_N == 100


def test_pair_cut_is_the_worst_correct_margin_plus_safety_never_below_the_floor_or_above_global():
    rows = [ok("ɪ", "ʌ", -0.9)] * 50 + [ok("ɪ", "ʌ", 0.05)] + [ok("ɪ", "ə", 0.6)] + [ok("ɪ", "iː", -0.5)] * 60
    cuts = pair_cuts(rows, global_m=0.95, safety=0.1, floor=0.25, min_n=100)
    assert cuts["ɪ ʌ"] == pytest.approx(0.25)          # 0.05 + 0.1 is under the floor
    assert cuts["ɪ ə"] == pytest.approx(0.7)           # 0.6 + 0.1
    assert cuts["ɪ *"] == pytest.approx(0.7)           # an "other" never seen: bounded by the worst best-other margin
    assert "ɪ iː" in cuts and cuts["ɪ iː"] == pytest.approx(0.25)


def test_rare_targets_and_cuts_at_or_above_global_are_left_out():
    rows = [ok("ʒ", "ʃ", -0.9)] * 20 + [ok("s", "z", 0.9)] + [ok("s", "θ", -0.8)] * 150
    cuts = pair_cuts(rows, global_m=0.95, safety=0.1, floor=0.25, min_n=100)
    assert not any(k.startswith("ʒ ") for k in cuts)  # 20 correct examples: too few to trust, keeps the global cut
    assert "s z" not in cuts and "s *" not in cuts     # 0.9 + 0.1 >= 0.95: no gain, keep the global cut
    assert cuts["s θ"] == pytest.approx(0.25)


def test_native_variants_dont_set_the_cut():
    # a weak ɪ heard as ʌ is accepted (never red), so it must not push the ɪ ʌ cut up
    rows = [ok("ɪ", "ʌ", 0.8, accepted_variant=True)] + [ok("ɪ", "ʌ", -0.5)] * 120
    assert pair_cuts(rows, global_m=0.95, safety=0.1, floor=0.25, min_n=100)["ɪ ʌ"] == pytest.approx(0.25)


def test_never_blurred_vowel_pairs_include_pairs_never_seen_and_skip_blurred_or_rare_targets():
    from backend.any_sound import VOWELS
    from eval.any_sound import never_blurred_pairs
    rows = ([ok("ʌ", "ə", -0.2)] * 120 + [ok("ʌ", "ɑː", 0.85)]                 # ʌ leans to ɑː once: blurred
            + [ok("ʌ", "æ", 0.9, accepted_variant=True)]                      # a weak syllable never counts
            + [ok("ʊ", "uː", -0.5)] * 20                                       # too few ʊ to judge
            + [ok("k", "t", -0.9)] * 200)                                      # consonants are not part of it
    pairs = never_blurred_pairs(rows, cut=0.8, min_n=100)
    assert "ʌ æ" in pairs and "ʌ ɪ" in pairs                           # never seen at all still counts
    assert "ʌ ɑː" not in pairs and "ʌ ʌ" not in pairs
    assert not any(p.startswith("ʊ ") or p.startswith("k ") for p in pairs)
    assert all(set(p.split()) <= VOWELS for p in pairs) and pairs == sorted(pairs)
