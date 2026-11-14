"""ONE report over every labelled English set: tune on non-Korean speakers, test on Korean speakers.

    python -m eval.combined        # seconds; needs the 4 caches below (each made by its own slow run)

In brief: each corpus alone has too few Korean errors to decide anything (L2-ARCTIC: 14 R->L errors). So we
pool them. The rule for every row is the same as eval/run.py, just with more rows:
  - TUNE (set each pair's threshold) on speakers whose first language is NOT Korean, from all 4 corpora.
  - TEST on the Korean speakers (L2-ARCTIC sentences, the same 4 speakers' suitcase stories, SAA's Korean readers).
  - The bar: a pair could go live only if, on the Korean test speakers, false alarms <= its cap (0.5%) AND at
    least half of its reds are real errors.

Who goes where (role()):
  l2arctic     others -> tune, korean -> test
  suitcase     suitcase_others -> tune, suitcase_korean -> test (the SAME 4 Korean speakers as L2-ARCTIC, new speech)
  speechocean  so_adult -> tune; so_child -> left out (children's voices; our users are adults)
  saa          others (every other first language, native English too) -> tune, korean -> test
Only "correct" and "error" rows count. speechocean's "wrong_any" (experts say wrong, not HOW) is never a pair error:
a wrong R there might be a dropped R, not R said as L. Same for "other", "tap", "deleted", "accented".

This does NOT change the app. backend/thresholds.json stays as eval/run.py wrote it. The report also scores those
CURRENT app thresholds on the new, bigger Korean test set ("current app (korean)"), which is the honest check of
what's live today. Adopting the pooled thresholds is a separate, manual decision.
Writes results/combined.json.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

from eval.run import FEATURES_NUMERIC, cap_for, evaluate_pair, flag_t, precision, rate, sentence_level

ROOT = Path(__file__).resolve().parents[1]
CACHES = {"l2arctic": ROOT / "data/cache/eval_l2arctic.csv",
          "suitcase": ROOT / "data/cache/eval_suitcase.csv",
          "speechocean": ROOT / "data/cache/eval_speechocean.csv",
          "saa": ROOT / "data/cache/eval_saa_all.csv"}
APP_THRESHOLDS = ROOT / "backend/thresholds.json"
RESULTS = ROOT / "results/combined.json"
PAIRS = ("r_as_l", "l_as_r", "f_as_p", "v_as_b", "th_as_s", "dh_as_d", "ih_as_iy", "iy_as_ih", "extra_vowel")
ROLES = {("l2arctic", "others"): "tune", ("l2arctic", "korean"): "test",
         ("suitcase", "suitcase_others"): "tune", ("suitcase", "suitcase_korean"): "test",
         ("speechocean", "so_adult"): "tune",
         ("saa", "others"): "tune", ("saa", "korean"): "test"}
THRESHOLD_KEYS = ("variant", "feature", "margin", "m_lo", "dip")


def role(source, group):
    """-> 'tune', 'test', or None (left out)."""
    return ROLES.get((source, group))


def normalize(r, source):
    """One cache row -> the row shape eval/run.py expects (group = 'others' or 'korean'), or None if left out."""
    who = role(source, r["group"])
    if who is None:
        return None
    out = dict(r)
    out.update(source=source, group="others" if who == "tune" else "korean",
               speaker=f"{source}:{r['speaker']}",   # ids are only unique inside one corpus
               margin=float(r["margin"]), heard_agrees=r["heard_agrees"] == "1",
               baseline_flag=r["baseline_flag"] == "1")
    for f in FEATURES_NUMERIC:
        out[f] = float(r[f]) if r.get(f) not in (None, "") else None
    return out


def load_all(caches=CACHES):
    rows, missing = [], [s for s, p in caches.items() if not p.exists()]
    for source, path in caches.items():
        if path.exists():
            rows += [n for n in (normalize(r, source) for r in csv.DictReader(open(path))) if n is not None]
    return rows, missing


def score(rows, t):
    """Korean test numbers for one fixed threshold dict t."""
    c = [r for r in rows if r["group"] == "korean" and r["human"] == "correct"]
    e = [r for r in rows if r["group"] == "korean" and r["human"] == "error"]
    fa, caught = rate(sum(flag_t(r, t) for r in c), len(c)), rate(sum(flag_t(r, t) for r in e), len(e))
    p = precision(caught["k"], fa["k"])
    return {"caught": caught, "false_alarms": fa, "precision": None if p is None else round(p, 4)}


def evaluate_all(rows, pairs=PAIRS, app_thresholds=None):
    out = {"pairs": {}}
    for p in pairs:
        rs = [r for r in rows if r["pair"] == p]
        if not any(r["group"] == "others" and r["human"] == "correct" for r in rs):
            out["pairs"][p] = None   # nothing to tune on
            continue
        res = evaluate_pair(rs, cap_for(p))                 # tuned on 'others' only (eval/run.py)
        t = {k: res[k] for k in THRESHOLD_KEYS if k in res}
        res["test by source"] = {s: score([r for r in rs if r["source"] == s], t)
                                 for s in sorted({r["source"] for r in rs if r["group"] == "korean"})}
        res["tuning rows by source"] = {s: {h: sum(r["source"] == s and r["human"] == h and r["group"] == "others"
                                                   for r in rs) for h in ("correct", "error")}
                                        for s in sorted({r["source"] for r in rs if r["group"] == "others"})}
        if app_thresholds and p in app_thresholds:          # what's live TODAY, on the bigger test set
            res["current app (korean)"] = {**score(rs, app_thresholds[p]),
                                           "was_enabled": bool(app_thresholds[p].get("enabled"))}
        out["pairs"][p] = res
    # sentence level, per test source (an SAA 'sentence' is the whole ~30 s paragraph, so keep them apart)
    tuned = {p: r for p, r in out["pairs"].items() if r}
    out["recordings with a false red (korean, pooled thresholds where enabled)"] = {
        s: sentence_level([r for r in rows if r["source"] == s and r["pair"] in tuned], tuned)
        for s in sorted({r["source"] for r in rows if r["group"] == "korean"})}
    return out


def main():
    rows, missing = load_all()
    app = json.loads(APP_THRESHOLDS.read_text())["pairs"] if APP_THRESHOLDS.exists() else None
    if app and any(t.get("variant") == "D" for t in app.values()):   # an adopted detector needs SAA's x_ columns
        from eval.detectors import attach_saa_features, load_saa_features
        rows = attach_saa_features(rows, load_saa_features())
    res = evaluate_all(rows, app_thresholds=app)
    res["data"] = {s: str(p.relative_to(ROOT)) for s, p in CACHES.items()}
    res["missing caches"] = missing
    RESULTS.write_text(json.dumps(res, indent=2, ensure_ascii=False))

    def pct(x):
        return "—" if x["rate"] is None else f"{x['k']}/{x['n']} ({100 * x['rate']:.1f}%)"

    def prec(x):
        return "—" if x is None else f"{100 * x:.0f}%"

    if missing:
        print(f"WARNING: missing caches {missing}; numbers below are without them.")
    print("| pair | var | tuning errors | KO caught | KO false alarms | reds right | bar | "
          "baseline caught | baseline FA | current app: caught / FA |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for p, t in res["pairs"].items():
        if t is None:
            print(f"| {p} | no tuning rows |")
            continue
        k, b, cur = t["test (korean)"], t["baseline (korean)"], t.get("current app (korean)")
        now = "—" if not cur else f"{pct(cur['caught'])} / {pct(cur['false_alarms'])}{' (live)' if cur['was_enabled'] else ''}"
        print(f"| {p} | {t['variant']} | {t['tuning (others)']['caught']['n']} | {pct(k['caught'])} | "
              f"{pct(k['false_alarms'])} | {prec(k['precision'])} | {'PASS' if t['enabled'] else 'fail'} | "
              f"{pct(b['caught'])} | {pct(b['false_alarms'])} | {now} |")
    print("\nKorean test, per source (pooled thresholds): caught / false alarms")
    for p, t in res["pairs"].items():
        if t:
            print(f"  {p:12s} " + "   ".join(f"{s}: {pct(v['caught'])} / {pct(v['false_alarms'])}"
                                            for s, v in t["test by source"].items()))
    print(f"\nwrote {RESULTS.relative_to(ROOT)} (backend/thresholds.json NOT changed)")


if __name__ == "__main__":
    main()
