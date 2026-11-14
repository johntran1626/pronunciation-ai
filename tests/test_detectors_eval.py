"""eval/detectors.py, the pre-registered detector pass, on small made-up rows."""
import numpy as np

from eval.detectors import attach_saa_features, evaluate_pair, pick_threshold, speaker_folds


def test_speaker_folds_keep_each_speaker_in_one_fold():
    spk = ["a", "a", "b", "c", "c", "c", "d", "e", "f"]
    folds = speaker_folds(spk, k=3)
    assert len(folds) == len(spk) and set(folds) <= {0, 1, 2}
    for s in set(spk):
        assert len({f for f, x in zip(folds, spk) if x == s}) == 1
    assert list(folds) == list(speaker_folds(spk, k=3))   # same split every run


def test_pick_threshold_is_the_lowest_with_few_false_alarms():
    scores = list(range(200))                  # 200 correct sounds scored 0..199
    t = pick_threshold(scores, cap=0.005)      # at most 1 of 200 may be above t
    assert t == 198
    assert pick_threshold([0.1, 0.2], cap=0.005) == 0.2   # tiny n: nothing may be flagged


def row(speaker, human, margin, group="others", source="saa", **x):
    r = {"speaker": speaker, "human": human, "margin": margin, "heard_agrees": margin > 0, "group": group,
         "source": source, "baseline_flag": margin > 0, "utt": "u", "pair": "th_as_s", "op": "match",
         "f3_dip": None, "fric": None, "closure": None}
    r.update(x)
    return r


def rows(signal=3.0, seed=0):
    """40 tuning speakers x 50 correct + 1 error each; 4 Korean test speakers. The x_hiss feature separates them."""
    rng = np.random.default_rng(seed)
    out = []
    for s in range(40):
        out += [row(f"t{s}", "correct", -0.9, x_hiss=float(rng.normal())) for _ in range(50)]
        out.append(row(f"t{s}", "error", -0.9, x_hiss=float(rng.normal() + signal)))
    for s in range(4):
        out += [row(f"k{s}", "correct", -0.9, group="korean", x_hiss=float(rng.normal())) for _ in range(50)]
        out += [row(f"k{s}", "error", -0.9, group="korean", x_hiss=float(rng.normal() + signal))]
    return out


def test_a_useless_feature_stops_at_the_feasibility_bar_without_looking_at_korean():
    res = evaluate_pair(rows(signal=0.0), cap=0.005)
    assert res["feasible"] is False and res["oof_auc"] < 0.7
    assert "test (korean)" not in res and res["enabled"] is False


def test_a_strong_feature_is_tested_on_korean():
    res = evaluate_pair(rows(signal=4.0), cap=0.005)
    assert res["feasible"] is True and res["oof_auc"] > 0.9
    k = res["test (korean)"]
    assert k["caught"]["n"] == 4 and k["false_alarms"]["n"] == 200
    assert res["tuning (others)"]["false_alarms"]["rate"] <= 0.005
    assert res["enabled"] == (k["false_alarms"]["k"] / 200 <= 0.005 and k["precision"] is not None
                              and k["precision"] >= 0.5 and k["caught"]["k"] >= 1)
    assert "margin rule (korean)" in res and "baseline (korean)" in res


def test_korean_rows_never_move_the_model():
    rs = rows(signal=4.0)
    a = evaluate_pair(rs, cap=0.005)
    rs.append(row("k9", "correct", 0.99, group="korean", x_hiss=50.0))
    b = evaluate_pair(rs, cap=0.005)
    assert a["model"] == b["model"] and a["threshold"] == b["threshold"]


def test_saa_features_join_on_speaker_and_sound():
    rs = [{"source": "saa", "speaker": "saa:korean1", "word_index": "2", "phoneme_index": "0", "pair": "th_as_s"},
          {"source": "l2arctic", "speaker": "l2arctic:HJK", "x_hiss": 1.0}]
    feats = {("korean1", 2, 0): {"x_hiss": -3.5}}
    out = attach_saa_features(rs, feats)
    assert out[0]["x_hiss"] == -3.5 and out[1]["x_hiss"] == 1.0


# ---------- the feature runs: cache columns ----------
def test_x_columns_blank_for_missing():
    from eval.detectors import X_COLS, x_columns
    cols = x_columns({"heard_nothing": 1, "dur": -0.5, "f1_z": None, **{k: 0.0 for k in
                      ("f2_z", "f3_z", "voiced", "hiss", "centroid", "closure", "burst", "after_voiced",
                       "no_formants", "no_reference")}})
    assert set(cols) == set(X_COLS) and "x_heard_nothing" not in cols   # op already says it
    assert cols["x_dur"] == -0.5 and cols["x_f1_z"] == ""
    assert x_columns(None) == {c: "" for c in X_COLS}


def test_saa_feature_rows_from_saved_times():
    from eval.saa import saa_feature_rows
    from tests.test_features import SR, sentence
    audio, words = sentence()
    out = saa_feature_rows("korean1", words, audio, SR)
    assert len(out) == sum(len(w["phonemes"]) for w in words)
    r = [r for r in out if (r["word_index"], r["phoneme_index"]) == (0, 3)][0]
    assert r["speaker"] == "korean1" and isinstance(r["x_hiss"], float)
