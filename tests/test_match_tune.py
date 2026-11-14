"""The threshold pickers in eval/match_tune.py."""
from eval.match_tune import gate_rejects, pick_gate, pick_lenient_gate, pick_word_rule, word_flags


def s(heard, conf, n_heard=10):
    return {"heard": heard, "conf": conf, "n_heard": n_heard}


def w(n, heard, conf):
    return {"n": n, "heard": heard, "conf": conf}


def test_nothing_heard_is_always_rejected():
    assert gate_rejects(s(0.9, 0.9, n_heard=0), {"min_heard": 0, "min_conf": 0})


def test_gate_keeps_false_rejections_under_the_cap_and_catches_the_rest():
    good = [s(0.7, 0.6)] * 199 + [s(0.3, 0.3)]          # one oddly low correct reading
    bad = [s(0.1, 0.1)] * 50 + [s(0.35, 0.35)] * 10
    t = pick_gate(good, bad, cap=0.01)
    assert sum(gate_rejects(g, t) for g in good) / len(good) <= 0.01
    assert sum(gate_rejects(b, t) for b in bad) == 60    # all bad ones caught (0.35 > the odd good one's 0.3)


def test_gate_with_cap_zero_never_rejects_a_good_reading():
    good = [s(0.7, 0.6), s(0.2, 0.15)]
    t = pick_gate(good, [s(0.1, 0.1)], cap=0.0)
    assert not any(gate_rejects(g, t) for g in good)


def test_lenient_gate_is_the_smallest_that_rejects_every_noise_clip():
    noise = [s(0.0, 0.0, n_heard=0), s(0.05, 0.08), s(0.1, 0.04)]
    t = pick_lenient_gate(noise)
    assert all(gate_rejects(x, t) for x in noise)
    assert not gate_rejects(s(0.12, 0.10), t)             # anything a bit above the noise passes


def test_word_rule_respects_the_false_alarm_cap():
    said = [w(4, 0.75, 0.7)] * 995 + [w(4, 0.25, 0.2)] * 5   # 0.5% of said words look missing
    missing = [w(4, 0.25, 0.2)] * 40 + [w(4, 0.0, 0.05)] * 60
    t = pick_word_rule(said, missing, cap=0.004)              # can't afford the 5 look-alikes
    assert sum(word_flags(x, t) for x in said) / len(said) <= 0.004
    assert sum(word_flags(x, t) for x in missing) == 60


def test_word_rule_ignores_words_shorter_than_min_sounds():
    assert not word_flags(w(1, 0.0, 0.0), {"min_sounds": 2, "max_heard": 0.5, "max_conf": 0.5})


def test_rate_of_nothing_is_empty_not_a_crash():
    # Korean words have no human labels -> "0 of 0" must report as unknown (found on the first real run)
    from eval.match_tune import rate
    assert rate(0, 0) == {"k": 0, "n": 0, "rate": None, "ci95": None}
