"""Slplab as a second listener (private test).py."""
import math

import numpy as np
import pytest

from backend.detector import FEATURE_NAMES, fit, vectorize

from eval import slplab as slp

VOCAB = {"<pad>": 0, "l": 1, "r": 2, "r_err": 3, "b": 4, "b*": 5, "v": 6, "eu": 7, "l_err": 8, "s": 9}
SPF = 0.02   # seconds per frame, like wav2vec2


def lp(frames, hot):
    """(frames, vocab) log-probs: frame i puts 0.97 on token hot[i] (default <pad>), the rest spread evenly."""
    n = len(VOCAB)
    p = np.full((frames, n), 0.03 / (n - 1))
    for i in range(frames):
        p[i, VOCAB[hot.get(i, "<pad>")]] = 0.97
    return np.log(p)


def test_heard_wrong_only_inside_the_window():
    # target L at 0.20-0.30 s = frames 10-15; slplab says "r" at frame 12 -> heard the mistake
    f = slp.window_features(lp(40, {12: "r"}), SPF, 0.20, 0.30, "l_as_r", VOCAB)
    assert f["s_heard_wrong"] == 1 and f["s_margin"] > 0
    # the same "r" far outside the window (frame 35 = 0.70 s) does not count
    g = slp.window_features(lp(40, {35: "r"}), SPF, 0.20, 0.30, "l_as_r", VOCAB)
    assert g["s_heard_wrong"] == 0


def test_margin_sign_follows_which_sound_wins():
    right = slp.window_features(lp(40, {12: "l"}), SPF, 0.20, 0.30, "l_as_r", VOCAB)
    wrong = slp.window_features(lp(40, {12: "r"}), SPF, 0.20, 0.30, "l_as_r", VOCAB)
    assert right["s_margin"] < 0 < wrong["s_margin"]


def test_err_and_star_variants_count_as_the_sound():
    # "r_err" is still an r; "b*" is still a b (v_as_b: target v, mistake b)
    assert slp.window_features(lp(40, {12: "r_err"}), SPF, 0.20, 0.30, "l_as_r", VOCAB)["s_heard_wrong"] == 1
    assert slp.window_features(lp(40, {12: "b*"}), SPF, 0.20, 0.30, "v_as_b", VOCAB)["s_heard_wrong"] == 1


def test_err_score_is_the_strongest_err_frame():
    f = slp.window_features(lp(40, {12: "l_err"}), SPF, 0.20, 0.30, "l_as_r", VOCAB)
    assert f["s_err"] == pytest.approx(0.97, abs=0.01)
    assert slp.window_features(lp(40, {12: "l"}), SPF, 0.20, 0.30, "l_as_r", VOCAB)["s_err"] < 0.05


def test_extra_vowel_looks_just_after_the_consonant():
    # final consonant 0.20-0.30 s; an inserted "eu" 0.1 s later counts, one 0.3 s later does not
    near = slp.window_features(lp(40, {20: "eu"}), SPF, 0.20, 0.30, "extra_vowel", VOCAB)
    far = slp.window_features(lp(40, {30: "eu"}), SPF, 0.20, 0.30, "extra_vowel", VOCAB)
    assert near["s_heard_wrong"] == 1 and far["s_heard_wrong"] == 0
    assert near["s_margin"] > far["s_margin"]


def test_window_at_the_edges_does_not_crash():
    f = slp.window_features(lp(10, {}), SPF, 0.0, 0.5, "l_as_r", VOCAB)   # runs past the last frame
    assert set(f) == set(slp.S_COLS) and all(math.isfinite(v) for v in f.values())


def _row(source, spk, utt, wi, pi, pair, group="korean", human="correct"):
    return {"source": source, "speaker": f"{source}:{spk}", "utt": utt, "word_index": str(wi),
            "phoneme_index": str(pi), "pair": pair, "group": group, "human": human}


def test_attach_joins_on_corpus_speaker_utt_sound_and_pair():
    rows = [_row("l2arctic", "HJK", "a1", 0, 1, "l_as_r"), _row("saa", "HJK", "a1", 0, 1, "l_as_r")]
    feats = {("l2arctic", "HJK", "a1", 0, 1, "l_as_r"): {"s_margin": "1.5", "s_heard_wrong": "1", "s_err": "0.2"}}
    slp.attach(rows, feats)
    assert rows[0]["s_margin"] == "1.5" and "s_margin" not in rows[1]   # same ids, other corpus: no match


def test_recordings_needed_skips_other_pairs_and_unlabelled_rows():
    rows = [_row("l2arctic", "HJK", "a1", 0, 1, "l_as_r"),
            _row("l2arctic", "HJK", "a2", 0, 1, "r_as_l"),                  # live pair, not part of the slplab test
            _row("l2arctic", "HJK", "a3", 0, 1, "th_as_s", human="other"),   # not correct/error
            _row("saa", "korean1", "paragraph", 3, 0, "dh_as_d", human="error")]
    assert slp.recordings_needed(rows) == {("l2arctic", "HJK", "a1"), ("saa", "korean1", "paragraph")}


def test_fit_keeps_the_names_it_was_given():
    names = FEATURE_NAMES + slp.S_COLS
    rng = np.random.default_rng(0)
    rows = [dict({n: rng.normal() for n in names}, s_margin=float(i % 2) * 4) for i in range(60)]
    y = np.array([i % 2 for i in range(60)], dtype=float)
    model = fit(vectorize(rows, names), y, names=names)
    assert model["names"] == list(names) and len(model["w"]) == len(names)
    assert max(zip(model["w"], names))[1] == "s_margin"   # the one clue that separates gets the biggest weight


def test_evaluate_pair_with_the_extra_columns_reports_their_weights():
    from eval.detectors import evaluate_pair
    rng = np.random.default_rng(1)
    rows = []
    for i in range(400):
        err = i % 10 == 0
        rows.append({"group": "others" if i < 300 else "korean", "human": "error" if err else "correct",
                     "speaker": f"s{i % 20}", "source": "l2arctic", "margin": rng.normal(), "heard_agrees": 0,
                     "baseline_flag": False, "utt": "u", "pair": "th_as_s", "f3_dip": None, "fric": None, "closure": None,
                     "op": "match", "s_margin": (5.0 if err else 0.0) + rng.normal() * 0.1,
                     "s_heard_wrong": int(err), "s_err": 0.0})
    res = evaluate_pair(rows, 0.005, names=FEATURE_NAMES + slp.S_COLS)
    assert res["feasible"] and "s_margin" in res["weights"]
