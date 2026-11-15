"""Korean checks with the Korean-trained listener: which sounds get a check, the red rule, the cut, the bars."""
import io

import pytest

from backend.g2p import expected_phonemes
from backend.korean_listener import CHECKS, candidates, fires
from eval.korean_checks import bars, cut_from_natives, pooled_check


def _checks_for(text):
    words = expected_phonemes(text, "ko")
    return {(c["wi"], c["pi"], c["check"]) for c in candidates(words)}


# ---------- which sounds get a check ----------
def test_the_ten_candidate_checks_are_fixed_before_any_run():
    assert set(CHECKS) == {"ㅓ_as_ㅗ", "ㅗ_as_ㅓ", "ㅡ_as_ㅜ", "ㅜ_as_ㅡ",
                           "lenis_as_tense", "lenis_as_asp", "tense_as_lenis", "tense_as_asp",
                           "asp_as_lenis", "asp_as_tense"}


def test_a_spelled_tense_stop_gets_both_tense_checks():
    # 꼬리: ㄲ is written, so an English puff (tense said as aspirated) can be checked
    assert {(0, 0, "tense_as_lenis"), (0, 0, "tense_as_asp")} <= _checks_for("꼬리")


def test_a_tense_sound_made_only_by_a_sound_rule_is_never_checked():
    # 학교 is said 학꾜: the ㄲ sound comes from a rule, the spelling has ㄱ
    words = expected_phonemes("학교", "ko")
    tense_at = words[0]["phonemes"].index("k͈")
    assert not any(pi == tense_at for (_, pi, _) in _checks_for("학교"))


def test_an_aspirated_sound_made_by_merging_with_h_is_never_checked():
    words = expected_phonemes("좋다", "ko")        # said 조타: ㅌ is not written
    asp_at = words[0]["phonemes"].index("tʰ")
    assert not any(pi == asp_at for (_, pi, _) in _checks_for("좋다"))


def test_plain_vowels_get_their_pair_check_but_glides_do_not():
    assert (0, 0, "ㅓ_as_ㅗ") in _checks_for("어")
    assert not any(c.startswith("ㅓ") for (_, _, c) in _checks_for("여"))   # ㅕ is one glide symbol (iEO)


def test_a_final_unreleased_stop_is_not_a_stop_check():
    words = expected_phonemes("밥", "ko")
    last = len(words[0]["phonemes"]) - 1
    assert not any(pi == last for (_, pi, _) in _checks_for("밥"))


# ---------- the red rule ----------
def test_red_needs_both_a_big_margin_and_the_wrong_sound_heard():
    assert fires({"margin": 0.9, "heard_said": 1}, 0.5)
    assert not fires({"margin": 0.9, "heard_said": 0}, 0.5)   # far, but the model didn't write the wrong sound
    assert not fires({"margin": 0.3, "heard_said": 1}, 0.5)   # heard it, but not by a clear margin


def test_pooled_check_names_the_stop_types():
    assert pooled_check("ㅃ_as_ㅍ") == "tense_as_asp"
    assert pooled_check("ㅓ_as_ㅗ") == "ㅓ_as_ㅗ"


# ---------- the cut, from native speakers ----------
def _rows(margins, heard=1):
    return [{"margin": m, "heard_said": heard} for m in margins]


def test_cut_lets_at_most_the_tune_cap_of_native_sounds_fire():
    natives = _rows([0.95, 0.9, 0.8] + [0.1] * 997)          # 1,000 correct native sounds
    cut = cut_from_natives(natives, cap=0.0025)             # 0.25% of 1,000 = 2 may fire
    assert sum(fires(r, cut) for r in natives) <= 2
    assert cut == 0.8


def test_cut_is_never_below_zero_the_model_must_lean_to_the_mistake():
    natives = _rows([-0.5] * 100)
    assert cut_from_natives(natives, cap=0.0025) == 0.0


# ---------- the four bars ----------
def _learner(speaker, rating, fired, n):
    return [{"speaker": speaker, "rating": rating, "margin": 0.9 if i < fired else 0.0, "heard_said": 1}
            for i in range(n)]


def _passing_inputs():
    natives_test = _rows([0.0] * 1000)                                            # 0 false alarms
    errors = [dict(r, speaker=f"s{i % 6}") for i, r in enumerate(_rows([0.9] * 40 + [0.0] * 60))]
    learners = []
    for s in range(20):
        learners += _learner(f"a{s}", 3, 0, 50)      # 상: 0 of 1,000 fire
        learners += _learner(f"a{s}", 2, 5, 50)      # 중: 10% fire
    return natives_test, errors, learners


def test_all_four_bars_pass_on_a_clean_detector():
    v = bars(*_passing_inputs(), cut=0.5)
    assert v["live"] is True
    assert all(v[b]["pass"] for b in ("bar1", "bar2", "bar3", "bar4"))


def test_bar1_fails_when_natives_go_red_too_often():
    natives_test, errors, learners = _passing_inputs()
    natives_test = _rows([0.9] * 6 + [0.0] * 994)          # 0.6% > 0.5%
    v = bars(natives_test, errors, learners, cut=0.5)
    assert v["bar1"]["pass"] is False and v["live"] is False


def test_bar2_fails_when_top_rated_learners_go_red_too_often():
    natives_test, errors, _ = _passing_inputs()
    learners = []
    for s in range(20):
        learners += _learner(f"a{s}", 3, 1, 50)      # 상: 2% fire
        learners += _learner(f"a{s}", 2, 5, 50)
    v = bars(natives_test, errors, learners, cut=0.5)
    assert v["bar2"]["pass"] is False and v["live"] is False


def test_bar3_fails_when_worse_speech_does_not_fire_more():
    natives_test, errors, _ = _passing_inputs()
    learners = []
    for s in range(20):
        learners += _learner(f"a{s}", 3, 0, 50)
        learners += _learner(f"a{s}", 2, 0, 50)      # 중 fires no more than 상
    v = bars(natives_test, errors, learners, cut=0.5)
    assert v["bar3"]["pass"] is False and v["live"] is False


def test_bar4_fails_when_it_catches_under_a_quarter_of_big_errors():
    natives_test, _, learners = _passing_inputs()
    errors = [dict(r, speaker=f"s{i % 6}") for i, r in enumerate(_rows([0.9] * 20 + [0.0] * 80))]
    v = bars(natives_test, errors, learners, cut=0.5)
    assert v["bar4"]["pass"] is False and v["live"] is False


def test_too_little_data_is_never_live():
    natives_test, _, learners = _passing_inputs()
    errors = [dict(r, speaker="s0") for r in _rows([0.9] * 10)]   # 10 errors, 1 speaker
    v = bars(natives_test, errors, learners, cut=0.5)
    assert v["bar4"]["pass"] is False and v["live"] is False


# ---------- the real model, on one native recording ----------
@pytest.mark.skipif(not __import__("pathlib").Path("data/zeroth/data").exists(), reason="Zeroth not downloaded")
def test_live_model_measures_a_native_recording_and_rarely_hears_the_wrong_sound():
    import pyarrow.parquet as pq
    import soundfile as sf
    from backend.korean_listener import measure
    from eval.korean_sim import SOURCES

    _, path, _ = [s for s in SOURCES if s[0] == "test"][0]
    rows_seen = []
    for r in pq.read_table(path).to_pylist()[:3]:
        audio, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
        rows_seen += measure(audio, sr, expected_phonemes(r["text"], "ko"))
    assert rows_seen, "native sentences have checkable sounds"
    assert all(-1.0 <= r["margin"] <= 1.0 for r in rows_seen)
    assert sum(r["heard_said"] for r in rows_seen) / len(rows_seen) < 0.1
