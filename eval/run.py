"""Tune the red/green thresholds on some speakers, test them on speakers never seen, compare to a baseline.

    python -m eval.l2arctic          # first: run the pipeline on L2-ARCTIC (slow, cached)
    python -m eval.run               # then: tune + test + report (seconds)

Method (false alarms first; conservative scoring):
  1. TUNE on the 20 non-Korean speakers: for each pair, the lowest margin at which correct sounds
     are wrongly flagged at most `cap` of the time. Done for variant A (posterior margin) and
     B (margin AND the free recognizer heard the wrong sound); keep whichever catches more errors
     on the tuning speakers (tie -> B, the stricter one).
  2. TEST on the 4 Korean speakers (never used in step 1): errors caught and false alarms, with 95% CIs.
  3. GATE: a pair is enabled in the app only if, on the Korean speakers, (a) its false-alarm rate is also
     <= cap AND (b) at least MIN_PRECISION of its reds were real errors. (b) exists because a rare error
     (extra vowel: 34 in ~3,100 word endings) gives more false reds than true ones even at a 0.2% FA rate.
     (Caveat: this gate looks at the test speakers, so enabled pairs' numbers are slightly optimistic.
     A labelled test set of our own would fix that.)
  Caps: 0.5% per checked sound. PAIR_CAPS can give a pair its own cap; R/L was tried at 1%
  and set back to 0.5% (88% of reds right vs 60%).
  4. BASELINE: flag every target sound the recognizer transcribed differently
     (no margin, no tuning). If we barely beat it, that's the finding.
Writes results/eval.json (everything) and backend/thresholds.json (what the app uses).
"""
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from backend.scoring import EXTRA_VOWEL, PAIRS, THRESHOLDS_FILE

FEATURES = Path("data/cache/eval_l2arctic.csv")
TIMING = Path("data/cache/eval_l2arctic_timing.csv")
RESULTS = Path("results/eval.json")
CAPS = [0.005, 0.01, 0.02]   # the sweep reported for every pair (for comparison)
DEFAULT_CAP = 0.005          # what the APP uses, per checked sound
PAIR_CAPS = {}  # per-pair overrides, e.g. {"r_as_l": 0.01}; R/L was tried at 1%, now 0.5%
MIN_PRECISION = 0.5          # at least half of a pair's reds must be real errors
# pairs that may use variant F, and with which waveform features (low F3 = R-like; little
# frication or a deep closure dip = B-like). Each feature is tried on the TUNING speakers; the best one is kept.
TIE_BREAK = {"l_as_r": ("f3_dip",)}
# v_as_b ("fric", "closure") was tried and FAILED its pre-registered feasibility bar (tuning AUC 0.60 /
# 0.62 < 0.70). Left out on purpose so a weak rule can't pass the test by luck. Code kept (acoustics.py).
FEATURES_NUMERIC = ("f3_dip", "fric", "closure")


def cap_for(pair):
    return PAIR_CAPS.get(pair, DEFAULT_CAP)


# ---------- the math ----------
def precision(caught, false_alarms):
    """Of all the reds, the share that were real errors. This is what a user experiences."""
    reds = caught + false_alarms
    return caught / reds if reds else None


def _flag(r, variant, m):
    return r["margin"] > m and (variant == "A" or r["heard_agrees"])


def count(rows, variant, m):
    """-> (how many rows are flagged, how many rows)."""
    return sum(_flag(r, variant, m) for r in rows), len(rows)


def flag_t(r, t):
    """Flag a row with a full threshold dict (any variant, incl. F = the F3 tie-breaker)."""
    if t["variant"] == "D":  # an adopted trained detector: the row's cached x_ columns, as the app measures
        from backend.detector import predict, vectorize
        from eval.detectors import slot
        return bool(predict(t["model"], vectorize([slot(r)], t["model"]["names"]))[0] > t["threshold"])
    if t["variant"] == "F":
        dip = r.get(t.get("feature", "f3_dip"))
        return r["margin"] > t["margin"] or (r["margin"] > t["m_lo"] and dip is not None and dip < t["dip"])
    return _flag(r, t["variant"], t["margin"])


def pick_f3_rule(correct, errors, cap, feature="f3_dip"):
    """Grid search on the TUNING speakers for variant F: most errors caught with false alarms <= cap;
    ties -> fewer false alarms. m_hi = 'recognizer sure' line, m_lo = start of the borderline band,
    dip = how R-like F3 must be. Grid = EXACT search: a cut only changes which errors are caught when it
    crosses an error's value, so the only cuts worth trying sit just below an error's margin / just above
    an error's dip (plus 'never'). Any other cut catches the same errors with as many or more false alarms.
    (A 25-quantile grid missed variant A's exact margin and did worse than A; fixed 2026-11-12.)"""
    import numpy as np
    m_c, m_e = np.array([r["margin"] for r in correct]), np.array([r["margin"] for r in errors])
    nan = float("nan")
    d_c = np.array([nan if r.get(feature) is None else r[feature] for r in correct])
    d_e = np.array([nan if r.get(feature) is None else r[feature] for r in errors])
    eps = 1e-9
    m_grid = sorted({r["margin"] - eps for r in errors}) + [1.0001]
    d_grid = sorted({r[feature] + eps for r in errors if r.get(feature) is not None}) + [-1e9]
    best = None
    for m_hi in m_grid:
        sure_c, sure_e = m_c > m_hi, m_e > m_hi
        for m_lo in [m for m in m_grid if m <= m_hi]:
            for d in d_grid:
                with np.errstate(invalid="ignore"):
                    fl_c = sure_c | ((m_c > m_lo) & (d_c < d))
                    fl_e = sure_e | ((m_e > m_lo) & (d_e < d))
                fa, caught = int(fl_c.sum()), int(fl_e.sum())
                if len(m_c) and fa / len(m_c) > cap:
                    continue
                key = (caught, -fa, m_hi, m_lo, -d)
                if best is None or key > best[0]:
                    best = (key, dict(variant="F", feature=feature, margin=float(m_hi), m_lo=float(m_lo), dip=float(d),
                                      tune_caught=caught, tune_false_alarms=fa))
    return best[1]


def pick_margin(correct, variant, cap):
    """Lowest margin m such that at most `cap` of the CORRECT sounds are flagged (flag = margin > m)."""
    candidates = [-1.0001] + sorted({r["margin"] for r in correct})
    for m in candidates:
        flagged, n = count(correct, variant, m)
        if n == 0 or flagged / n <= cap:
            return m
    return candidates[-1]


def wilson(k, n, z=1.96):
    """95% confidence interval for a rate k/n (Wilson score interval: honest for small n)."""
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(centre - half, 4), round(centre + half, 4)


def rate(k, n):
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": wilson(k, n)}


# ---------- the report ----------
def load():
    rows = list(csv.DictReader(open(FEATURES)))
    for r in rows:
        r["margin"] = float(r["margin"])
        r["heard_agrees"] = r["heard_agrees"] == "1"
        r["baseline_flag"] = r["baseline_flag"] == "1"
        for f in FEATURES_NUMERIC:
            r[f] = float(r[f]) if r.get(f) not in (None, "") else None
    return rows


def evaluate_pair(rows, cap):
    split = defaultdict(list)
    for r in rows:
        split[(r["group"], r["human"])].append(r)
    tune_c, tune_e = split[("others", "correct")], split[("others", "error")]
    test_c, test_e = split[("korean", "correct")], split[("korean", "error")]

    options = {}
    for variant in ("B", "A"):  # B first, so it wins ties
        m = pick_margin(tune_c, variant, cap)
        options[variant] = dict(margin=m, tune_caught=count(tune_e, variant, m)[0])
    variant = max(options, key=lambda v: options[v]["tune_caught"])
    t = {"variant": variant, "margin": options[variant]["margin"]}
    best = None  # try each waveform tie-breaker for this pair; chosen on TUNING speakers only
    for feature in TIE_BREAK.get(tune_c[0]["pair"], ()) if tune_c else ():
        f = pick_f3_rule(tune_c, tune_e, cap, feature)
        if best is None or (f["tune_caught"], -f["tune_false_alarms"]) > (best["tune_caught"], -best["tune_false_alarms"]):
            best = f
    if best and best["tune_caught"] > options[variant]["tune_caught"]:
        t = {k: best[k] for k in ("variant", "feature", "margin", "m_lo", "dip")}

    def n_flag(rs):
        return sum(flag_t(r, t) for r in rs), len(rs)

    fa = rate(*n_flag(test_c))
    caught = rate(*n_flag(test_e))
    prec = precision(caught["k"], fa["k"])
    return {
        "cap": cap, **t,
        "tuning (others)": {"caught": rate(*n_flag(tune_e)), "false_alarms": rate(*n_flag(tune_c))},
        "test (korean)": {"caught": caught, "false_alarms": fa,
                          "precision": None if prec is None else round(prec, 4)},
        "baseline (korean)": {"caught": rate(sum(r["baseline_flag"] for r in test_e), len(test_e)),
                              "false_alarms": rate(sum(r["baseline_flag"] for r in test_c), len(test_c))},
        # exact k/n, not the 4-decimal rounded rate: 4/793 = 0.504% rounds to 0.0050 and slipped past a 0.5% cap
        "enabled": fa["n"] > 0 and fa["k"] / fa["n"] <= cap and prec is not None and prec >= MIN_PRECISION,
        "excluded (korean)": {"other": len(split[("korean", "other")]), "unlabelled": len(split[("korean", "unlabelled")])},
    }


def sentence_level(rows, per_pair):
    """Share of Korean sentences with at least one FALSE red (and with at least one TRUE red)."""
    by_utt = defaultdict(list)
    for r in rows:
        if r["group"] == "korean":
            by_utt[(r["speaker"], r["utt"])].append(r)
    false_red = true_red = base_false = 0
    for rs in by_utt.values():
        def red(r):
            t = per_pair[r["pair"]]
            return t["enabled"] and flag_t(r, t)
        false_red += any(red(r) for r in rs if r["human"] == "correct")
        true_red += any(red(r) for r in rs if r["human"] == "error")
        base_false += any(r["baseline_flag"] for r in rs if r["human"] == "correct")
    n = len(by_utt)
    return {"sentences": n, "with_a_false_red": rate(false_red, n), "with_a_true_red": rate(true_red, n),
            "baseline_with_a_false_red": rate(base_false, n)}


def thresholds_payload(app, old=None):
    """What backend/thresholds.json gets: this run's margin rules, EXCEPT pairs where a trained detector was
    adopted (variant D, `python -m eval.detectors --adopt <pair>`): those are kept as they are."""
    keep = {p: t for p, t in (old or {}).get("pairs", {}).items() if t.get("variant") == "D"}
    pairs = {p: {k: t[k] for k in ("cap", "variant", "feature", "margin", "m_lo", "dip", "enabled") if k in t}
             for p, t in app.items()}
    return {"source": "eval/run.py on L2-ARCTIC (see results/eval.json, 'app'); variant D = adopted trained "
                      "detector (results/detectors.json)",
            "pairs": {**pairs, **keep}}


def main():
    if not FEATURES.exists():
        raise SystemExit("Run `python -m eval.l2arctic` first.")
    rows = load()
    pairs = list(PAIRS) + [EXTRA_VOWEL]
    rows_of = {p: [r for r in rows if r["pair"] == p] for p in pairs}
    results = {"data": "L2-ARCTIC v5.0: tune on 20 non-Korean speakers, test on HJK HKK YDCK YKWK",
               "sweep": {}}
    for cap in CAPS:  # every pair at the same cap, for comparison
        per_pair = {p: evaluate_pair(rows_of[p], cap) for p in pairs}
        results["sweep"][str(cap)] = {"pairs": per_pair, "sentences (korean)": sentence_level(rows, per_pair)}
    app = {p: evaluate_pair(rows_of[p], cap_for(p)) for p in pairs}  # what the app uses
    results["app"] = {"default_cap": DEFAULT_CAP, "pair_caps": PAIR_CAPS, "min_precision": MIN_PRECISION,
                      "pairs": app, "sentences (korean)": sentence_level(rows, app)}

    secs = sorted(float(r["seconds"]) for r in csv.DictReader(open(TIMING)))
    results["seconds_per_sentence"] = {"n": len(secs), "median": round(statistics.median(secs), 3),
                                       "p95": round(secs[int(0.95 * (len(secs) - 1))], 3)}
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    old = json.loads(THRESHOLDS_FILE.read_text()) if THRESHOLDS_FILE.exists() else None
    THRESHOLDS_FILE.write_text(json.dumps(thresholds_payload(app, old), indent=2))

    def pct(x):
        return "—" if x["rate"] is None else f"{x['k']}/{x['n']} ({100 * x['rate']:.1f}%)"

    def table(title, res):
        print(f"\n## {title}")
        print("| pair | cap | var | caught | false alarms | reds that were right | baseline caught | baseline FA | enabled |")
        print("|---|---|---|---|---|---|---|---|---|")
        for p, t in res["pairs"].items():
            k, b = t["test (korean)"], t["baseline (korean)"]
            prec = "—" if k["precision"] is None else f"{100 * k['precision']:.0f}%"
            print(f"| {p} | {100 * t['cap']:.1f}% | {t['variant']} | {pct(k['caught'])} | {pct(k['false_alarms'])} | "
                  f"{prec} | {pct(b['caught'])} | {pct(b['false_alarms'])} | {'yes' if t['enabled'] else 'no'} |")
        s = res["sentences (korean)"]
        print(f"Korean sentences with a false red: {pct(s['with_a_false_red'])} "
              f"(baseline {pct(s['baseline_with_a_false_red'])}); with a true red: {pct(s['with_a_true_red'])}")

    for cap in CAPS:
        table(f"sweep: every pair at {100 * cap:.1f}%", results["sweep"][str(cap)])
    table(f"APP SETTINGS: {100 * DEFAULT_CAP:.1f}% default, overrides {PAIR_CAPS}, >= 50% of reds right", results["app"])
    print(f"\nseconds per sentence: median {results['seconds_per_sentence']['median']}, "
          f"p95 {results['seconds_per_sentence']['p95']} (n={len(secs)})")
    print(f"wrote {RESULTS} and {THRESHOLDS_FILE}")


if __name__ == "__main__":
    main()
