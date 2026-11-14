"""Pick the "did they say it?" thresholds and report how well they work.

    python -m eval.match_tune      # reads data/cache/match_*.csv (from eval/match_eval.py)

Writes results/match.json (every number, with counts) and backend/match_thresholds.json (what the app uses).

ENGLISH (L2-ARCTIC, real learner readings). Tune on the 20 non-Korean speakers, report on the 4 Korean ones:
  sentence check: at most SENTENCE_CAP of correct readings may be rejected ("couldn't match"); within that,
                  reject as many wrong-sentence texts and noise clips as possible.
  word check:     at most WORD_CAP of spoken words may be called "not heard" (0.2%); within that,
                  catch as many cut-out / swapped words as possible. Enabled only if the cap also holds on the
                  Korean test speakers.
KOREAN (Zeroth, natives only: no labelled learner Korean):
  sentence check: LENIENT on purpose: the gentlest setting that still rejects every silence/noise/beep clip.
                  A beginner who reads badly but honestly must not be told "couldn't match".
  word check:     measured and reported, never enabled.
"""
import csv
import json
from pathlib import Path

import numpy as np

from eval.run import wilson

SENT = Path("data/cache/match_sentences.csv")
WORDS = Path("data/cache/match_words.csv")
RESULTS = Path("results/match.json")
THRESHOLDS = Path("backend/match_thresholds.json")
SENTENCE_CAP = 0.01
WORD_CAP = 0.002  # 0.2% chosen: 0.7% of correct sentences with a false red vs 2.2% at 0.5%
GRID = [round(i * 0.02, 2) for i in range(41)]          # 0.00 .. 0.80
HEARD_GRID = [0.0, 0.1, 0.2, 0.25, 0.34, 0.4, 0.5, 0.6]   # share of a word's sounds heard
MIN_SOUNDS = [1, 2, 3]


# ---------- the rules (same logic as backend/match.py, on plain rows) ----------
def gate_rejects(r, t):
    return r["n_heard"] == 0 or r["heard"] < t["min_heard"] or r["conf"] < t["min_conf"]


def word_flags(r, t):
    return r["n"] >= t["min_sounds"] and r["heard"] <= t["max_heard"] and r["conf"] <= t["max_conf"]


def _arr(rows, keys):
    return {k: np.array([float(r[k]) for r in rows]) for k in keys}


def _gate_mask(a, h, c):
    return (a["n_heard"] == 0) | (a["heard"] < h) | (a["conf"] < c)


# ---------- pickers ----------
def pick_gate(good, bad, cap):
    """Reject as many `bad` as possible while rejecting at most `cap` of `good`.
    Ties: fewer good rejected, then the gentler setting (lower thresholds)."""
    g, b = _arr(good, ("heard", "conf", "n_heard")), _arr(bad, ("heard", "conf", "n_heard"))
    best = None
    for h in GRID:
        for c in GRID:
            fr = int(_gate_mask(g, h, c).sum())
            if fr > cap * len(good):
                continue
            key = (int(_gate_mask(b, h, c).sum()), -fr, -(h + c))
            if best is None or key > best[0]:
                best = (key, {"min_heard": h, "min_conf": c})
    return best[1]


def pick_lenient_gate(noise):
    """The gentlest (lowest) thresholds that still reject every no-speech clip."""
    a = _arr(noise, ("heard", "conf", "n_heard"))
    ok = [(h + c, c, h) for h in GRID for c in GRID if _gate_mask(a, h, c).all()]
    _, c, h = min(ok)
    return {"min_heard": h, "min_conf": c}


def pick_word_rule(said, missing, cap):
    """Flag as many `missing` words as possible while flagging at most `cap` of `said` words.
    Ties: fewer false flags, then the stricter rule (lower thresholds, more sounds required)."""
    s, m = _arr(said, ("n", "heard", "conf")), _arr(missing, ("n", "heard", "conf"))
    best = None
    for k in MIN_SOUNDS:
        for h in HEARD_GRID:
            s_base, m_base = (s["n"] >= k) & (s["heard"] <= h), (m["n"] >= k) & (m["heard"] <= h)
            for c in GRID:
                fa = int((s_base & (s["conf"] <= c)).sum())
                if fa > cap * len(said):
                    continue
                key = (int((m_base & (m["conf"] <= c)).sum()), -fa, -(h + c), k)
                if best is None or key > best[0]:
                    best = (key, {"min_sounds": k, "max_heard": h, "max_conf": c})
    return best[1]


# ---------- reporting ----------
def rate(k, n):
    if n == 0:
        return {"k": k, "n": 0, "rate": None, "ci95": None}
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": [round(lo, 4), round(hi, 4)] if n else None}


def _load(path, numeric):
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        for k in numeric:
            r[k] = float(r[k]) if r.get(k) not in (None, "") else 0.0
    return rows


def gate_report(rows, t):
    out = {}
    for cond in ("orig", "swap", "cut", "other", "noise"):
        rs = [r for r in rows if r["cond"] == cond]
        if rs:
            out[cond] = rate(sum(gate_rejects(r, t) for r in rs), len(rs))
    return out


def word_report(words, sentences, gate_t, rule):
    passed = {(r["speaker"], r["utt"], r["cond"]) for r in sentences if not gate_rejects(r, gate_t)}
    live = [w for w in words if (w["speaker"], w["utt"], w["cond"]) in passed]  # the app only checks words if
    orig = [w for w in live if w["cond"] == "orig"]                              # the sentence passed
    out = {
        "false_not_heard_all_words": rate(sum(word_flags(w, rule) for w in orig), len(orig)),
        "false_not_heard_human_correct": rate(sum(word_flags(w, rule) for w in orig if w["human"] == "correct"),
                                              sum(w["human"] == "correct" for w in orig)),
        "false_not_heard_human_error": rate(sum(word_flags(w, rule) for w in orig if w["human"] == "error"),
                                            sum(w["human"] == "error" for w in orig)),
    }
    for cond in ("cut", "swap"):
        tgt = [w for w in words if w["cond"] == cond and w["is_target"] == 1]
        out[f"caught_{cond}"] = rate(sum(word_flags(w, rule) and (w["speaker"], w["utt"], cond) in passed
                                         for w in tgt), len(tgt))
    near = [w for w in live if w["cond"] == "cut" and w["is_target"] == 0 and w["dist"] == 1]
    far = [w for w in live if w["cond"] == "cut" and w["is_target"] == 0 and w["dist"] >= 2]
    out["cut_neighbour_flagged"] = rate(sum(word_flags(w, rule) for w in near), len(near))
    out["cut_far_word_flagged"] = rate(sum(word_flags(w, rule) for w in far), len(far))
    by_sentence = {}
    for w in orig:
        by_sentence.setdefault((w["speaker"], w["utt"]), []).append(word_flags(w, rule))
    out["sentences_with_a_false_not_heard"] = rate(sum(any(v) for v in by_sentence.values()), len(by_sentence))
    return out


def main():
    S = _load(SENT, ("n", "heard", "conf", "n_heard"))
    W = _load(WORDS, ("n", "heard", "conf", "is_target", "dist"))
    for w in W:
        w["dist"] = int(w["dist"]) if w["dist"] != "" else -1
    results, thresholds = {"caps": {"sentence": SENTENCE_CAP, "word": WORD_CAP}}, {}

    # ----- English -----
    en = [r for r in S if r["lang"] == "en"]
    tune = [r for r in en if r["group"] == "others"]
    test = [r for r in en if r["group"] == "korean"]
    noise = [r for r in en if r["cond"] == "noise"]
    gate = pick_gate([r for r in tune if r["cond"] == "orig"],
                     [r for r in tune if r["cond"] == "other"] + noise, SENTENCE_CAP)
    en_w = [w for w in W if w["lang"] == "en"]
    w_tune = [w for w in en_w if w["group"] == "others"]
    rule = pick_word_rule([w for w in w_tune if w["cond"] == "orig"],
                          [w for w in w_tune if w["cond"] in ("cut", "swap") and w["is_target"] == 1], WORD_CAP)
    w_test_rep = word_report([w for w in en_w if w["group"] == "korean"], test, gate, rule)
    word_ok = w_test_rep["false_not_heard_all_words"]["rate"] <= WORD_CAP and w_test_rep["caught_cut"]["k"] > 0
    gate_test = {**gate_report(test, gate), "noise": gate_report(noise, gate)["noise"]}
    gate_ok = gate_test["orig"]["rate"] <= SENTENCE_CAP
    results["en"] = {
        "sentence": {"thresholds": gate, "enabled": gate_ok, "tune": gate_report(tune + noise, gate), "test": gate_test},
        "word": {"thresholds": rule, "enabled": word_ok,
                 "tune": word_report(w_tune, tune, gate, rule), "test": w_test_rep},
    }
    thresholds["en"] = {"sentence": {"enabled": gate_ok, **gate}, "word": {"enabled": word_ok, **rule}}

    # ----- Korean (natives only) -----
    ko = [r for r in S if r["lang"] == "ko"]
    ko_noise = [r for r in ko if r["cond"] == "noise"]
    ko_tune, ko_test = [r for r in ko if r["group"] == "tune"], [r for r in ko if r["group"] == "test"]
    lenient = pick_lenient_gate(ko_noise)
    strict = pick_gate([r for r in ko_tune if r["cond"] == "orig"],
                       [r for r in ko_tune if r["cond"] == "other"] + ko_noise, SENTENCE_CAP)
    ko_w = [w for w in W if w["lang"] == "ko"]
    ko_rule = pick_word_rule([w for w in ko_w if w["group"] == "tune" and w["cond"] == "orig"],
                             [w for w in ko_w if w["group"] == "tune" and w["cond"] in ("cut", "swap")
                              and w["is_target"] == 1], WORD_CAP)
    results["ko"] = {
        "sentence": {"thresholds": lenient, "enabled": True, "why": "lenient: rejects only no-speech (no learner data)",
                     "test": {**gate_report(ko_test, lenient), "noise": gate_report(ko_noise, lenient)["noise"]},
                     "for_comparison_native_tuned": {"thresholds": strict, "test": gate_report(ko_test, strict)}},
        "word": {"thresholds": ko_rule, "enabled": False, "why": "no Korean reds without learner data",
                 "test_natives": word_report([w for w in ko_w if w["group"] == "test"], ko_test, lenient, ko_rule)},
    }
    thresholds["ko"] = {"sentence": {"enabled": True, **lenient}, "word": {"enabled": False, **ko_rule}}
    thresholds["source"] = "eval/match_tune.py (see results/match.json)"

    RESULTS.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n")
    THRESHOLDS.write_text(json.dumps(thresholds, indent=1) + "\n")
    print(json.dumps(results, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
