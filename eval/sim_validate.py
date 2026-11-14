"""Is a SIMULATED error set a fair stand-in for real learner errors? Checked in English, where we have both.
Plan and pass bars fixed before the run.

    python -m eval.sim_validate             # CMU ARCTIC natives on the Korean speakers' prompts (~10-15 min)
    python -m eval.sim_validate --limit 5   # quick check: 5 prompts

In brief: for Korean we can only test on fake errors (native audio + a swapped target). Before we
trust that, we build the SAME kind of fake set in English and compare it with the REAL English learner
results we already have (L2-ARCTIC Korean speakers, results/eval.json). If real detection is never clearly
higher than simulated detection, the simulated set is a safe "upper bound": a check that fails it would
also fail on real learners, so it can be ruled out without learner data.

  1. Natives: CMU ARCTIC bdl rms slt clb reading the prompts annotated for HJK HKK YDCK YKWK.
  2. Correct rows: every checkable sound in the real sentence (scoring.candidates), as in eval/l2arctic.py.
  3. Error rows: for each pair, take one place where the native said the WRONG sound (SAID; e.g. l for
     r_as_l), set the target there to the RIGHT sound (ɹ), re-align on the same model output, and score it.
  4. Flag with the app's tuned margin and variant per pair (backend/thresholds.json), even for pairs that
     are switched off, so the comparison is like for like.
"""
import argparse
import copy
import csv
import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path

import soundfile as sf

from backend.align import align, emissions
from backend.compare import attach_heard
from backend.g2p import expected_phonemes
from backend.recognize import recognize
from backend.scoring import PAIRS, candidates, load_thresholds
from eval.l2arctic import DATA as L2, KOREAN
from eval.run import RESULTS as REAL_RESULTS, _flag, rate, wilson

CMU = Path("data/cmu_arctic")
CMU_SPEAKERS = ["bdl", "rms", "slt", "clb"]
OUT = Path("data/cache/sim_validate.csv")
RESULTS = Path("results/sim_validate.json")
SEED = 17
SAID = {name: p["produced"] for name, p in PAIRS.items()}  # what a learner says instead (r_as_l -> l)


# ---------- building the simulated errors ----------
def error_positions(words, pair):
    """Every (word, phoneme) where the native said SAID[pair], i.e. a place we can turn into this error."""
    return [(wi, pi) for wi, w in enumerate(words) for pi, p in enumerate(w["phonemes"]) if p == SAID[pair]]


def swap_target(words, wi, pi, ipa):
    """A copy of the expected phonemes with ONE target changed (the audio is never touched)."""
    new = copy.deepcopy(words)
    new[wi]["phonemes"][pi] = ipa
    return new


# ---------- the comparison math ----------
def _ranks(xs):
    """Average ranks, 1-based (ties share the mean of their positions)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs, ys):
    """Rank correlation: +1 = same order, -1 = reversed. Pearson's r on the ranks."""
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    var = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return round(cov / var, 4) if var else None


def upper_bound_ok(sim_rate, real_k, real_n):
    """P1: real detection is NOT significantly above simulated (real's 95% lower bound <= simulated)."""
    if not real_n:
        return None
    return wilson(real_k, real_n)[0] <= sim_rate


# ---------- running it ----------
def prompts(limit):
    """The prompts annotated for the 4 Korean L2-ARCTIC speakers (union), with their text."""
    out = {}
    for spk in KOREAN:
        for g in sorted((L2 / spk / "annotation").glob("*.TextGrid")):
            out.setdefault(g.stem, (L2 / spk / "transcript" / f"{g.stem}.txt").read_text().strip())
    return sorted(out.items())[:limit] if limit else sorted(out.items())


def _row(spk, utt, pair, human, cand, p):
    return dict(speaker=spk, utt=utt, pair=pair, human=human, margin=cand["margin"],
                heard_agrees=int(cand["heard_agrees"]), baseline_flag=int(p["op"] != "match"))


def run_one(spk, utt, text, rng):
    audio, sr = sf.read(CMU / f"cmu_us_{spk}_arctic" / "wav" / f"{utt}.wav", dtype="float32")
    em = emissions(audio, sr)
    heard = recognize(em)
    expected = expected_phonemes(text, "en")
    words, _ = attach_heard(align(em, expected, "en"), heard, "en")
    rows = []
    for c in candidates(em, words, "en"):
        if c["pair"] in PAIRS:
            rows.append(_row(spk, utt, c["pair"], "correct", c, words[c["word_index"]]["phonemes"][c["phoneme_index"]]))
    for pair in PAIRS:
        spots = error_positions(expected, pair)
        if not spots:
            continue
        wi, pi = rng.choice(spots)
        vwords, _ = attach_heard(align(em, swap_target(expected, wi, pi, PAIRS[pair]["target"]), "en"), heard, "en")
        c = next(c for c in candidates(em, vwords, "en")
                 if (c["word_index"], c["phoneme_index"], c["pair"]) == (wi, pi, pair))
        rows.append(_row(spk, utt, pair, "error", c, vwords[wi]["phonemes"][pi]))
    return rows


def compare(rows, thresholds, real):
    """Per pair: simulated (natives) vs real (Korean speakers) detection and false alarms."""
    by = defaultdict(list)
    for r in rows:
        by[(r["pair"], r["human"])].append(r)
    out = {}
    for pair in PAIRS:
        t = thresholds["pairs"][pair]
        err, ok = by[(pair, "error")], by[(pair, "correct")]
        flag = lambda r: _flag(r, t["variant"], t["margin"])
        sim_det = rate(sum(map(flag, err)), len(err))
        sim_fa = rate(sum(map(flag, ok)), len(ok))
        sim_bdet = rate(sum(r["baseline_flag"] for r in err), len(err))
        sim_bfa = rate(sum(r["baseline_flag"] for r in ok), len(ok))
        rp = real["pairs"][pair]
        r_det, r_fa = rp["test (korean)"]["caught"], rp["test (korean)"]["false_alarms"]
        r_bdet, r_bfa = rp["baseline (korean)"]["caught"], rp["baseline (korean)"]["false_alarms"]
        out[pair] = dict(
            variant=t["variant"], margin=t["margin"], enabled_in_app=t["enabled"],
            simulated=dict(detection=sim_det, false_alarms=sim_fa, baseline_detection=sim_bdet, baseline_false_alarms=sim_bfa),
            real=dict(detection=r_det, false_alarms=r_fa, baseline_detection=r_bdet, baseline_false_alarms=r_bfa),
            p1_upper_bound_ok=upper_bound_ok(sim_det["rate"] or 0.0, r_det["k"], r_det["n"]),
            p1_baseline_upper_bound_ok=upper_bound_ok(sim_bdet["rate"] or 0.0, r_bdet["k"], r_bdet["n"]),
            p3_native_fa_le_real=None if sim_fa["rate"] is None or r_fa["rate"] is None else sim_fa["rate"] <= r_fa["rate"],
        )
    return out


def verdict(per_pair):
    p1 = [v["p1_upper_bound_ok"] for v in per_pair.values() if v["p1_upper_bound_ok"] is not None]
    sim = [v["simulated"]["detection"]["rate"] or 0.0 for v in per_pair.values()]
    real = [v["real"]["detection"]["rate"] or 0.0 for v in per_pair.values()]
    rho = spearman(sim, real)
    return dict(
        p1_pairs_ok=sum(p1), p1_pairs=len(p1), p1_pass=sum(p1) >= 7 and len(p1) == 8,
        p2_spearman=rho, p2_useful_for_ranking=rho is not None and rho >= 0.5,
        p3_pairs_native_fa_le_real=sum(bool(v["p3_native_fa_le_real"]) for v in per_pair.values()),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="prompts (quick check)")
    args = ap.parse_args()
    rng = random.Random(SEED)
    rows, n, t0 = [], 0, time.time()
    for utt, text in prompts(args.limit):
        for spk in CMU_SPEAKERS:
            if not (CMU / f"cmu_us_{spk}_arctic" / "wav" / f"{utt}.wav").exists():
                continue
            try:
                rows += run_one(spk, utt, text, rng)
            except ValueError as e:
                print(f"skip {spk}/{utt}: {e}")
                continue
            n += 1
            if n % 200 == 0:
                print(f"{n} recordings, {time.time() - t0:.0f} s", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    per_pair = compare(rows, load_thresholds(), json.loads(REAL_RESULTS.read_text())["app"])
    report = dict(source="eval/sim_validate.py : simulated errors on CMU ARCTIC natives vs REAL "
                         "L2-ARCTIC Korean-speaker errors (results/eval.json, app)",
                  recordings=n, limit=args.limit, seed=SEED, verdict=verdict(per_pair), pairs=per_pair)
    RESULTS.write_text(json.dumps(report, ensure_ascii=False, indent=1))

    def pct(x):
        return "—" if x["rate"] is None else f"{x['k']}/{x['n']} ({100 * x['rate']:.0f}%)"

    print(f"done: {n} recordings, {len(rows)} rows in {time.time() - t0:.0f} s -> {OUT}, {RESULTS}")
    print("| pair | sim caught | real caught | P1 | sim FA | real FA | sim baseline caught | real baseline caught |")
    print("|---|---|---|---|---|---|---|---|")
    for p, v in per_pair.items():
        s, r = v["simulated"], v["real"]
        print(f"| {p} | {pct(s['detection'])} | {pct(r['detection'])} | {v['p1_upper_bound_ok']} | "
              f"{pct(s['false_alarms'])} | {pct(r['false_alarms'])} | {pct(s['baseline_detection'])} | {pct(r['baseline_detection'])} |")
    print(json.dumps(report["verdict"]))


if __name__ == "__main__":
    main()
