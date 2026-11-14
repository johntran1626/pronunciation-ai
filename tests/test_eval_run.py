"""The tuning math in eval/run.py (tiny hand-made numbers)."""
import pytest

from eval.run import count, pick_margin, wilson


def rows(margins, agrees=None, human="correct"):
    agrees = agrees or [1] * len(margins)
    return [{"margin": m, "heard_agrees": a, "human": human} for m, a in zip(margins, agrees)]


CORRECT = rows([-0.9, -0.5, 0.1, 0.3])


def test_pick_margin_is_the_lowest_that_keeps_false_alarms_under_the_cap():
    assert pick_margin(CORRECT, "A", cap=0.25) == 0.1    # flag only > 0.1 -> 1 of 4 correct flagged = 25%
    assert pick_margin(CORRECT, "A", cap=0.0) == 0.3     # nothing flagged
    assert pick_margin(CORRECT, "A", cap=1.0) < -0.9     # cap 100%: flag everything


def test_variant_b_only_counts_sounds_the_recognizer_also_heard_wrong():
    correct = rows([-0.9, -0.5, 0.1, 0.3], agrees=[0, 0, 1, 0])
    assert pick_margin(correct, "B", cap=0.0) == 0.1


def test_count_flags():
    errors = rows([0.5, 0.0, -0.2], human="error")
    assert count(errors, "A", 0.1) == (1, 3)              # 1 of 3 errors is above 0.1


def test_wilson_interval():
    lo, hi = wilson(20, 27)
    assert 0.53 < lo < 0.56 and 0.86 < hi < 0.89          # spikes/c_rl.py: 74%, CI 55-87%
    assert wilson(0, 0) is None


def test_precision_is_the_share_of_reds_that_were_real_errors():
    from eval.run import precision
    assert precision(caught=5, false_alarms=7) == 5 / 12      # extra vowel at 0.5%: most reds wrong
    assert precision(caught=0, false_alarms=0) is None         # no reds at all: undefined


def test_each_pair_can_have_its_own_cap(monkeypatch):
    import eval.run as er
    assert er.cap_for("r_as_l") == 0.005 and er.cap_for("v_as_b") == 0.005   # everything 0.5% now
    monkeypatch.setitem(er.PAIR_CAPS, "r_as_l", 0.01)                         # an override still works
    assert er.cap_for("r_as_l") == 0.01


# ---------- the F3 tie-breaker rule (variant F) ----------
from eval.run import flag_t, pick_f3_rule  # noqa: E402


def f3rows(pairs, human):
    return [{"margin": m, "heard_agrees": 0, "f3_dip": d, "human": human} for m, d in pairs]


def test_f3_rule_flags_borderline_only_when_f3_dips():
    t = {"variant": "F", "margin": 0.8, "m_lo": 0.0, "dip": -1.0}
    assert flag_t({"margin": 0.9, "heard_agrees": 0, "f3_dip": 2.0}, t)       # recognizer sure: red
    assert flag_t({"margin": 0.3, "heard_agrees": 0, "f3_dip": -2.0}, t)      # borderline + R-like F3: red
    assert not flag_t({"margin": 0.3, "heard_agrees": 0, "f3_dip": 0.5}, t)   # borderline + L-like F3: green
    assert not flag_t({"margin": 0.3, "heard_agrees": 0, "f3_dip": None}, t)  # borderline, F3 unknown: green
    assert not flag_t({"margin": -0.5, "heard_agrees": 0, "f3_dip": -3.0}, t) # recognizer says L: green


def test_pick_f3_rule_rescues_a_borderline_error_without_false_alarms():
    correct = f3rows([(-0.9, 0.2), (-0.5, -0.3), (0.4, 0.8), (0.5, 0.1)], "correct")  # borderline correct L's: F3 high
    errors = f3rows([(0.45, -2.0), (0.9, -1.5)], "error")                           # borderline error: F3 low
    rule = pick_f3_rule(correct, errors, cap=0.0)
    assert rule["tune_caught"] == 2 and rule["tune_false_alarms"] == 0


def test_flag_t_matches_old_variants():
    r = {"margin": 0.3, "heard_agrees": 0, "f3_dip": None}
    assert flag_t(r, {"variant": "A", "margin": 0.2})
    assert not flag_t(r, {"variant": "B", "margin": 0.2})


def test_f3_rule_is_never_worse_than_the_plain_margin_on_tuning_data():
    # 'margin > m, F3 never used' is one of F's options, so F must catch at least as many as variant A.
    # Regression (2026-11-12): a 25-point grid skipped A's exact margin (0.94 here) and caught 0.
    correct = f3rows([(i / 100, 0.0) for i in range(100)], "correct")
    errors = f3rows([(0.945, 1.0)], "error")
    m = pick_margin(correct, "A", cap=0.05)
    rule = pick_f3_rule(correct, errors, cap=0.05)
    assert rule["tune_caught"] >= count(errors, "A", m)[0] == 1


# ---------- the tie-breaker rule on a named feature ----------
def test_pick_f3_rule_can_use_another_feature():
    rows = lambda pairs, human: [{"margin": m, "heard_agrees": 0, "fric": f, "human": human} for m, f in pairs]
    correct = rows([(-0.9, -5.0), (0.4, -8.0), (0.5, -6.0)], "correct")
    errors = rows([(0.45, -30.0)], "error")
    rule = pick_f3_rule(correct, errors, cap=0.0, feature="fric")
    assert rule["feature"] == "fric" and rule["tune_caught"] == 1 and rule["tune_false_alarms"] == 0
    assert flag_t(errors[0], rule) and not any(flag_t(r, rule) for r in correct)


# ---------- the false-alarm gate must use the exact rate, not the rounded one ----------
def test_gate_rejects_a_false_alarm_rate_just_over_the_cap():
    from eval.run import evaluate_pair
    tune = [{"pair": "r_as_l", "group": "others", "human": "correct", "margin": -0.9, "heard_agrees": False,
             "baseline_flag": False}] * 10
    tune += [{"pair": "r_as_l", "group": "others", "human": "error", "margin": 0.9, "heard_agrees": True,
              "baseline_flag": True}]
    # Korean test: 4 false alarms in 793 correct = 0.504%, which rounds to 0.0050 but is OVER the 0.5% cap
    test = [{"pair": "r_as_l", "group": "korean", "human": "correct", "margin": m, "heard_agrees": a,
             "baseline_flag": False} for m, a in [(0.9, True)] * 4 + [(-0.9, False)] * 789]
    test += [{"pair": "r_as_l", "group": "korean", "human": "error", "margin": 0.9, "heard_agrees": True,
              "baseline_flag": True}] * 10
    res = evaluate_pair(tune + test, cap=0.005)
    assert res["test (korean)"]["false_alarms"]["k"] == 4 and res["test (korean)"]["false_alarms"]["n"] == 793
    assert res["enabled"] is False
