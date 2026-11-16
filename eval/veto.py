"""Second opinion on English reds: would asking the ORIGINAL model (facebook/wav2vec2-xlsr-53-espeak-cv-ft) before
marking a sound red cut false alarms without losing real catches? Measurement only; the app is unchanged.

    python -m eval.veto --limit 1132    # run BOTH listeners on the eval/any_sound.py set (~1 h) -> data/cache/any_sound_veto.csv
    python -m eval.veto                 # re-read the cache and print the table
    python -m eval.veto --write         # also write results/veto.json

The idea in plain words: the live English listener is a fine-tuned copy of the original model. Fine-tuning made
it better on most sounds, but it also picked up its own odd habits (a correct L in "locker" heard as W). The
original model has different habits. If a red only stands when BOTH models find the sound wrong, a false red
needs both to be fooled at the same spot, which should be rarer. The price: a real mistake the original model
misses gets cancelled too. This script measures both sides on the same recordings as eval/any_sound.py.

The second opinion reads the original model's probabilities in the SAME time window the live check used (the
fine-tuned listener's forced alignment), so both models judge exactly the same stretch of audio:
  - a swap stands only if the original's margin (best other sound minus the expected sound) is above vm AND the
    other sound it prefers is not a normal native variant (backend/any_sound.accepted);
  - a left-out sound stands only if the original's evidence for the expected sound is below vr.
vm = None or vr = inf switches that half off. The veto is fair only if the cut-offs are re-tuned with it at the
SAME false-alarm cap (fewer false reds leave room for more lenient cut-offs), so both versions are tuned the same
way on the tune voices and compared on the held-out voices.
"""
import argparse
import csv
import json
import random
import statistics
import time
from itertools import product

import numpy as np
import soundfile as sf

from backend.align import MODEL, align, emissions, live_listener
from backend.any_sound import THRESHOLDS_FILE, VOWELS, accepted, dropped_ok, evidence
from backend.compare import attach_heard
from backend.g2p import expected_phonemes
from backend.recognize import recognize
from eval.any_sound import (CAPS, LIVE_CAP, M_GRID, R_GRID, ROOT, RS_GRID, add_context, cmu_items, korean_items,
                            variants)
from eval.l2arctic import label_phonemes

OUT = ROOT / "data" / "cache" / "any_sound_veto.csv"
RESULTS = ROOT / "results" / "veto.json"
NO_VETO = (None, np.inf)
VM_GRID = [None] + [float(x) for x in np.round(np.arange(-0.9, 0.95, 0.1), 2)]
VR_GRID = [np.inf, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005]
FIXED_VETOES = [(-0.5, np.inf), (-0.1, np.inf), (0.0, np.inf), (0.3, np.inf), (None, 0.2), (-0.3, 0.2)]
FIELDS = ["group", "speaker", "utt", "cond", "said", "word_index", "phoneme_index", "target", "right", "other",
          "margin", "op", "heard", "agrees", "human", "o_right", "o_other", "o_margin", "o_op", "o_heard", "o_sec"]


# ---------- the rule ----------
def flag2(r, m, rc, rs, veto):
    """eval/any_sound.flag (the live rule) plus the original model's second opinion. veto = (vm, vr)."""
    vm, vr = veto
    if r["skip"]:
        return False
    confirmed = vm is None or (r["o_margin"] > vm and not accepted(dict(r, other=r["o_other"])))
    swapped = (r["margin"] > m or (r["op"] == "sub" and r["right"] < rs)) and not accepted(r) and confirmed
    missing = r["op"] == "del" and r["right"] < rc and not dropped_ok(r) and r["o_right"] < vr
    return swapped or missing


def to_arrays(rows):
    """The same facts as numpy arrays, so thousands of cut-off combinations can be tried in seconds."""
    sents = {}
    sid = np.array([sents.setdefault((r["speaker"], r["utt"]), len(sents)) for r in rows], dtype=int)
    col = lambda f: np.array([f(r) for r in rows], dtype=bool) if rows else np.zeros(0, bool)
    num = lambda k: np.array([r[k] for r in rows], dtype=float)
    a = dict(sid=sid, n=len(sents), margin=num("margin"), right=num("right"), o_margin=num("o_margin"),
             o_right=num("o_right"), skip=col(lambda r: r["skip"]), sub=col(lambda r: r["op"] == "sub"),
             dele=col(lambda r: r["op"] == "del"), acc=col(accepted), dok=col(dropped_ok),
             o_acc=col(lambda r: accepted(dict(r, other=r["o_other"]))))
    could_fire = ~a["skip"] & (~a["acc"] | (a["dele"] & ~a["dok"]))   # eval/any_sound.evaluate counts these sentences
    member = np.zeros(a["n"], bool)
    member[sid[could_fire]] = True
    a["member"] = member
    return a


def _parts(a, rc, rs, veto):
    vm, vr = veto
    confirmed = np.ones_like(a["skip"]) if vm is None else (a["o_margin"] > vm) & ~a["o_acc"]
    swap_ok = ~a["skip"] & ~a["acc"] & confirmed
    other = (swap_ok & a["sub"] & (a["right"] < rs)) | \
            (~a["skip"] & a["dele"] & (a["right"] < rc) & ~a["dok"] & (a["o_right"] < vr))
    return swap_ok, other


def flags(a, m, rc, rs, veto):
    swap_ok, other = _parts(a, rc, rs, veto)
    return other | (swap_ok & (a["margin"] > m))


def false_red_curve(a, rc, rs, veto, grid):
    """Share of correct sentences with at least one red, for every margin cut-off in grid."""
    swap_ok, other = _parts(a, rc, rs, veto)
    top = np.full(a["n"], -9.0)
    np.maximum.at(top, a["sid"][swap_ok], a["margin"][swap_ok])
    any_other = np.zeros(a["n"], bool)
    any_other[a["sid"][other]] = True
    fired = any_other[:, None] | (top[:, None] > np.asarray(grid)[None, :])
    return fired[a["member"]].mean(0) if a["member"].any() else np.full(len(grid), np.nan)


# ---------- running both listeners ----------
def run(limit, n_sub, n_del, seed=0):
    """eval/any_sound.run (same voices, same made-up mistakes, same seed) with the original model's evidence added."""
    if live_listener("en") == MODEL:
        raise SystemExit("the fine-tuned English listener isn't set up here, so there is nothing to compare")
    rng = random.Random(seed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=FIELDS)
        wr.writeheader()
        items = list(cmu_items(limit)) + list(korean_items(limit // 2))
        for n, (group, spk, utt, text, wav, human_labels) in enumerate(items, 1):
            try:
                audio, sr = sf.read(wav, dtype="float32")
                expected = expected_phonemes(text, "en")
                em = emissions(audio, sr, "en")                 # the live (fine-tuned) listener
                t0 = time.perf_counter()
                em2 = emissions(audio, sr, model=MODEL)         # the second opinion
                o_sec = round(time.perf_counter() - t0, 3)
                if em2.log_probs.shape != em.log_probs.shape:
                    raise ValueError("the two listeners gave different frame counts")
                heard, heard2 = recognize(em), recognize(em2)
                p1, p2 = em.log_probs.exp(), em2.log_probs.exp()

                def both(target):
                    raw = align(em, target, "en")
                    ev1 = evidence(p1, em.sec_per_frame, attach_heard(raw, heard, "en")[0])
                    ev2 = evidence(p2, em.sec_per_frame, attach_heard(raw, heard2, "en")[0])
                    return [dict(e1, o_right=e2["right"], o_other=e2["other"], o_margin=e2["margin"], o_op=e2["op"],
                                 o_heard=e2["heard"], o_sec=o_sec) for e1, e2 in zip(ev1, ev2)]

                correct = both(expected)
            except ValueError as e:
                print("skip", spk, utt, e)
                continue
            labels = label_phonemes(expected, human_labels)[0] if human_labels else None
            offsets = [0]
            for w in expected:
                offsets.append(offsets[-1] + len(w["phonemes"]))
            for ev in correct:
                lab = labels[offsets[ev["word_index"]] + ev["phoneme_index"]] if labels else None
                human = "" if labels is None else ("unlabelled" if lab is None else lab[0])
                wr.writerow(dict(group=group, speaker=spk, utt=utt, cond="correct", said=ev["target"], human=human, **ev))
            if group == "korean":
                continue
            for new, (cond, said, tgt, wi, pi) in variants(expected, rng, n_sub, n_del):
                try:
                    evs = both(new)
                except ValueError:
                    continue
                for ev in evs:
                    if (ev["word_index"], ev["phoneme_index"]) == (wi, pi):
                        wr.writerow(dict(group=group, speaker=spk, utt=utt, cond=cond, said=said or "", human="", **ev))
            if n % 50 == 0:
                print(f"{n}/{len(items)}", flush=True)
                f.flush()


def load_rows():
    rows = list(csv.DictReader(OUT.open()))
    for r in rows:
        for k in ("margin", "right", "o_margin", "o_right", "o_sec"):
            r[k] = float(r[k])
    add_context(rows)
    return rows


# ---------- the numbers ----------
def tune(a_correct, a_errs, cap, vetoes):
    """The most lenient cut-offs (and veto) that keep correct TUNE sentences with a false red at or under cap,
    picking whatever catches the most tune mistakes. Ties keep the earlier option (no veto comes first)."""
    best = None
    for rc, rs, veto in product(R_GRID, RS_GRID, vetoes):
        ok = np.nonzero(false_red_curve(a_correct, rc, rs, veto, M_GRID) <= cap)[0]
        if not len(ok):
            continue
        m = float(M_GRID[ok[0]])
        hit = int(flags(a_errs, m, rc, rs, veto).sum())
        if best is None or hit > best[0]:
            best = (hit, m, rc, rs, veto)
    return best


def evaluate(rows):
    rows = [r for r in rows if not r["skip"]]
    pick = lambda cond, g: [r for r in rows if r["cond"] == cond and r["group"] == g]
    correct = {g: [r for r in pick("correct", g) if g != "korean" or r["human"] == "correct"]
               for g in ("tune", "test", "korean")}
    subs, dels = {g: pick("sub", g) for g in ("tune", "test")}, {g: pick("del", g) for g in ("tune", "test")}
    strong = [r for r in subs["test"] if not r["weak"] and not accepted(dict(r, other=r["said"]))]
    sets = {"stressed": strong, "stressed_vowels": [r for r in strong if r["target"] in VOWELS],
            "stressed_consonants": [r for r in strong if r["target"] not in VOWELS], "all": subs["test"],
            "left_out": dels["test"]}
    A = {k: to_arrays(v) for k, v in {**{f"c_{g}": v for g, v in correct.items()}, **sets,
                                      "tune_errs": subs["tune"] + dels["tune"]}.items()}

    def measure(m, rc, rs, veto):
        share = lambda k: {"caught": int(flags(A[k], m, rc, rs, veto).sum()), "n": len(sets[k])}
        return {"margin": m, "right": rc, "sub_right": rs,
                "veto_margin": veto[0], "veto_right": None if np.isinf(veto[1]) else veto[1],
                "false_red_sentences": {g: round(float(false_red_curve(A[f"c_{g}"], rc, rs, veto, [m])[0]), 4)
                                        for g in ("tune", "test", "korean")},
                **{f"swaps_{k}" if k != "left_out" else k: share(k) for k in sets}}

    live = json.loads(THRESHOLDS_FILE.read_text())
    out = {"sentences": {g: int(A[f"c_{g}"]["member"].sum()) for g in ("tune", "test", "korean")},
           "live_today": measure(live["margin"], live["right"], live["sub_right"], NO_VETO), "caps": {}}
    # the other way to use a veto: keep today's cut-offs and only cancel reds (fewer false reds, some catches lost)
    out["live_cutoffs_with_veto"] = [measure(live["margin"], live["right"], live["sub_right"], v) for v in FIXED_VETOES]
    sec = list({(r["speaker"], r["utt"]): r["o_sec"] for r in rows}.values())
    out["second_model_sec"] = {"median": round(statistics.median(sec), 3),
                               "p95": round(float(np.percentile(sec, 95)), 3), "n": len(sec)}
    for cap in CAPS:
        res = {}
        for name, vetoes in (("no_veto", [NO_VETO]), ("veto", list(product(VM_GRID, VR_GRID)))):
            best = tune(A["c_tune"], A["tune_errs"], cap, vetoes)
            if best:
                res[name] = measure(*best[1:])
        out["caps"][f"{cap:.2f}"] = res
    return out


def show(res):
    pct = lambda d: f"{100 * d['caught'] / d['n']:5.1f}%" if d["n"] else "  n/a"

    def line(name, c):
        fr = c["false_red_sentences"]
        return (f"  {name:<10} false-red sentences: natives {100 * fr['test']:4.1f}%  korean {100 * fr['korean']:4.1f}%"
                f" | swaps caught: stressed {pct(c['swaps_stressed'])} (vowels {pct(c['swaps_stressed_vowels'])},"
                f" consonants {pct(c['swaps_stressed_consonants'])}), all {pct(c['swaps_all'])}"
                f" | left out {pct(c['left_out'])}"
                f"\n             cut-offs: margin > {c['margin']:+.4f}, sub right < {c['sub_right']}, left-out right < "
                f"{c['right']}; veto: original margin > {c['veto_margin']}, original right < {c['veto_right']}")

    print(f"held-out correct sentences: natives {res['sentences']['test']}, korean {res['sentences']['korean']}")
    print(line("live today", res["live_today"]))
    print("today's cut-offs, veto added (cancels reds only):")
    for c in res["live_cutoffs_with_veto"]:
        print(line("+ veto", c))
    for cap, c in res["caps"].items():
        print(f"cap {float(cap):.0%} (on the tune voices):")
        for name in ("no_veto", "veto"):
            if name in c:
                print(line(name.replace("_", " "), c[name]))
    s = res["second_model_sec"]
    print(f"second model: median {s['median']} s, p95 {s['p95']} s per sentence ({s['n']} sentences, CPU)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="run both listeners first: sentences per CMU ARCTIC voice")
    ap.add_argument("--subs", type=int, default=4)
    ap.add_argument("--dels", type=int, default=2)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if a.limit:
        run(a.limit, a.subs, a.dels)
    res = evaluate(load_rows())
    show(res)
    if a.write:
        RESULTS.write_text(json.dumps(res, indent=1) + "\n")
        print("wrote", RESULTS.relative_to(ROOT))
