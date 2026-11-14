"""Tests for eval/sim_validate.py: does a simulated error set predict real learner results?"""
from backend.g2p import expected_phonemes
from eval.sim_validate import SAID, error_positions, spearman, swap_target, upper_bound_ok


def test_said_sound_per_pair():
    assert SAID["r_as_l"] == "l" and SAID["l_as_r"] == "ɹ"
    assert SAID["f_as_p"] == "p" and SAID["ih_as_iy"] == "iː"


def test_error_positions_find_the_said_sound():
    words = expected_phonemes("light", "en")       # l aɪ t
    assert (0, 0) in error_positions(words, "r_as_l")  # the native said l; a target of ɹ makes it "R said as L"
    assert error_positions(words, "l_as_r") == []    # no ɹ to swap


def test_swap_target_changes_one_phoneme_and_copies():
    words = expected_phonemes("light", "en")
    new = swap_target(words, 0, 0, "ɹ")
    assert new[0]["phonemes"] == ["ɹ", "aɪ", "t"]
    assert words[0]["phonemes"] == ["l", "aɪ", "t"]  # original untouched


def test_spearman():
    assert spearman([1, 2, 3], [10, 20, 30]) == 1.0
    assert spearman([1, 2, 3], [3, 2, 1]) == -1.0
    assert abs(spearman([1, 2, 2, 3], [1, 2, 3, 4]) - 0.9487) < 1e-3  # ties get average ranks


def test_upper_bound_ok():
    assert upper_bound_ok(0.9, 7, 14)        # real 50% is below simulated 90%
    assert upper_bound_ok(0.4, 7, 14)        # real 50% (CI 27-73%) is not SIGNIFICANTLY above 40%
    assert not upper_bound_ok(0.1, 13, 14)   # real 93% (CI ~69-99%) is clearly above 10%
    assert upper_bound_ok(0.0, 0, 0) is None  # no real errors: can't say
