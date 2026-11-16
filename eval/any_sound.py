"""Eval of the every-sound English check (backend/any_sound.py): does it catch ANY English sound said as another
sound, or left out, without marking correct speech red?

    python -m eval.any_sound --limit 1132    # all CMU ARCTIC sentences of 4 voices + 150 per Korean voice (~30 min)
    python -m eval.any_sound                 # re-read data/cache/any_sound.csv and print the table
    python -m eval.any_sound --write         # also write backend/any_sound_thresholds.json + results/any_sound.json

The idea in plain words: we have thousands of CORRECT recordings, but no recordings of a native speaker saying
every possible wrong sound. So we make the mistake on the TEXT side instead. A correct recording of "testing"
scored against the target "tasting" is exactly a learner who said [ɛ] where [eɪ] was wanted. Changing one sound of
the target per try gives thousands of real "said X instead of Y" cases with a known answer, from real voices,
with no hand labelling. Adding a sound to the target that the speaker never said gives a "sound left out" case.

Who is used for what (by speaker, never by recording):
    tune = CMU ARCTIC bdl (male) + slt (female);  test = rms (male) + clb (female);
    korean = L2-ARCTIC HJK HKK YDCK YKWK, only sounds the human annotators marked CORRECT (false alarms on learners).
None of these voices were in the listener's fine-tune data (eval/ft_data.py).

The cut-offs: the most lenient pair (margin, right) that keeps the share of correct TUNE sentences with any false
red at or under the cap, picking the pair that catches the most tune errors. The live cap is 5% ("Balanced"),
chosen from the 2% / 5% / 10% table. Tried and dropped: also requiring the free recognizer to agree (caught
fewer swaps at the same cap, and almost no left-out sounds).
"""
import argparse
import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf

from backend.align import align, emissions
from backend.any_sound import CLASSES, NAMES, THRESHOLDS_FILE, VOWELS, accepted, context, dropped_ok, evidence
from backend.compare import attach_heard
from backend.g2p import expected_phonemes
from backend.listener import listener_id, live_listener
from backend.recognize import recognize
from eval.l2arctic import KOREAN, _phones_tier, label_phonemes

ROOT = Path(__file__).resolve().parents[1]
CMU = ROOT / "data" / "cmu_arctic"
L2 = ROOT / "data" / "l2arctic"
OUT = ROOT / "data" / "cache" / "any_sound.csv"
RESULTS = ROOT / "results" / "any_sound.json"
TUNE, TEST = ("bdl", "slt"), ("rms", "clb")
CAPS, LIVE_CAP = (0.02, 0.05, 0.10), 0.05
M_GRID = np.round(np.concatenate([np.arange(-1.0, 0.9, 0.02), np.arange(0.9, 1.0001, 0.0025)]), 4)
R_GRID = [0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05]
RS_GRID = [0.0, 0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.005, 0.01]


# ---------- making the mistakes ----------
def variants(expected, rng, n_sub, n_del):
    """Changed targets: ("sub", said, target, wi, pi) = the audio has `said` where the target now wants another
    sound of the same kind; ("del", None, target, wi, pi) = the target gains a sound the audio never had."""
    out = []
    slots = [(wi, pi) for wi, w in enumerate(expected) for pi, p in enumerate(w["phonemes"]) if p in CLASSES and p != "ə"]
    for wi, pi in rng.sample(slots, min(n_sub, len(slots))):
        said = expected[wi]["phonemes"][pi]
        tgt = rng.choice([c for c in NAMES if c != "ə" and c != said and (c in VOWELS) == (said in VOWELS)])
        new = [dict(w, phonemes=list(w["phonemes"])) for w in expected]
        new[wi]["phonemes"][pi] = tgt
        out.append((new, ("sub", said, tgt, wi, pi)))
    for _ in range(n_del):
        wi = rng.randrange(len(expected))
        pi = rng.randrange(len(expected[wi]["phonemes"]) + 1)
        tgt = rng.choice([c for c in NAMES if c != "ə"])
        new = [dict(w, phonemes=list(w["phonemes"])) for w in expected]
        new[wi]["phonemes"].insert(pi, tgt)
        out.append((new, ("del", None, tgt, wi, pi)))
    return out


def cmu_items(limit):
    for spk in TUNE + TEST:
        lines = (CMU / f"cmu_us_{spk}_arctic" / "etc" / "txt.done.data").read_text().splitlines()
        for line in lines[:limit]:
            m = re.match(r'\(\s*(\S+)\s+"(.*)"\s*\)', line)
            if m:
                yield ("tune" if spk in TUNE else "test"), spk, m[1], m[2], CMU / f"cmu_us_{spk}_arctic" / "wav" / f"{m[1]}.wav", None


def korean_items(limit):
    for spk in KOREAN:
        for g in sorted((L2 / spk / "annotation").glob("*.TextGrid"))[:limit]:
            text = (L2 / spk / "transcript" / f"{g.stem}.txt").read_text().strip()
            yield "korean", spk, g.stem, text, L2 / spk / "wav" / f"{g.stem}.wav", _phones_tier(g.read_text(errors="replace"))


def run(limit, n_sub, n_del, seed=0):
    rng = random.Random(seed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = ["group", "speaker", "utt", "cond", "said", "word_index", "phoneme_index", "target", "right", "other",
              "margin", "op", "heard", "agrees", "human"]
    with OUT.open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=fields)
        wr.writeheader()
        items = list(cmu_items(limit)) + list(korean_items(limit // 2))
        for n, (group, spk, utt, text, wav, human_labels) in enumerate(items, 1):
            try:
                audio, sr = sf.read(wav, dtype="float32")
                expected = expected_phonemes(text, "en")
                em = emissions(audio, sr, "en")        # the live English listener
                heard = recognize(em)
                probs = em.log_probs.exp()
                words, _ = attach_heard(align(em, expected, "en"), heard, "en")
            except ValueError as e:
                print("skip", spk, utt, e)
                continue
            labels = label_phonemes(words, human_labels)[0] if human_labels else None
            offsets = [0]
            for w in words:
                offsets.append(offsets[-1] + len(w["phonemes"]))
            for ev in evidence(probs, em.sec_per_frame, words):
                lab = labels[offsets[ev["word_index"]] + ev["phoneme_index"]] if labels else None
                human = "" if labels is None else ("unlabelled" if lab is None else lab[0])
                wr.writerow(dict(group=group, speaker=spk, utt=utt, cond="correct", said=ev["target"], human=human, **ev))
            if group == "korean":
                continue                                # learners' own errors are counted by the humans' labels
            for new, (cond, said, tgt, wi, pi) in variants(expected, rng, n_sub, n_del):
                try:
                    w2, _ = attach_heard(align(em, new, "en"), heard, "en")
                except ValueError:
                    continue
                for ev in evidence(probs, em.sec_per_frame, w2):
                    if (ev["word_index"], ev["phoneme_index"]) == (wi, pi):
                        wr.writerow(dict(group=group, speaker=spk, utt=utt, cond=cond, said=said or "", human="", **ev))
            if n % 50 == 0:
                print(f"{n}/{len(items)}", flush=True)
                f.flush()


# ---------- the numbers ----------
def flag(r, m, rc, rs=0.0):
    """The live rule (backend/any_sound.verdict) with these cut-offs: m = margin, rc = right for a dropped sound,
    rs = right for a sound the recognizer replaced."""
    if r["skip"]:
        return False
    swapped = (r["margin"] > m or (r["op"] == "sub" and r["right"] < rs)) and not accepted(r)
    return swapped or (r["op"] == "del" and r["right"] < rc and not dropped_ok(r))


def _texts():
    return {(spk, utt): text for _, spk, utt, text, _, _ in list(cmu_items(10 ** 6)) + list(korean_items(10 ** 6))}


def add_context(rows):
    """Each row gains the live word context (backend/any_sound.context) of its sound. A made-up target (sub / del)
    is not a dictionary word: it has no other pronunciations, and an added sound is treated as stressed."""
    texts, cache = _texts(), {}
    for r in rows:
        key = (r["speaker"], r["utt"])
        if key not in cache:
            words = expected_phonemes(texts[key], "en")
            cache[key] = (words, context(words))
        words, ctx = cache[key]
        wi, pi = int(r["word_index"]), int(r["phoneme_index"])
        ph = words[wi]["phonemes"]
        if "-" in words[wi]["word"] or (r["cond"] != "del" and (wi, pi) not in ctx):
            r.update(skip=True)   # made before g2p looked hyphenated words up part by part: positions don't match
            continue
        if r["cond"] == "del":                       # the target gained a sound at pi; the rest shifted right
            base = ctx[(wi, min(pi, len(ph) - 1))]
            prev, nxt = (ph[pi - 1] if pi else ""), (ph[pi] if pi < len(ph) else "")
            c = dict(base, weak=base["func"], next=nxt, alts=set(),
                     between_consonants=bool(prev) and prev not in VOWELS and nxt not in VOWELS)
        else:
            c = dict(ctx[(wi, pi)])
            if r["cond"] == "sub":
                c["alts"] = set()
        r.update(c)


def load_rows():
    rows = list(csv.DictReader(OUT.open()))
    for r in rows:
        r["margin"], r["agrees"], r["right"] = float(r["margin"]), int(r["agrees"]), float(r["right"])
    add_context(rows)
    return rows


def evaluate(rows):
    skipped = sum(r["skip"] for r in rows)
    rows = [r for r in rows if not r["skip"]]
    groups = ("tune", "test", "korean")
    correct = {g: [r for r in rows if r["cond"] == "correct" and r["group"] == g
                   and (g != "korean" or r["human"] == "correct")] for g in groups}
    subs = {g: [r for r in rows if r["cond"] == "sub" and r["group"] == g] for g in ("tune", "test")}
    dels = {g: [r for r in rows if r["cond"] == "del" and r["group"] == g] for g in ("tune", "test")}

    # per sentence: the highest margin that could fire, and the weakest sound the recognizer dropped
    stats = {}
    for g in groups:
        d = defaultdict(lambda: [-9.0, 9.0, 9.0])
        for r in correct[g]:
            k = (r["speaker"], r["utt"])
            if r["op"] == "del" and not dropped_ok(r):
                d[k][1] = min(d[k][1], r["right"])
            if not accepted(r):
                d[k][0] = max(d[k][0], r["margin"])
                if r["op"] == "sub":
                    d[k][2] = min(d[k][2], r["right"])
        stats[g] = np.array(list(d.values())).reshape(-1, 3)

    def fa(g, m, rc, rs):
        a = stats[g]
        return float(np.mean((a[:, 0] > m) | (a[:, 1] < rc) | (a[:, 2] < rs))) if len(a) else float("nan")

    def share(rows_, m, rc, rs):
        return {"caught": sum(flag(r, m, rc, rs) for r in rows_), "n": len(rows_)}

    out = {"sentences": {g: len(stats[g]) for g in groups}, "sounds": {g: len(correct[g]) for g in groups},
           "not_graded_rows": skipped, "caps": {}}
    for cap in CAPS:
        best = None
        errs = subs["tune"] + dels["tune"]
        for rc in R_GRID:
            for rs in RS_GRID:
                ok = [m for m in M_GRID if fa("tune", m, rc, rs) <= cap]
                if ok:
                    m = float(ok[0])
                    hit = sum(flag(r, m, rc, rs) for r in errs)
                    if best is None or hit > best[0]:
                        best = (hit, m, rc, rs)
        if best is None:
            continue
        _, m, rc, rs = best
        strong = [r for r in subs["test"] if not r["weak"] and not accepted(dict(r, other=r["said"]))]
        caught = [r for r in strong if flag(r, m, rc, rs)]
        out["caps"][f"{cap:.2f}"] = {
            "margin": m, "right": rc, "sub_right": rs,
            "false_red_sentences": {g: round(fa(g, m, rc, rs), 4) for g in ("tune", "test", "korean")},
            "swaps_all": share(subs["test"], m, rc, rs),
            "swaps_stressed": share(strong, m, rc, rs),
            "swaps_stressed_vowels": share([r for r in strong if r["target"] in VOWELS], m, rc, rs),
            "swaps_stressed_consonants": share([r for r in strong if r["target"] not in VOWELS], m, rc, rs),
            "said_sound_named_right": {"caught": sum(r["other"] == r["said"] for r in caught), "n": len(caught)},
            "left_out": share(dels["test"], m, rc, rs),
        }
    return out


def show(res):
    pct = lambda d: f"{100 * d['caught'] / d['n']:5.1f}% ({d['caught']}/{d['n']})" if d["n"] else "n/a"
    print(f"correct sentences: {res['sentences']}; rows not graded (word not in the dictionary): {res['not_graded_rows']}")
    for cap, c in res["caps"].items():
        fr = c["false_red_sentences"]
        print(f"cap {float(cap):.0%}: margin > {c['margin']:+.4f}, replaced if right < {c['sub_right']}, "
              f"left out if right < {c['right']}\n"
              f"   false-red sentences: test {100 * fr['test']:.1f}%, korean {100 * fr['korean']:.1f}%\n"
              f"   swaps caught: stressed content words {pct(c['swaps_stressed'])} (vowels {pct(c['swaps_stressed_vowels'])}, "
              f"consonants {pct(c['swaps_stressed_consonants'])}); all {pct(c['swaps_all'])}\n"
              f"   said-sound named right {pct(c['said_sound_named_right'])}; left out caught {pct(c['left_out'])}")


def write(res):
    live = res["caps"][f"{LIVE_CAP:.2f}"]
    THRESHOLDS_FILE.write_text(json.dumps({
        "source": "eval/any_sound.py (see results/any_sound.json)", "enabled": True, "cap": LIVE_CAP,
        "margin": live["margin"], "right": live["right"], "sub_right": live["sub_right"], "listener": listener_id(str(live_listener("en")))}, indent=1) + "\n")
    RESULTS.write_text(json.dumps({"live_cap": LIVE_CAP, **res}, indent=1) + "\n")
    print("wrote", THRESHOLDS_FILE.relative_to(ROOT), "and", RESULTS.relative_to(ROOT))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="run the pipeline first: sentences per CMU ARCTIC voice")
    ap.add_argument("--subs", type=int, default=4)
    ap.add_argument("--dels", type=int, default=2)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if a.limit:
        run(a.limit, a.subs, a.dels)
    res = evaluate(load_rows())
    show(res)
    if a.write:
        write(res)
