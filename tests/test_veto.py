"""The second-opinion rule in eval/veto.py: a red from the live English listener only stands if the original
model also finds the sound wrong in the same time window."""
import random

import numpy as np

from backend.any_sound import accepted, dropped_ok
from eval.any_sound import flag
from eval.veto import NO_VETO, false_red_curve, flag2, flags, to_arrays


def row(**kw):
    r = dict(group="tune", speaker="bdl", utt="a1", cond="correct", target="l", other="w", margin=0.99, right=0.001,
             op="sub", o_other="w", o_margin=-0.8, o_right=0.9, alts=set(), next="", weak=False, func=False,
             between_consonants=False, skip=False)
    r.update(kw)
    return r


CUT = dict(m=0.9, rc=0.0005, rs=0.005)


def test_no_veto_is_exactly_the_old_rule():
    rng = random.Random(1)
    for _ in range(300):
        r = row(margin=rng.uniform(-1, 1), right=rng.choice([0.0001, 0.003, 0.3]), op=rng.choice(["sub", "del", "match"]),
                target=rng.choice(["l", "ə", "t", "iː"]), other=rng.choice(["w", "ə", "ɪ"]), weak=rng.random() < 0.3)
        assert flag2(r, **CUT, veto=NO_VETO) == flag(r, CUT["m"], CUT["rc"], CUT["rs"])


def test_swap_is_cancelled_when_the_original_model_hears_the_right_sound():
    r = row()                                            # live listener: L sounds like W; original: clearly L
    assert flag2(r, **CUT, veto=NO_VETO)
    assert not flag2(r, **CUT, veto=(0.0, np.inf))
    assert flag2(row(o_margin=0.4), **CUT, veto=(0.0, np.inf))   # original agrees: the red stands


def test_swap_is_cancelled_when_the_original_only_hears_a_native_variant():
    r = row(target="ɪ", other="iː", o_other="ə", o_margin=0.5, weak=True)   # weak vowel said "uh" is normal
    assert not flag2(r, **CUT, veto=(0.0, np.inf))


def test_left_out_sound_is_cancelled_when_the_original_hears_it():
    r = row(op="del", margin=-0.5, right=0.0001)
    assert flag2(r, **CUT, veto=NO_VETO)
    assert not flag2(r, **CUT, veto=(None, 0.1))         # original: right = 0.9, clearly there
    assert flag2(row(op="del", margin=-0.5, right=0.0001, o_right=0.01), **CUT, veto=(None, 0.1))


def test_fast_sentence_curve_matches_the_slow_rule():
    rng = random.Random(7)
    rows = []
    for s in range(40):
        for _ in range(rng.randint(3, 12)):
            rows.append(row(utt=f"u{s}", margin=rng.uniform(-1, 1), right=rng.choice([0.0001, 0.003, 0.3]),
                            op=rng.choice(["sub", "del", "match"]), target=rng.choice(["l", "ə", "t", "iː"]),
                            other=rng.choice(["w", "ə", "ɪ"]), o_other=rng.choice(["w", "ə", "l"]),
                            o_margin=rng.uniform(-1, 1), o_right=rng.choice([0.001, 0.05, 0.6])))
    a = to_arrays(rows)
    grid = np.array([-0.5, 0.0, 0.5, 0.9])
    for veto in (NO_VETO, (0.0, np.inf), (-0.3, 0.1)):
        curve = false_red_curve(a, CUT["rc"], CUT["rs"], veto, grid)
        for i, m in enumerate(grid):
            per = {}            # a sentence counts if any sound in it could ever fire (eval/any_sound.evaluate)
            for r in rows:
                if not accepted(r) or (r["op"] == "del" and not dropped_ok(r)):
                    per.setdefault(r["utt"], False)
            for r in rows:
                if r["utt"] in per:
                    per[r["utt"]] = per[r["utt"]] or flag2(r, m, CUT["rc"], CUT["rs"], veto)
            assert abs(curve[i] - np.mean(list(per.values()))) < 1e-9
            assert list(flags(a, m, CUT["rc"], CUT["rs"], veto)) == [flag2(r, m, CUT["rc"], CUT["rs"], veto) for r in rows]
