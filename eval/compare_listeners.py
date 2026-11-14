"""OLD vs NEW (fine-tuned) listener. Same detectors, same pass bar, same Korean test sounds.

    python -m eval.compare_listeners --build    # waits for the fine-tune to finish, then runs the 5 cache builds
                                                # with the new listener (held-out speakers only), then the report
    python -m eval.compare_listeners            # the report alone (seconds), once the new caches exist

In brief: it's a rematch with the rules fixed in advance. Both listeners go through the exact same pipeline
(align -> recognize -> margin + detector features -> detectors). For a fair fight:
  1. TUNING uses DEV speakers only, for BOTH listeners. The new listener trained on the other speakers, so tuning on
     them would be like grading a student on the homework they already saw. The old listener gets the same dev-only
     tuning, so any difference comes from the listener, not from different tuning data.
  2. TEST = the Korean speakers (never in training, never in tuning), and only the sounds BOTH listeners scored
     (common_rows), so neither gets an easier set.
  3. The bar, as before: false alarms <= the pair's cap (0.5%), >= 50% of reds right, >= 1 real error caught.
Per pair, two rules are tried: the margin rule (eval/run.py) and the detector (eval/detectors.py, which
first needs out-of-fold AUC >= 0.70 on tuning speakers before the Korean rows are even looked at).

Writes results/listeners.json. Changes NOTHING in the app (backend/thresholds.json, the live listener): switching
the live app to the new listener is a manual decision, after this report.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from backend.listener import LISTENER_ENV, listener_tag
from eval.combined import CACHES, PAIRS, load_all
from eval.listener import SPEAKERS_ENV, tagged

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "data" / "models" / "listener_v1" / "best"
TRAIN_LOG = ROOT / "data" / "models" / "listener_v1" / "train.log"
BUILD_LOG = ROOT / "data" / "cache" / "listener_v1" / "build.log"
RESULTS = ROOT / "results" / "listeners.json"
SAA_FEATURES = ROOT / "data" / "cache" / "saa_all_features.csv"   # the old listener's; tagged() for the new one
KEY = ("source", "speaker", "utt", "word_index", "phoneme_index", "pair", "target")


def _split_of(source, speaker, korean):
    from eval.ft_data import split_of
    return split_of(source, speaker, korean)


# ---------- 1. fairness ----------
def _split(r, split):
    source, raw = r["speaker"].split(":", 1)   # eval/combined.py stores 'source:speaker'
    return split(source, raw, r["group"] == "korean")


def dev_only(rows, split=_split_of):
    """Korean test rows + tuning rows of DEV speakers. Training speakers of the fine-tune are dropped."""
    return [r for r in rows if r["group"] == "korean" or _split(r, split) == "dev"]


def check_tuning(rows, split=_split_of):
    """Refuse to tune on any speaker the new listener trained on."""
    bad = sorted({r["speaker"] for r in rows if r["group"] == "others" and _split(r, split) == "train"})
    if bad:
        raise ValueError(f"{len(bad)} training speakers in the tuning rows, e.g. {bad[:3]}")


def _key(r):
    return tuple(str(r.get(k)) for k in KEY)


def common_rows(old, new):
    """Only the sounds both listeners scored (a recording can fail to align for one of them).
    -> (old rows, new rows, how many rows each lost)."""
    both = {_key(r) for r in old} & {_key(r) for r in new}
    o, n = [r for r in old if _key(r) in both], [r for r in new if _key(r) in both]
    return o, n, {"old": len(old) - len(o), "new": len(new) - len(n)}


# ---------- 2. the comparison ----------
def _numbers(res):
    """A rule's result without the fitted weights (the report keeps numbers only)."""
    return {k: v for k, v in res.items() if k != "model"}


def _one(rows, pair):
    from eval.detectors import PAIRS as DETECTOR_PAIRS
    from eval.detectors import evaluate_pair as detector
    from eval.run import cap_for
    from eval.run import evaluate_pair as margin_rule
    pr = [r for r in rows if r["pair"] == pair]
    out = {"margin rule": _numbers(margin_rule(pr, cap_for(pair)))}
    if pair in DETECTOR_PAIRS:
        out["detector"] = _numbers(detector(pr, cap_for(pair)))
    out["passes bar"] = any(out[rule].get("enabled") for rule in ("margin rule", "detector") if rule in out)
    return out


def compare(old_rows, new_rows, pairs=PAIRS, split=_split_of):
    old_rows, new_rows = dev_only(old_rows, split), dev_only(new_rows, split)
    check_tuning(old_rows, split)
    check_tuning(new_rows, split)
    old_rows, new_rows, dropped = common_rows(old_rows, new_rows)

    def count(rows, group):
        return sum(r["group"] == group and r["human"] in ("correct", "error") for r in rows)

    out = {"rule": "false-alarm cap per pair, >= 50% of reds right, >= 1 caught; tuning = dev speakers only, both listeners",
           "rows": {"tuning (dev)": {"old": count(old_rows, "others"), "new": count(new_rows, "others")},
                    "korean test": {"old": count(old_rows, "korean"), "new": count(new_rows, "korean")},
                    "dropped (not scored by both)": dropped},
           "pairs": {}}
    for p in pairs:
        out["pairs"][p] = {"old": _one(old_rows, p), "new": _one(new_rows, p)}
    out["passing"] = {who: [p for p in pairs if out["pairs"][p][who]["passes bar"]] for who in ("old", "new")}
    return out


# ---------- 3. loading ----------
def load(tag):
    """All 4 caches + SAA's feature sidecar for one listener ('' = old)."""
    from eval.detectors import attach_saa_features, load_saa_features
    rows, missing = load_all({s: tagged(p, tag) for s, p in CACHES.items()})
    feats = tagged(SAA_FEATURES, tag)
    if not feats.exists():
        missing.append(str(feats.relative_to(ROOT)))
    if missing:
        raise SystemExit(f"listener '{tag or 'old'}': missing {missing}; run `python -m eval.compare_listeners --build`")
    return attach_saa_features(rows, load_saa_features(feats))


# ---------- 4. the overnight run ----------
def training_done(log=TRAIN_LOG):
    """eval/finetune.py writes 'HH:MM:SS done: ...' as its very last line."""
    return Path(log).exists() and any(" done: " in line for line in open(log, encoding="utf-8"))


def build_commands(listener=NEW):
    py = sys.executable
    cmds = [[py, "-m", "eval.l2arctic"],
            [py, "-m", "eval.extra_corpora", "suitcase"],
            [py, "-m", "eval.extra_corpora", "speechocean"],
            [py, "-m", "eval.saa", "--set", "all", "--run"],
            [py, "-m", "eval.saa", "--set", "all", "--features"]]
    env = {**os.environ, LISTENER_ENV: str(listener), SPEAKERS_ENV: "heldout"}
    return cmds, env


def build(listener=NEW, poll=60):
    BUILD_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(BUILD_LOG, "a", encoding="utf-8") as log:
        def say(s):
            line = f"{time.strftime('%H:%M:%S')} {s}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

        if not training_done():
            say(f"waiting for the fine-tune to finish ({TRAIN_LOG.name} has no 'done' line yet)")
            while not training_done():
                time.sleep(poll)
        say("fine-tune done; building the new listener's caches (held-out speakers only)")
        cmds, env = build_commands(listener)
        for c in cmds:
            t0 = time.time()
            say("run: " + " ".join(c[2:]))
            r = subprocess.run(c, env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            if r.returncode:
                say(f"FAILED ({r.returncode}) after {time.time() - t0:.0f} s: " + " ".join(c[2:]))
                raise SystemExit(r.returncode)
            say(f"ok in {time.time() - t0:.0f} s")
        say("caches built; writing the report")


# ---------- 5. the report ----------
def _pct(x):
    return "—" if not x or x.get("rate") is None else f"{x['k']}/{x['n']} ({100 * x['rate']:.1f}%)"


def _cell(one):
    best = None
    for rule in ("detector", "margin rule"):
        res = one.get(rule)
        if res and res.get("test (korean)") and (best is None or res.get("enabled")):
            best = (rule, res)
    if best is None:
        return "not looked at (AUC < 0.70)"
    rule, res = best
    k = res["test (korean)"]
    p = "—" if k.get("precision") is None else f"{100 * k['precision']:.0f}%"
    return f"{'PASS' if one['passes bar'] else 'fail'} · {rule}: caught {_pct(k['caught'])}, FA {_pct(k['false_alarms'])}, reds right {p}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="wait for the fine-tune, build the new caches, then report")
    a = ap.parse_args()
    if a.build:
        build()
    tag = listener_tag(str(NEW))
    out = compare(load(""), load(tag))
    out["listeners"] = {"old": "facebook/wav2vec2-xlsr-53-espeak-cv-ft", "new": str(NEW.relative_to(ROOT))}
    RESULTS.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    rows = out["rows"]
    print(f"tuning rows (dev speakers): old {rows['tuning (dev)']['old']}, new {rows['tuning (dev)']['new']}; "
          f"Korean test rows: {rows['korean test']['new']}; dropped (not scored by both): "
          f"{rows['dropped (not scored by both)']}")
    print("| pair | old listener | new listener |\n|---|---|---|")
    for p, r in out["pairs"].items():
        print(f"| {p} | {_cell(r['old'])} | {_cell(r['new'])} |")
    print(f"\npassing the bar: old {out['passing']['old']}, new {out['passing']['new']}")
    print(f"wrote {RESULTS.relative_to(ROOT)} (the app is NOT changed)")


if __name__ == "__main__":
    main()
