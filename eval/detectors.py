"""ONE detector pass for the 8 failing pairs (plan, features and pass bar fixed before any run).

    python -m eval.detectors --adopt extra_vowel   # copy a PASSING pair's model + threshold into
                                                   # backend/thresholds.json as variant D (manual, per pair)
    python -m eval.detectors       # seconds; needs the 4 caches of eval/combined.py WITH the x_ feature columns
                                   # (eval.l2arctic / eval.extra_corpora reruns) + data/cache/saa_all_features.csv

Per pair, in this order (each step only sees what the plan allows):
  1. TUNING rows = non-Korean speakers of all 4 corpora (eval/combined.py's roles), correct vs error only.
  2. FEASIBILITY (tuning only): out-of-fold AUC. The tuning speakers are split into 5 groups; the model is trained
     on 4 groups and scores the 5th, round robin, so every score comes from a model that never saw that speaker.
     AUC = the chance a random error scores above a random correct sound. Below 0.70: STOP, the Korean test rows
     are not looked at for this pair.
  3. RULE: one model fit on ALL tuning rows; t = lowest probability with <= 0.5% of tuning correct sounds above it.
  4. TEST on the Korean speakers: the bar (false alarms <= 0.5% exact, >= 50% of reds right, >= 1 caught), next to
     the margin-only rule and the baseline on the SAME rows.
Writes results/detectors.json. Does NOT touch backend/thresholds.json (adoption is manual: --adopt).
"""
import csv
import json
import sys
import zlib
from pathlib import Path

import numpy as np

from backend.detector import FEATURE_NAMES, auc, fit, predict, vectorize
from backend.features import MEASURED
from eval.combined import CACHES, load_all
from eval.run import MIN_PRECISION, cap_for, evaluate_pair as margin_rule, precision, rate

ROOT = Path(__file__).resolve().parents[1]
SAA_FEATURES = ROOT / "data/cache/saa_all_features.csv"
RESULTS = ROOT / "results/detectors.json"
PAIRS = ("l_as_r", "f_as_p", "v_as_b", "th_as_s", "dh_as_d", "ih_as_iy", "iy_as_ih", "extra_vowel")
FEASIBLE_AUC = 0.70
FOLDS = 5
X_COLS = tuple(f"x_{n}" for n in MEASURED if n != "heard_nothing")   # heard_nothing comes from the 'op' column


def x_columns(feats):
    """backend.features output for one sound -> the cache's x_ columns ('' = not measured)."""
    feats = feats or {}
    return {c: "" if feats.get(c[2:]) is None else feats[c[2:]] for c in X_COLS}


def speaker_folds(speakers, k=FOLDS):
    """Fold number per row; all rows of one speaker share a fold. crc32 of the name: the same split every run."""
    return np.array([zlib.crc32(str(s).encode()) % k for s in speakers])


def pick_threshold(scores, cap):
    """Lowest t (one of the scores) with at most `cap` of the scores above it."""
    s = np.sort(np.asarray(scores, dtype=float))
    allowed = int(np.floor(cap * len(s) + 1e-9))
    return float(s[len(s) - 1 - allowed]) if allowed < len(s) else float(s[0])


def slot(r):
    """A row -> the detector's input dict (FEATURE_NAMES, plus slplab's s_ columns when attached)."""
    d = {"margin": r["margin"], "heard_agrees": r["heard_agrees"], "heard_nothing": r.get("op") == "del"}
    d.update({n: r.get(f"x_{n}") for n in MEASURED if n != "heard_nothing"})
    d.update({k: v for k, v in r.items() if k.startswith("s_")})
    return d


def _flags(model, rows, t):
    if not rows:
        return np.zeros(0, dtype=bool)
    return predict(model, vectorize([slot(r) for r in rows], tuple(model["names"]))) > t


def _test(model, t, correct, errors):
    fa, caught = rate(int(_flags(model, correct, t).sum()), len(correct)), rate(int(_flags(model, errors, t).sum()), len(errors))
    p = precision(caught["k"], fa["k"])
    return {"caught": caught, "false_alarms": fa, "precision": None if p is None else round(p, 4)}


def evaluate_pair(rows, cap, names=FEATURE_NAMES):
    tune = [r for r in rows if r["group"] == "others" and r["human"] in ("correct", "error")]
    tc = [r for r in tune if r["human"] == "correct"]
    te = [r for r in tune if r["human"] == "error"]
    res = {"cap": cap, "tuning rows": {"correct": len(tc), "error": len(te)}, "enabled": False,
           "margin_auc": auc([r["margin"] for r in tc], [r["margin"] for r in te])}
    if not tc or not te:
        return {**res, "feasible": False, "oof_auc": None}
    X, y = vectorize([slot(r) for r in tune], names), np.array([r["human"] == "error" for r in tune], dtype=float)
    folds, oof = speaker_folds([r["speaker"] for r in tune]), np.full(len(tune), np.nan)
    for f in range(FOLDS):
        train, held = folds != f, folds == f
        if held.any() and y[train].sum() and (1 - y[train]).sum():
            oof[held] = predict(fit(X[train], y[train], names=names), X[held])
    ok = ~np.isnan(oof)
    res["oof_auc"] = auc(oof[ok & (y == 0)], oof[ok & (y == 1)])
    res["feasible"] = res["oof_auc"] is not None and res["oof_auc"] >= FEASIBLE_AUC
    if not res["feasible"]:
        return res                                   # the plan: stop here, Korean rows not looked at

    model = fit(X, y, names=names)
    t = pick_threshold(predict(model, X[y == 0]), cap)
    kc = [r for r in rows if r["group"] == "korean" and r["human"] == "correct"]
    ke = [r for r in rows if r["group"] == "korean" and r["human"] == "error"]
    k = _test(model, t, kc, ke)
    old = margin_rule(rows, cap)                     # the margin rule on the same rows, for comparison
    res.update(model=model, threshold=t, weights=dict(zip(model["names"], (round(w, 3) for w in model["w"]))),
               **{"tuning (others)": {"caught": rate(int(_flags(model, te, t).sum()), len(te)),
                                      "false_alarms": rate(int(_flags(model, tc, t).sum()), len(tc))},
                  "test (korean)": k,
                  "test by source": {s: _test(model, t, [r for r in kc if r["source"] == s],
                                              [r for r in ke if r["source"] == s])
                                     for s in sorted({r["source"] for r in kc + ke})},
                  "margin rule (korean)": old["test (korean)"], "baseline (korean)": old["baseline (korean)"]})
    n = k["false_alarms"]["n"]
    res["enabled"] = (n > 0 and k["false_alarms"]["k"] / n <= cap and k["precision"] is not None
                      and k["precision"] >= MIN_PRECISION and k["caught"]["k"] >= 1)
    return res


def attach_saa_features(rows, feats):
    """SAA rows get their x_ columns from the sidecar file, keyed (speaker, word_index, phoneme_index)."""
    for r in rows:
        if r.get("source") == "saa":
            r.update(feats.get((r["speaker"].split(":", 1)[1], int(r["word_index"]), int(r["phoneme_index"])), {}))
    return rows


def load_saa_features(path=SAA_FEATURES):
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        out[(r["speaker"], int(r["word_index"]), int(r["phoneme_index"]))] = {c: r[c] for c in X_COLS}
    return out


def adopt(pair, results=None, path=None):
    """Copy one pair's tuned detector from results/detectors.json into backend/thresholds.json (variant D).
    Refuses a pair that didn't pass the bar on the Korean test speakers. Every other pair is left as it is."""
    from backend.scoring import THRESHOLDS_FILE
    path = Path(path or THRESHOLDS_FILE)
    results = results or json.loads(RESULTS.read_text())
    r = results["pairs"].get(pair)
    if not r or not r.get("enabled"):
        raise SystemExit(f"{pair} did not pass the bar in {RESULTS.name}: not adopted")
    th = json.loads(path.read_text()) if path.exists() else {"pairs": {}}
    th["pairs"][pair] = {"cap": r.get("cap"), "variant": "D", "model": r["model"], "threshold": r["threshold"],
                         "enabled": True, "source": f"{RESULTS.name} (trained detector, passed the false-alarm cap)"}
    path.write_text(json.dumps(th, indent=2))
    print(f"adopted {pair} (variant D, threshold {r['threshold']:.4f}) into {path.name}")


def main():
    if sys.argv[1:2] == ["--adopt"]:
        return adopt(sys.argv[2])
    rows, missing = load_all(CACHES)
    if missing or not SAA_FEATURES.exists():
        raise SystemExit(f"missing caches {missing} or {SAA_FEATURES.name}: run the detector feature runs first")
    rows = attach_saa_features(rows, load_saa_features())
    used = [r for r in rows if r["pair"] in PAIRS and r["human"] in ("correct", "error")]
    no_x = sum(all(r.get(c) in (None, "") for c in X_COLS) for r in used)
    print(f"{len(used)} correct/error rows; {no_x} without any feature value")
    out = {"plan": "pre-registered detector pass", "features": list(FEATURE_NAMES), "feasible_auc": FEASIBLE_AUC,
           "rows without features": no_x, "pairs": {}}
    for p in PAIRS:
        out["pairs"][p] = evaluate_pair([r for r in rows if r["pair"] == p], cap_for(p))
    RESULTS.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    def pct(x):
        return "—" if x["rate"] is None else f"{x['k']}/{x['n']} ({100 * x['rate']:.1f}%)"

    def prec(x):
        return "—" if x is None else f"{100 * x:.0f}%"

    print("| pair | tuning c/e | margin AUC | model AUC (out of fold) | bar 0.70 | KO caught | KO false alarms | "
          "reds right | bar | margin rule: caught / FA |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for p, r in out["pairs"].items():
        n = r["tuning rows"]
        head = (f"| {p} | {n['correct']}/{n['error']} | {r['margin_auc']:.3f} | "
                f"{'—' if r['oof_auc'] is None else format(r['oof_auc'], '.3f')} | {'pass' if r['feasible'] else 'FAIL'} |")
        if not r["feasible"]:
            print(head + " not looked at | | | | |")
            continue
        k, m = r["test (korean)"], r["margin rule (korean)"]
        print(head + f" {pct(k['caught'])} | {pct(k['false_alarms'])} | {prec(k['precision'])} | "
                     f"{'PASS' if r['enabled'] else 'fail'} | {pct(m['caught'])} / {pct(m['false_alarms'])} |")
    print(f"\nwrote {RESULTS.relative_to(ROOT)} (backend/thresholds.json NOT changed)")


if __name__ == "__main__":
    main()
