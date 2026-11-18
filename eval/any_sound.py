"""Eval of the every-sound English check (backend/any_sound.py): does it catch ANY English sound said as another
sound, or left out, without marking correct speech red?

    python -m eval.any_sound --limit 1132    # all CMU ARCTIC sentences of 9 voices + 566 per Korean voice (~1 h)
    python -m eval.any_sound                 # re-read data/cache/any_sound.csv and print the table
    python -m eval.any_sound --write         # also write backend/any_sound_thresholds.json + results/any_sound.json
    python -m eval.any_sound --never-blurred [--write]   # gentler cut for vowel pairs natives never blur

The idea in plain words: we have thousands of CORRECT recordings, but no recordings of a native speaker saying
every possible wrong sound. So we make the mistake on the TEXT side instead. A correct recording of "testing"
scored against the target "tasting" is exactly a learner who said [ɛ] where [eɪ] was wanted. Changing one sound of
the target per try gives thousands of real "said X instead of Y" cases with a known answer, from real voices,
with no hand labelling. Adding a sound to the target that the speaker never said gives a "sound left out" case.

Who is used for what (by speaker, never by recording):
    tune = CMU ARCTIC bdl, aew, jmk (Canadian) (male) + slt, ljm (female);  test = rms (male) + clb, eey, lnh (female);
    (until 2026-11-16 only bdl + slt / rms + clb: 2 tune voices proved too few for per-pair cut-offs);
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
from backend.any_sound import CLASSES, NAMES, THRESHOLDS_FILE, VOWELS, accepted, context, dropped_ok, evidence, margin_cut
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
# 9 native US / Canadian voices (CMU ARCTIC; the 5 added later have no license file in their archives: used on this
# machine for evaluation only, never redistributed). None were in the listener's fine-tune data.
TUNE, TEST = ("bdl", "slt", "aew", "ljm", "jmk"), ("rms", "clb", "eey", "lnh")
CAPS, LIVE_CAP = (0.02, 0.05, 0.10), 0.05
M_GRID = np.round(np.concatenate([np.arange(-1.0, 0.9, 0.02), np.arange(0.9, 1.0001, 0.0025)]), 4)
R_GRID = [0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05]
RS_GRID = [0.0, 0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.005, 0.01]
# Per-pair cut-offs (python -m eval.any_sound --pairs), all fixed BEFORE looking at the held-out voices:
FLOOR = 0.25            # never gentler than this: another sound must win by at least 0.25
MIN_N = 100             # a target needs this many correct tune examples before it gets its own cut-offs
SAFETY_GRID = [0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5]
ADD_CAP = 0.005         # leave-one-voice-out on tune: the pair cuts may add at most 0.5 points of false-red sentences
PAIR_BARS = {"test_false_red_max": 0.05, "korean_false_red_max_rise": 0.01}   # held out; plus: catches must go up
PAIRS_RESULTS = ROOT / "results" / "any_sound_pairs.json"
# Never-blurred vowel pairs (python -m eval.any_sound --never-blurred): a stressed vowel natives never said like a
# given other vowel gets the gentler cut NB_CUT. Bars = PAIR_BARS (fixed before). NB_CUT was chosen on 2026-11-17
# knowing one real "lucky" said "lacky" scored margin 0.83, so it is not a blind choice; the bars are on held-out voices.
NB_CUT = 0.8
NB_RESULTS = ROOT / "results" / "any_sound_never_blurred.json"


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
def flag(r, m, rc, rs=0.0, cuts=None, nb=None):
    """The live rule (backend/any_sound.verdict) with these cut-offs: m = margin, rc = right for a dropped sound,
    rs = right for a sound the recognizer replaced, cuts = per-pair margin cut-offs (pair_cuts), nb = the
    never-blurred vowel pairs ({"cut", "pairs"}, never_blurred_pairs)."""
    if r["skip"]:
        return False
    swapped = (r["margin"] > margin_cut(r, {"margin": m, "pair_margin": cuts, "never_blurred": nb}) or (r["op"] == "sub" and r["right"] < rs)) \
        and not accepted(r)
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


# ---------- per-pair cut-offs ----------
# The one global margin cut-off is set by the pairs natives blur on their own, so a pair natives never blur (stressed
# ɪ heard as ʌ: "drinking" said "drunking") can be missed at margin 0.3. Here each (target, other sound) pair with
# enough correct tune examples gets its own cut-off: the worst margin any CORRECT tune sound of that target showed
# toward that other sound, plus a safety gap, never below FLOOR and only if it is gentler than the global cut.
# "target *" = the target's fallback for other sounds never seen as its best rival: a correct sound's margin toward
# any other sound is at most its margin toward its best rival, so the worst best-rival margin bounds them all.
def pair_cuts(correct, global_m, safety, floor=FLOOR, min_n=MIN_N):
    """correct = correct tune rows (with context). -> {"t o": cut, "t *": cut} (only cuts below global_m)."""
    by_target = defaultdict(list)
    for r in correct:
        if not r["skip"]:
            by_target[r["target"]].append(r)
    cuts = {}
    for t, rs in by_target.items():
        if len(rs) < min_n:
            continue
        worst = defaultdict(lambda: -1.0)
        for r in rs:
            if not accepted(r):          # a native variant is never red, so it must not push a cut up
                worst[r["other"]] = max(worst[r["other"]], r["margin"])
        for key, m in [(f"{t} {o}", m) for o, m in worst.items()] + [(f"{t} *", max(worst.values(), default=-1.0))]:
            cut = round(max(floor, m + safety), 4)
            if cut < global_m:
                cuts[key] = cut
    return cuts


def _false_red(rows, m, rc, rs, cuts=None, nb=None):
    """Share of correct sentences with at least one false red (swap or left-out sound)."""
    hit = defaultdict(bool)
    for r in rows:
        k = (r["speaker"], r["utt"])
        hit[k] |= flag(r, m, rc, rs, cuts, nb) or (r["op"] == "del" and r["right"] < rc and not dropped_ok(r))
    return sum(hit.values()) / len(hit) if hit else float("nan")


def choose_safety(correct_tune, m, rc, rs, grid=SAFETY_GRID, add_cap=ADD_CAP):
    """The smallest safety gap whose pair cuts, made from the OTHER tune voices, add at most add_cap false-red
    sentences on the one left out (each tune voice left out once, averaged). -> (safety, {safety: added})."""
    voices = sorted({r["speaker"] for r in correct_tune})
    added = {}
    for s in grid:
        diffs = []
        for v in voices:
            made = [r for r in correct_tune if r["speaker"] != v]
            held = [r for r in correct_tune if r["speaker"] == v]
            cuts = pair_cuts(made, m, s)
            diffs.append(_false_red(held, m, rc, rs, cuts) - _false_red(held, m, rc, rs))
        added[s] = round(float(np.mean(diffs)), 4)
        if added[s] <= add_cap:
            return s, added
    return None, added


def evaluate_pairs(rows, live):
    """Today's live cut-offs vs the same plus per-pair cut-offs, on the held-out voices."""
    rows = [r for r in rows if not r["skip"]]
    m, rc, rs = live["margin"], live["right"], live["sub_right"]
    correct = {g: [r for r in rows if r["cond"] == "correct" and r["group"] == g
                   and (g != "korean" or r["human"] == "correct")] for g in ("tune", "test", "korean")}
    safety, added = choose_safety(correct["tune"], m, rc, rs)
    out = {"settings": {"floor": FLOOR, "min_n": MIN_N, "add_cap": ADD_CAP, "bars": PAIR_BARS},
           "leave_one_voice_out_added": {str(k): v for k, v in added.items()}, "safety": safety}
    if safety is None:
        out["adopt"] = False
        return out
    cuts = pair_cuts(correct["tune"], m, safety)
    subs = [r for r in rows if r["cond"] == "sub" and r["group"] == "test"]
    strong = [r for r in subs if not r["weak"] and not accepted(dict(r, other=r["said"]))]
    lax = {"ɪ", "ʌ", "æ", "ɛ", "ʊ"}
    sets = {"swaps_all": subs, "swaps_stressed": strong,
            "swaps_stressed_vowels": [r for r in strong if r["target"] in VOWELS],
            "swaps_stressed_consonants": [r for r in strong if r["target"] not in VOWELS],
            "swaps_stressed_lax_vowels": [r for r in strong if r["target"] in lax and r["said"] in lax],
            "left_out": [r for r in rows if r["cond"] == "del" and r["group"] == "test"]}

    def measure(c):
        return {"false_red_sentences": {g: round(_false_red(correct[g], m, rc, rs, c), 4) for g in correct},
                **{k: {"caught": sum(flag(r, m, rc, rs, c) for r in v), "n": len(v)} for k, v in sets.items()}}
    today, pairs = measure(None), measure(cuts)
    fr = pairs["false_red_sentences"]
    out.update(n_pair_cuts=len(cuts), pair_margin=dict(sorted(cuts.items())), today=today, with_pairs=pairs)
    out["adopt"] = bool(fr["test"] <= PAIR_BARS["test_false_red_max"]
                        and fr["korean"] <= today["false_red_sentences"]["korean"] + PAIR_BARS["korean_false_red_max_rise"]
                        and pairs["swaps_stressed"]["caught"] > today["swaps_stressed"]["caught"])
    return out


def show_pairs(p):
    print(f"leave-one-voice-out, false-red sentences added by the pair cuts: {p['leave_one_voice_out_added']}")
    if p["safety"] is None:
        print("no safety gap kept the added false reds under the cap: per-pair cut-offs NOT adopted")
        return
    pct = lambda d: f"{100 * d['caught'] / d['n']:5.1f}% ({d['caught']}/{d['n']})" if d["n"] else "n/a"
    print(f"safety {p['safety']}: {p['n_pair_cuts']} pair cut-offs below the global one")
    for name in ("today", "with_pairs"):
        c = p[name]
        fr = c["false_red_sentences"]
        print(f"{name:10s} false-red sentences: tune {100 * fr['tune']:.1f}%, test {100 * fr['test']:.1f}%, "
              f"korean {100 * fr['korean']:.1f}% | stressed swaps {pct(c['swaps_stressed'])}, vowels "
              f"{pct(c['swaps_stressed_vowels'])}, lax vowels {pct(c['swaps_stressed_lax_vowels'])}, consonants "
              f"{pct(c['swaps_stressed_consonants'])}, all swaps {pct(c['swaps_all'])}, left out {pct(c['left_out'])}")
    print(f"adopt (bars fixed before the run): {p['adopt']}")


def write_pairs(p):
    PAIRS_RESULTS.write_text(json.dumps(p, indent=1, ensure_ascii=False) + "\n")
    print("wrote", PAIRS_RESULTS.relative_to(ROOT))
    if p.get("adopt"):
        t = json.loads(THRESHOLDS_FILE.read_text())
        t.update(pair_margin=p["pair_margin"], pair_source="eval/any_sound.py --pairs (see results/any_sound_pairs.json)")
        THRESHOLDS_FILE.write_text(json.dumps(t, indent=1, ensure_ascii=False) + "\n")
        print("wrote the pair cut-offs into", THRESHOLDS_FILE.relative_to(ROOT))


# ---------- never-blurred vowel pairs ----------
# The global cut sits at 0.98 because natives themselves blur some vowel pairs (ɛ/æ, ɪ/iː, ɑː/ʌ). A real learner's
# swap is less clean than a made-up one (their æ still sounds a bit like the ʌ they aimed at), so it can win by "only"
# 0.83 and stay green. Every stressed vowel pair natives NEVER blurred on the tune voices, rare pairs included, gets
# the gentler cut instead. Consonants are left out: the global cut already catches ~98% of consonant swaps, and the
# gentler cut there mostly added false reds on Korean speakers' correct sounds (ð->d, n->ŋ).
def never_blurred_pairs(correct, cut=NB_CUT, min_n=MIN_N):
    """correct = correct tune rows (with context). -> sorted "target other" vowel pairs: the target has at least
    min_n tune examples and no correct STRESSED example leaned toward that other vowel by `cut` or more."""
    n, worst = defaultdict(int), defaultdict(lambda: -9.0)
    for r in correct:
        if r["skip"] or r["target"] not in VOWELS:
            continue
        n[r["target"]] += 1
        if not r["weak"] and not accepted(r):
            worst[(r["target"], r["other"])] = max(worst[(r["target"], r["other"])], r["margin"])
    return sorted(f"{t} {o}" for t in n if n[t] >= min_n for o in VOWELS if o != t and worst[(t, o)] < cut)


def evaluate_never_blurred(rows, live, cut=NB_CUT):
    """Today's live cut-offs vs the same plus the never-blurred vowel pairs, on the held-out voices and on real
    learner mistakes (L2-ARCTIC Korean speakers' sounds the annotators marked as substituted)."""
    rows = [r for r in rows if not r["skip"]]
    m, rc, rs = live["margin"], live["right"], live["sub_right"]
    correct = {g: [r for r in rows if r["cond"] == "correct" and r["group"] == g
                   and (g != "korean" or r["human"] == "correct")] for g in ("tune", "test", "korean")}
    nb = {"cut": cut, "pairs": never_blurred_pairs(correct["tune"], cut)}
    strong = [r for r in rows if r["cond"] == "sub" and r["group"] == "test" and not r["weak"]
              and not accepted(dict(r, other=r["said"]))]
    sets = {"swaps_stressed_vowels": [r for r in strong if r["target"] in VOWELS],
            "real_learner_substitutions": [r for r in rows if r["group"] == "korean" and r["human"] == "sub"]}

    def measure(x):
        return {"false_red_sentences": {g: round(_false_red(correct[g], m, rc, rs, None, x), 4) for g in correct},
                **{k: {"caught": sum(flag(r, m, rc, rs, None, x) for r in v), "n": len(v)} for k, v in sets.items()}}
    today, with_nb = measure(None), measure(nb)
    fr = with_nb["false_red_sentences"]
    adopt = bool(fr["test"] <= PAIR_BARS["test_false_red_max"]
                 and fr["korean"] <= today["false_red_sentences"]["korean"] + PAIR_BARS["korean_false_red_max_rise"]
                 and with_nb["swaps_stressed_vowels"]["caught"] > today["swaps_stressed_vowels"]["caught"])
    return {"settings": {"cut": cut, "min_n": MIN_N, "bars": PAIR_BARS}, "n_pairs": len(nb["pairs"]),
            "never_blurred": nb, "today": today, "with_never_blurred": with_nb, "adopt": adopt}


def show_never_blurred(p):
    pct = lambda d: f"{100 * d['caught'] / d['n']:5.1f}% ({d['caught']}/{d['n']})" if d["n"] else "n/a"
    print(f"{p['n_pairs']} stressed vowel pairs natives never blurred get the cut {p['settings']['cut']}")
    for name in ("today", "with_never_blurred"):
        c = p[name]
        fr = c["false_red_sentences"]
        print(f"{name:18s} false-red sentences: tune {100 * fr['tune']:.2f}%, test {100 * fr['test']:.2f}%, "
              f"korean {100 * fr['korean']:.2f}% | stressed vowel swaps {pct(c['swaps_stressed_vowels'])} | "
              f"real learner substitutions {pct(c['real_learner_substitutions'])}")
    print(f"adopt (bars fixed before): {p['adopt']}")


def write_never_blurred(p):
    NB_RESULTS.write_text(json.dumps(p, indent=1, ensure_ascii=False) + "\n")
    print("wrote", NB_RESULTS.relative_to(ROOT))
    if p["adopt"]:
        t = json.loads(THRESHOLDS_FILE.read_text())
        t["never_blurred"] = p["never_blurred"]
        THRESHOLDS_FILE.write_text(json.dumps(t, indent=1, ensure_ascii=False) + "\n")
        print("wrote the never-blurred vowel pairs into", THRESHOLDS_FILE.relative_to(ROOT))


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
    old = json.loads(THRESHOLDS_FILE.read_text()) if THRESHOLDS_FILE.exists() else {}
    new = {"source": "eval/any_sound.py (see results/any_sound.json)", "enabled": True, "cap": LIVE_CAP,
           "margin": live["margin"], "right": live["right"], "sub_right": live["sub_right"],
           "listener": listener_id(str(live_listener("en")))}
    if "never_blurred" in old:                      # written by --never-blurred; kept across a re-tune
        new["never_blurred"] = old["never_blurred"]
    THRESHOLDS_FILE.write_text(json.dumps(new, indent=1, ensure_ascii=False) + "\n")
    RESULTS.write_text(json.dumps({"live_cap": LIVE_CAP, **res}, indent=1) + "\n")
    print("wrote", THRESHOLDS_FILE.relative_to(ROOT), "and", RESULTS.relative_to(ROOT))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="run the pipeline first: sentences per CMU ARCTIC voice")
    ap.add_argument("--subs", type=int, default=4)
    ap.add_argument("--dels", type=int, default=2)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--pairs", action="store_true", help="per-pair cut-offs on top of the live ones")
    ap.add_argument("--never-blurred", action="store_true", help="gentler cut for vowel pairs natives never blur")
    a = ap.parse_args()
    if a.limit:
        run(a.limit, a.subs, a.dels)
    if a.never_blurred:
        p = evaluate_never_blurred(load_rows(), json.loads(THRESHOLDS_FILE.read_text()))
        show_never_blurred(p)
        if a.write:
            write_never_blurred(p)
        raise SystemExit
    if a.pairs:
        p = evaluate_pairs(load_rows(), json.loads(THRESHOLDS_FILE.read_text()))
        show_pairs(p)
        if a.write:
            write_pairs(p)
        raise SystemExit
    res = evaluate(load_rows())
    show(res)
    if a.write:
        write(res)
