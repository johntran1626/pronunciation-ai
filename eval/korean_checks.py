"""Which Korean checks may go live? Four pass bars, with the Korean-trained listener.

    python -m eval.korean_checks --smoke       # 5 native + 5 learner recordings -> data/cache/korean_checks_smoke_*
    python -m eval.korean_checks --run         # slow (~1-2 h, CPU), resumable -> data/cache/korean_checks_*.csv
    python -m eval.korean_checks               # seconds: cut + bars -> results/korean_checks.json,
                                               #   backend/korean_thresholds.json

In brief: for each of the ten candidate checks (backend/korean_listener.CHECKS) we
  1. set the CUT on native Korean speakers we tune on (Zeroth, 16 speakers): the lowest cut at which at most
     0.25% of their correct sounds turn red (half of bar 1, as a safety margin), and never below 0 ("confident":
     the model must lean to the mistake);
  2. test it on data it never saw. A check goes live only if ALL FOUR bars hold:
       bar 1  native Korean (10 other Zeroth speakers): correct sounds red <= 0.5%
       bar 2  top-rated (상) AI Hub learner readings: red <= 1%. These readings still contain some real mistakes,
              so this is an UPPER BOUND on false alarms for good learners.
       bar 3  red is more common in 중/하 readings than in 상 ones: the 95% interval of the gap, from resampling
              whole SPEAKERS, is above 0. Shows the check reacts to worse speech.
       bar 4  simulated big errors on the test natives (the same audio, one jamo swapped in the target text,
              eval/korean_sim.py): caught >= 25%, from >= 30 errors and >= 5 speakers.
Bars set 2026-11-14 BEFORE any run. AI Hub has no per-sound labels, so it never gives a detection rate.
Simulated errors are clean native sounds, so bar 4 is optimistic: it can only rule out.

Privacy / terms: per-recording rows stay in data/cache/ (git-ignored). results/korean_checks.json = counts only.
"""
import argparse
import csv
import io
import json
import random
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np

from backend.korean_listener import CHECKS, MODEL, REVISION, fires

ROOT = Path(__file__).resolve().parents[1]
NATIVE_ROWS = ROOT / "data/cache/korean_checks_natives.csv"
LEARNER_ROWS = ROOT / "data/cache/korean_checks_learners.csv"
DONE = ROOT / "data/cache/korean_checks_done.csv"           # one line per finished recording (resume marker)
SMOKE = {"natives": ROOT / "data/cache/korean_checks_smoke_natives.csv",
         "learners": ROOT / "data/cache/korean_checks_smoke_learners.csv",
         "done": ROOT / "data/cache/korean_checks_smoke_done.csv"}
RESULTS = ROOT / "results/korean_checks.json"
THRESHOLDS = ROOT / "backend/korean_thresholds.json"

TUNE_CAP = 0.0025          # cut: at most 0.25% of the tune natives' correct sounds red
BAR1_NATIVE_FA = 0.005     # bar 1
BAR2_TOP_LEARNER = 0.01    # bar 2
BAR4_CAUGHT = 0.25         # bar 4
MIN_ERRORS, MIN_ERROR_SPEAKERS = 30, 5
MIN_TOP_SOUNDS = 200       # bar 2 needs at least this many 상 sounds to say anything
PER_SPEAKER = 40           # AI Hub readings per learner (same as the earlier learner check)
SEED = 17

NATIVE_FIELDS = ["group", "speaker", "utt", "human", "pair", "check", "position", "margin", "heard_said"]
LEARNER_FIELDS = ["split", "speaker", "file", "rating", "check", "position", "margin", "heard_said"]
STOP_TYPE = {j: t for t, js in (("lenis", "ㅂㄷㄱ"), ("tense", "ㅃㄸㄲ"), ("asp", "ㅍㅌㅋ")) for j in js}


def pooled_check(pair):
    """korean_sim pair 'ㅃ_as_ㅍ' -> our check name 'tense_as_asp'; vowel pairs keep their name."""
    target, said = pair.split("_as_")
    return f"{STOP_TYPE[target]}_as_{STOP_TYPE[said]}" if target in STOP_TYPE else pair


# ---------- 1. the cut ----------
def cut_from_natives(rows, cap=TUNE_CAP):
    """Lowest cut at which at most cap x (all correct native sounds) would fire; never below 0."""
    allowed = int(cap * len(rows))
    heard = sorted((float(r["margin"]) for r in rows if int(r["heard_said"]) == 1), reverse=True)
    cut = heard[allowed] if allowed < len(heard) else 0.0
    return max(cut, 0.0)


# ---------- 2. the four bars ----------
def _rate(rows, cut):
    k = sum(fires(r, cut) for r in rows)
    return k, len(rows)


def _gap(rows, cut):
    """Red rate in 중/하 readings minus red rate in 상 readings (None if either is empty)."""
    top = [r for r in rows if int(r["rating"]) == 3]
    low = [r for r in rows if int(r["rating"]) < 3]
    if not top or not low:
        return None
    return sum(fires(r, cut) for r in low) / len(low) - sum(fires(r, cut) for r in top) / len(top)


def _speaker_ci(rows, stat, n_boot=1000, seed=0):
    by = defaultdict(list)
    for r in rows:
        by[r["speaker"]].append(r)
    groups = list(by.values())
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        v = stat([r for i in pick for r in groups[i]])
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    return round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)


def _share(k, n):
    from eval.run import rate
    return rate(k, n)


def bars(natives_test, errors, learners, cut, n_boot=1000):
    """natives_test = correct sounds of test natives; errors = simulated errors on test natives;
    learners = AI Hub rows (rating 3 = 상, 2 = 중, 1 = 하). -> {bar1..bar4: {...,"pass"}, "live"}."""
    k1, n1 = _rate(natives_test, cut)
    bar1 = dict(_share(k1, n1), cap=BAR1_NATIVE_FA, pass_=bool(n1) and k1 / n1 <= BAR1_NATIVE_FA)

    top = [r for r in learners if int(r["rating"]) == 3]
    k2, n2 = _rate(top, cut)
    bar2 = dict(_share(k2, n2), cap=BAR2_TOP_LEARNER,
                pass_=n2 >= MIN_TOP_SOUNDS and k2 / n2 <= BAR2_TOP_LEARNER)

    low = [r for r in learners if int(r["rating"]) < 3]
    k_low, n_low = _rate(low, cut)
    gap = _gap(learners, cut)
    ci = _speaker_ci(learners, lambda rs: _gap(rs, cut), n_boot=n_boot) if gap is not None else None
    bar3 = dict(top=_share(k2, n2), lower_rated=_share(k_low, n_low),
                gap=None if gap is None else round(gap, 4), gap_ci95_by_speaker=ci,
                pass_=ci is not None and ci[0] > 0)

    k4, n4 = _rate(errors, cut)
    spk = len({r["speaker"] for r in errors})
    bar4 = dict(_share(k4, n4), speakers=spk, bar=BAR4_CAUGHT,
                pass_=n4 >= MIN_ERRORS and spk >= MIN_ERROR_SPEAKERS and k4 / n4 >= BAR4_CAUGHT)

    out = {}
    for name, b in (("bar1", bar1), ("bar2", bar2), ("bar3", bar3), ("bar4", bar4)):
        b["pass"] = b.pop("pass_")
        out[name] = b
    out["live"] = all(out[b]["pass"] for b in ("bar1", "bar2", "bar3", "bar4"))
    return out


# ---------- 3. measuring (loads the model) ----------
def _writer(path, fields):
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=fields)
    if new:
        w.writeheader()
    return f, w


def _done(path):
    return {r["key"] for r in csv.DictReader(open(path, encoding="utf-8"))} if path.exists() else set()


def native_rows(group, spk, utt, text, lp, rng):
    """Correct rows (what the native said) + one simulated error per swap pair (eval/korean_sim.py's trick)."""
    from backend.g2p import expected_phonemes
    from backend.korean_listener import measure_lp
    from eval.korean_sim import _sampled_variants
    text = " ".join(text.split())
    orig = expected_phonemes(text, "ko")
    base = dict(group=group, speaker=spk, utt=utt)
    out = [dict(base, human="correct", pair="", **_keep(r)) for r in measure_lp(lp, orig)]
    for v in _sampled_variants(text, orig, rng):
        want = pooled_check(v["pair"])
        try:
            rows = measure_lp(lp, expected_phonemes(v["target_text"], "ko"))
        except ValueError:
            continue
        hit = [r for r in rows if (r["wi"], r["pi"], r["check"]) == (v["word_index"], v["phoneme_index"], want)]
        if hit:
            out.append(dict(base, human="error", pair=v["pair"], **_keep(hit[0])))
    return out


def _keep(r):
    return {k: r[k] for k in ("check", "position", "margin", "heard_said")}


def _natives(limit):
    from itertools import islice
    from eval.korean_sim import recordings
    for group, spk, utt, text, audio, sr in islice(recordings(1 if limit else None), limit):
        yield f"native:{spk}:{utt}", dict(group=group, speaker=spk, utt=utt, text=text), lambda a=audio, s=sr: (a, s)


def _learners(limit):
    import soundfile as sf
    from eval.aihub505 import load_items, per_speaker
    items, _ = load_items()
    items.sort(key=lambda i: (i["speaker"], i["file"]))
    items = per_speaker(items, PER_SPEAKER)
    if limit:
        items = items[:limit]
    zips = {}

    def reader(it):
        z = zips.setdefault(it["audio_zip"], zipfile.ZipFile(it["audio_zip"], metadata_encoding="cp949"))
        return sf.read(io.BytesIO(z.read(it["member"])), dtype="float32")
    for it in items:
        yield f"learner:{it['file']}", it, lambda it=it: reader(it)


def run(paths, limit=None):
    from backend.g2p import expected_phonemes
    from backend.korean_listener import emissions, measure_lp
    done = _done(paths["done"])
    fn, wn = _writer(paths["natives"], NATIVE_FIELDS)
    fl, wl = _writer(paths["learners"], LEARNER_FIELDS)
    fd, wd = _writer(paths["done"], ["key", "error"])
    rng = random.Random(SEED)       # note: a resumed run draws different swaps for the rest (counts stay valid)
    t0, n = time.time(), 0
    try:
        for source in (_natives(limit), _learners(limit)):
            for key, it, load in source:
                if key in done:
                    continue
                err = ""
                try:
                    audio, sr = load()
                    lp = emissions(audio, sr)
                    if key.startswith("native:"):
                        for r in native_rows(it["group"], it["speaker"], it["utt"], it["text"], lp, rng):
                            wn.writerow(r)
                    else:
                        base = {k: it[k] for k in ("split", "speaker", "file", "rating")}
                        for r in measure_lp(lp, expected_phonemes(it["text"], "ko")):
                            wl.writerow(dict(base, **_keep(r)))
                except (ValueError, AssertionError) as e:     # too short, no Korean sounds, alignment mismatch
                    err = str(e)[:120] or type(e).__name__
                wd.writerow(dict(key=key, error=err))        # written LAST: marks the recording as done
                for f in (fn, fl, fd):
                    f.flush()
                n += 1
                if n % 100 == 0:
                    print(f"{time.strftime('%H:%M:%S')} {n} recordings, {(time.time() - t0) / n:.2f} s each",
                          flush=True)
    finally:
        for f in (fn, fl, fd):
            f.close()
    print(f"done: {n} recordings in {time.time() - t0:.0f} s", flush=True)


# ---------- 4. the report ----------
def _read(path):
    return list(csv.DictReader(open(path, encoding="utf-8"))) if Path(path).exists() else []


def report(paths, results=RESULTS, thresholds=THRESHOLDS, n_boot=1000):
    nat, lrn = _read(paths["natives"]), _read(paths["learners"])
    done = _read(paths["done"])
    by_check = {}
    for check in CHECKS:
        rows = [r for r in nat if r["check"] == check]
        tune_ok = [r for r in rows if r["group"] == "tune" and r["human"] == "correct"]
        test_ok = [r for r in rows if r["group"] == "test" and r["human"] == "correct"]
        test_err = [r for r in rows if r["group"] == "test" and r["human"] == "error"]
        learners = [r for r in lrn if r["check"] == check]
        cut = cut_from_natives(tune_ok) if tune_ok else None
        if cut is None:
            by_check[check] = dict(cut=None, tune_correct=0, live=False, note="no tune rows")
            continue
        b = bars(test_ok, test_err, learners, cut, n_boot=n_boot)
        by_check[check] = dict(cut=round(cut, 4), tune_correct=len(tune_ok), **b)
    res = dict(
        source="eval/korean_checks.py", model=MODEL, revision=REVISION,
        warning=("Bar 2 counts every red on top-rated learner readings, real mistakes included, so it is an UPPER "
                 "BOUND on false alarms. Bar 4 uses SIMULATED errors on native speech (optimistic; rule-out "
                 "only). AI Hub has no per-sound labels: no learner detection rate exists. Natives are Zeroth "
                 "(other microphones than AI Hub's phones). Counts only."),
        settings=dict(tune_cap=TUNE_CAP, bar1=BAR1_NATIVE_FA, bar2=BAR2_TOP_LEARNER, bar4=BAR4_CAUGHT,
                      min_errors=MIN_ERRORS, min_error_speakers=MIN_ERROR_SPEAKERS, min_top_sounds=MIN_TOP_SOUNDS,
                      per_speaker=PER_SPEAKER),
        recordings=dict(done=len(done), failed=sum(1 for r in done if r["error"]),
                        natives=len({(r["speaker"], r["utt"]) for r in nat}),
                        learners=len({r["file"] for r in lrn}), learner_speakers=len({r["speaker"] for r in lrn})),
        checks=by_check, live=sorted(c for c, v in by_check.items() if v.get("live")))
    results.parent.mkdir(parents=True, exist_ok=True)
    results.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    thresholds.write_text(json.dumps(
        {"source": "eval/korean_checks.py (see results/korean_checks.json)", "model": MODEL, "revision": REVISION,
         "checks": {c: dict(enabled=bool(v.get("live")), cut=v.get("cut")) for c, v in by_check.items()}},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    pct = lambda d: "-" if not d or d.get("rate") is None else f"{d['k']}/{d['n']} ({d['rate']:.2%})"
    print("| check | cut | bar1 natives red | bar2 상 red | bar3 gap [95%] | bar4 caught | live |")
    print("|---|---|---|---|---|---|---|")
    for c, v in by_check.items():
        if v.get("cut") is None:
            print(f"| {c} | - | - | - | - | - | no |")
            continue
        g = v["bar3"]
        print(f"| {c} | {v['cut']} | {pct(v['bar1'])} {'ok' if v['bar1']['pass'] else 'X'} "
              f"| {pct(v['bar2'])} {'ok' if v['bar2']['pass'] else 'X'} "
              f"| {g['gap']} {g['gap_ci95_by_speaker']} {'ok' if g['pass'] else 'X'} "
              f"| {pct(v['bar4'])} {'ok' if v['bar4']['pass'] else 'X'} | {'YES' if v['live'] else 'no'} |")
    print(f"live: {res['live']}  ->  {results}, {thresholds}")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="measure every recording (slow, resumable)")
    ap.add_argument("--smoke", action="store_true", help="5 native + 5 learner recordings, smoke files only")
    args = ap.parse_args(argv)
    if args.smoke:
        for p in SMOKE.values():
            p.unlink(missing_ok=True)
        run(SMOKE, limit=5)
        tmp = ROOT / "data/cache"
        report(SMOKE, results=tmp / "korean_checks_smoke.json", thresholds=tmp / "korean_thresholds_smoke.json",
               n_boot=50)
        return
    paths = dict(natives=NATIVE_ROWS, learners=LEARNER_ROWS, done=DONE)
    if args.run:
        run(paths)
    report(paths)


if __name__ == "__main__":
    sys.exit(main())
