"""Eval of the every-sound Korean check (backend/korean_any_sound.py): does it catch ANY Korean sound said as another
sound, or left out, without marking correct speech red?

    python -m eval.korean_any_sound --run --limit 3   # quick check: a few recordings per source
    python -m eval.korean_any_sound --run             # ~1 h on CPU, resumable (same command continues)
    python -m eval.korean_any_sound                   # re-read the cache, print the table -> results/korean_any_sound.json
    python -m eval.korean_any_sound --write           # also write backend/korean_any_sound_thresholds.json

The idea (same as eval/any_sound.py for English): we have native recordings but no native saying every possible
wrong sound, so the mistake is made on the TEXT side. A native's correct 말 scored against the target 멀 is exactly a
learner who said ㅏ where ㅓ was wanted. Changing one symbol of the target (to another of the same kind: vowel for
vowel, consonant for consonant, final stop for final stop) gives real "said X instead of Y" cases with a known
answer; adding a symbol the native never said gives a "sound left out" case. No hand labelling.

Who is used for what (by speaker, never by recording; the same readers as eval/korean_match.py):
    tune    = Zeroth native readers, 16 speakers of a train shard (20 readings each)
    test    = the 10 Zeroth test-split speakers (all 457 readings)
    learners = AI Hub 505, English-L1 learners reading Korean word for word, 6 readings per speaker per rating
              (상 / 중 / 하). AI Hub has no per-sound labels, so a red on a learner may be a REAL mistake: their
              false-red share is an UPPER bound.
The listener (slplab) was trained on another native corpus, not on Zeroth or AI Hub.

The cut-offs: the most lenient (margin, right, sub_right) that keeps the share of correct TUNE readings with any
false red at or under the cap, picking the set that catches the most tune mistakes. Live cap 5% (as for English, eval/any_sound.py).

Pass bars (fixed 2026-11-16 BEFORE the run; checked at the 5% cap):
    test natives: readings with a false red <= 7.5%
    test natives: made-up swaps caught >= 50%
    learners: red readings more common in 중/하 than in 상 (95% interval of the gap, resampling SPEAKERS, above 0)
    the left-out rule stays on only if it catches >= 25% of the test's left-out sounds (else it is switched off)
  -> grade (red) if 상 learner readings with any red <= 20%, else only a soft "check this" hint. A failed natives bar
     or learner bar = off.
Privacy / terms: per-recording rows stay in data/cache/ (git-ignored); results/korean_any_sound.json = counts only.
"""
import argparse
import csv
import json
import random
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from backend.korean_any_sound import SYMBOLS, THRESHOLDS_FILE, VOWEL_TOKS, accepted, dropped_ok, heard_ok, rival, verdict

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
ROWS, DONE, LOG = CACHE / "korean_any_sound.csv", CACHE / "korean_any_sound_done.csv", CACHE / "korean_any_sound.log"
RESULTS = ROOT / "results" / "korean_any_sound.json"
CAPS, LIVE_CAP = (0.02, 0.05, 0.10), 0.05
BARS = {"test_false_red_max": 0.075, "swaps_caught_min": 0.5, "left_out_min": 0.25, "top_false_red_grade": 0.20}
M_GRID = np.round(np.concatenate([np.arange(-1.0, 0.9, 0.02), np.arange(0.9, 1.0001, 0.0025)]), 4)
R_GRID = [0.0, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05]
RS_GRID = [0.0, 0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.005, 0.01]
FINALS = ("k", "p", "t")
FIELDS = ["group", "speaker", "utt", "rating", "cond", "said", "index", "word_index", "target", "right", "others",
          "op", "heard", "prev", "next", "prev_in_word", "alt", "skip"]
GROUPS = ("tune", "test", "learners", "learners_2", "learners_1")     # learners = 상, _2 = 중, _1 = 하


# ---------- 1. the made-up mistakes ----------
def kind(tok):
    return "vowel" if tok in VOWEL_TOKS else "final" if tok in FINALS else "consonant"


def variants(pairs, rng, n_sub, n_del):
    """Changed symbol lists: ("sub", said, target, i) = the audio has `said` at symbol i where the target now wants
    another symbol of the same kind; ("del", None, target, i) = the target gains symbol i the audio never had."""
    out = []
    for i in rng.sample(range(len(pairs)), min(n_sub, len(pairs))):
        said, cover = pairs[i]
        target = rng.choice([s for s in SYMBOLS if s != said and kind(s) == kind(said)])
        new = list(pairs)
        new[i] = (target, cover)
        out.append((new, ("sub", said, target, i)))
    for _ in range(n_del):
        i = rng.randrange(len(pairs) + 1)
        target = rng.choice([s for s in SYMBOLS if kind(s) != "final"])
        new = pairs[:i] + [(target, pairs[min(i, len(pairs) - 1)][1])] + pairs[i:]
        out.append((new, ("del", None, target, i)))
    return out


# ---------- 2. the run ----------
def _csv_row(base, cond, said, r, c):
    return dict(base, cond=cond, said=said or "", index=r["index"], word_index=r["cover"][0][0], target=r["target"],
                right=r["right"], others="|".join(f"{s}:{v}" for s, v in r["others"]), op=r["op"], heard=r["heard"],
                prev=c["prev"], next=c["next"], prev_in_word=c["prev_in_word"], alt="|".join(sorted(c["alt"])),
                skip=int(c["skip"]))


def recording_rows(base, lp, text, edits, n_sub=4, n_del=2):
    from backend.g2p import expected_phonemes
    from backend.korean_any_sound import context, evidence, pair_context
    from backend.korean_listener import greedy, to_mfa
    words = expected_phonemes(" ".join(text.split()), "ko")
    pairs, heard = to_mfa(words), greedy(lp)
    ctx = context(words, pairs)
    out = [_csv_row(base, "correct", "", r, c) for r, c in zip(evidence(lp, pairs, heard), ctx)]
    if not edits:
        return out
    rng = random.Random(f"korean_any_sound:{base['utt']}")      # per recording: a resumed run draws the same
    for new, (cond, said, target, i) in variants(pairs, rng, n_sub, n_del):
        try:
            r = evidence(lp, new, heard)[i]
        except (ValueError, AssertionError):
            continue
        c = pair_context(new)[i]
        c["skip"] = ctx[min(i, len(ctx) - 1)]["skip"]
        out.append(_csv_row(base, cond, said, r, c))
    return out


def _done():
    return {r["key"] for r in csv.DictReader(DONE.open(encoding="utf-8"))} if DONE.exists() else set()


def _writer(path, fields):
    new = not path.exists()
    f = path.open("a", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    if new:
        w.writeheader()
    return f, w


def run(limit=None):
    from backend.korean_listener import emissions
    from eval.korean_match import learners, natives
    CACHE.mkdir(parents=True, exist_ok=True)
    done = _done()
    fr, wr = _writer(ROWS, FIELDS)
    fd, wd = _writer(DONE, ["key", "error"])
    t0, n = time.time(), 0
    try:
        # learners one rating at a time: 6 readings per speaker PER RATING (as eval/korean_match.py's runs)
        for source in (natives(limit), *(learners(limit, (r,)) for r in (3, 2, 1))):
            for key, base, load, text, edits, _, _ in source:
                if key in done:
                    continue
                err = ""
                try:
                    audio, sr = load()
                    if audio.ndim > 1:
                        audio = audio.mean(axis=1)
                    base = {k: base[k] for k in ("group", "speaker", "utt", "rating")}
                    wr.writerows(recording_rows(base, emissions(audio, sr), text, edits))
                except (ValueError, AssertionError) as e:     # too short, no Korean sounds, alignment mismatch
                    err = str(e)[:120] or type(e).__name__
                wd.writerow(dict(key=key, error=err))        # written LAST: marks the recording as done
                fr.flush()
                fd.flush()
                n += 1
                if n % 50 == 0:
                    print(f"{time.strftime('%H:%M:%S')} {n} recordings, {(time.time() - t0) / n:.2f} s each", flush=True)
    finally:
        fr.close()
        fd.close()
    print(f"done: {n} recordings in {time.time() - t0:.0f} s", flush=True)


# ---------- 3. the numbers ----------
def load_rows(path=ROWS):
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    for r in rows:
        r["right"] = float(r["right"])
        r["others"] = [(s, float(v)) for s, v in (x.rsplit(":", 1) for x in r["others"].split("|") if x)]
        r["alt"] = set(filter(None, r["alt"].split("|")))
        r["skip"] = r["skip"] == "1"
        r["other"], r["margin"] = rival(r)
    return [r for r in rows if not r["skip"]]


def _t(m, rc, rs):
    return {"enabled": True, "margin": m, "right": rc, "sub_right": rs}


def false_red(rows, t):
    """Share of readings with at least one red, among `rows` (one reading = speaker + utt)."""
    hit = defaultdict(bool)
    for r in rows:
        hit[(r["speaker"], r["utt"])] |= verdict(r, t) is not None
    return sum(hit.values()) / len(hit) if hit else float("nan")


def _sentence_stats(rows):
    """Per reading: [highest margin, weakest right of a dropped symbol, weakest right of a replaced symbol]."""
    d = defaultdict(lambda: [-9.0, 9.0, 9.0])
    for r in rows:
        k = d[(r["speaker"], r["utt"])]
        k[0] = max(k[0], r["margin"])
        if r["op"] == "del" and not dropped_ok(r):
            k[1] = min(k[1], r["right"])
        if r["op"] == "sub" and not accepted(r, r["heard"]):
            k[2] = min(k[2], r["right"])
    return np.array(list(d.values())).reshape(-1, 3)


def _fa(a, m, rc, rs):
    return float(np.mean((a[:, 0] > m) | (a[:, 1] < rc) | (a[:, 2] < rs))) if len(a) else float("nan")


def share(rows, t, named=False):
    """Caught = turned red; named = red AND the symbol named as said is the one the native really said."""
    hits = [(r, verdict(r, t)) for r in rows]
    caught = sum(v is not None for _, v in hits)
    out = {"caught": caught, "n": len(rows), "rate": round(caught / len(rows), 4) if rows else None}
    if named:
        out["said_named_right"] = sum(v is not None and v[1] == r["said"] for r, v in hits)
    return out


def greens(rows, t):
    """How many would show GREEN in the app (no mistake found AND the listener heard the right sound there).
    On made-up swaps a green is a false green: the native said another sound. Measured after the cut was chosen."""
    g = sum(not r.get("skip") and verdict(r, t) is None and heard_ok(r) for r in rows)
    return {"green": g, "n": len(rows), "rate": round(g / len(rows), 4) if rows else None}


def _speaker_gap_ci(readings, n_boot=1000, seed=0):
    """readings = [(speaker, rating, red)]. 95% interval of (red share in 중/하) - (red share in 상), by speaker."""
    by = defaultdict(list)
    for x in readings:
        by[x[0]].append(x)
    groups = list(by.values())

    def gap(rs):
        top = [red for _, rating, red in rs if rating == 3]
        low = [red for _, rating, red in rs if rating < 3]
        return np.mean(low) - np.mean(top) if top and low else None
    if gap(readings) is None:
        return None, None
    rng = np.random.default_rng(seed)
    vals = [v for v in (gap([x for i in rng.integers(0, len(groups), len(groups)) for x in groups[i]])
                        for _ in range(n_boot)) if v is not None]
    return round(float(gap(readings)), 4), (round(float(np.percentile(vals, 2.5)), 4),
                                             round(float(np.percentile(vals, 97.5)), 4))


def decide(m):
    """Measured numbers -> "grade" / "hint" / "off" (BARS, fixed before the run)."""
    ci = m["lower_rated_gap_ci"]
    if m["test_false_red"] > BARS["test_false_red_max"] or m["swaps_caught"] < BARS["swaps_caught_min"] \
            or ci is None or ci[0] <= 0:
        return "off"
    return "grade" if m["top_false_red"] <= BARS["top_false_red_grade"] else "hint"


def _pick(stats, errs, cap, r_grid):
    best = None
    for rc in r_grid:
        for rs in RS_GRID:
            ok = [m for m in M_GRID if _fa(stats, m, rc, rs) <= cap]
            if ok:
                t = _t(float(ok[0]), rc, rs)
                hit = sum(verdict(r, t) is not None for r in errs)
                if best is None or hit > best[0]:
                    best = (hit, t)
    return best and best[1]


def measure(rows, cap):
    correct = {g: [r for r in rows if r["cond"] == "correct" and r["group"] == g] for g in GROUPS}
    subs = {g: [r for r in rows if r["cond"] == "sub" and r["group"] == g and not accepted(r, r["said"])]
            for g in ("tune", "test")}
    dels = {g: [r for r in rows if r["cond"] == "del" and r["group"] == g] for g in ("tune", "test")}
    stats = _sentence_stats(correct["tune"])
    t = _pick(stats, subs["tune"] + dels["tune"], cap, R_GRID)
    if t is None:
        return None
    left_out = share(dels["test"], t)
    left_out_on = (left_out["rate"] or 0) >= BARS["left_out_min"]
    if not left_out_on:                                   # the left-out rule is switched off: re-pick without it
        t = _pick(stats, subs["tune"] + dels["tune"], cap, [0.0])
        left_out = share(dels["test"], t)
    readings = defaultdict(bool)
    for g in ("learners", "learners_2", "learners_1"):
        for r in correct[g]:
            readings[(r["speaker"], r["utt"], int(r["rating"]))] |= verdict(r, t) is not None
    gap, ci = _speaker_gap_ci([(s, rating, red) for (s, _, rating), red in readings.items()])
    out = {"thresholds": {k: t[k] for k in ("margin", "right", "sub_right")}, "left_out_rule_on": left_out_on,
           "readings": {g: len({(r["speaker"], r["utt"]) for r in correct[g]}) for g in GROUPS},
           "false_red_readings": {g: round(false_red(correct[g], t), 4) for g in GROUPS},
           "swaps": share(subs["test"], t, named=True),
           **{f"swaps_{k}": share([r for r in subs["test"] if kind(r["target"]) == k], t, named=True)
              for k in ("vowel", "consonant", "final")},
           "left_out": left_out, "lower_rated_gap": gap, "lower_rated_gap_ci": ci,
           "swaps_green": greens(subs["test"], t), "test_sounds_green": greens(correct["test"], t)}
    out["measured"] = {"test_false_red": out["false_red_readings"]["test"], "swaps_caught": out["swaps"]["rate"] or 0,
                       "lower_rated_gap_ci": ci, "top_false_red": out["false_red_readings"]["learners"]}
    out["verdict"] = decide(out["measured"])
    return out


def report(rows):
    done = list(csv.DictReader(DONE.open(encoding="utf-8"))) if DONE.exists() else []
    return {"source": "eval/korean_any_sound.py", "bars": BARS, "live_cap": LIVE_CAP,
            "recordings": {"done": len(done), "failed": sum(bool(d["error"]) for d in done)},
            "warning": "Swaps and left-out sounds are made up on native speech (clean sounds: catches look better than "
                       "on learners). Learner reds include real mistakes: an UPPER bound on false alarms. Counts only.",
            "caps": {f"{c:.2f}": measure(rows, c) for c in CAPS}}


def show(res):
    pct = lambda d: f"{100 * d['caught'] / d['n']:5.1f}% ({d['caught']}/{d['n']})" if d["n"] else "n/a"
    print(f"recordings: {res['recordings']}")
    for cap, c in res["caps"].items():
        if c is None:
            print(f"cap {float(cap):.0%}: no cut-offs meet it")
            continue
        fr = c["false_red_readings"]
        print(f"cap {float(cap):.0%}: {c['thresholds']} (left-out rule {'on' if c['left_out_rule_on'] else 'OFF'})\n"
              f"   readings with a false red: tune {100 * fr['tune']:.1f}%, test {100 * fr['test']:.1f}%, "
              f"상 {100 * fr['learners']:.1f}%, 중 {100 * fr['learners_2']:.1f}%, 하 {100 * fr['learners_1']:.1f}%"
              f" (gap 중/하 - 상 {c['lower_rated_gap']}, 95% {c['lower_rated_gap_ci']})\n"
              f"   swaps caught {pct(c['swaps'])} (vowels {pct(c['swaps_vowel'])}, consonants "
              f"{pct(c['swaps_consonant'])}, finals {pct(c['swaps_final'])}); said named right "
              f"{c['swaps']['said_named_right']}; left out {pct(c['left_out'])}\n   verdict: {c['verdict']}")


def write(res):
    RESULTS.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    print("wrote", RESULTS.relative_to(ROOT))


def write_thresholds(res):
    from backend.korean_listener import MODEL, REVISION
    live = res["caps"][f"{LIVE_CAP:.2f}"]
    THRESHOLDS_FILE.write_text(json.dumps({
        "source": "eval/korean_any_sound.py (see results/korean_any_sound.json)", "model": MODEL, "revision": REVISION,
        "enabled": live["verdict"] != "off", "mode": live["verdict"], "cap": LIVE_CAP, **live["thresholds"]},
        indent=1) + "\n")
    print("wrote", THRESHOLDS_FILE.relative_to(ROOT))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--write", action="store_true", help="also write backend/korean_any_sound_thresholds.json")
    a = ap.parse_args()
    if a.run:
        run(a.limit)
    res = report(load_rows())
    show(res)
    write(res)
    if a.write:
        write_thresholds(res)
