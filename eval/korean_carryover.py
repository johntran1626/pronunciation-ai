"""English sounds carried into Korean, used as SIMULATED learner errors (the second of two simulation methods).
Plan and pass bar fixed before the run.

    python -m eval.korean_carryover            # ~6 min: CMU ARCTIC (4 x 150) + Zeroth test (457)
    python -m eval.korean_carryover --limit 5  # quick check

In brief: an English speaker learning Korean often just uses the English sound. So a native English
"r" in "very" is a stand-in for "Korean ㄹ said as English R". We ask: can a detector tell those English
sounds apart from real Korean ㄹ? And, the important twist, can it ALSO tell them apart from English
sounds that should PASS (the "t" in "better", which Americans say as a tap, like ㄹ)? If a detector flags
the "better" taps too, it is spotting "this is the English recording", not the mistake. Those are the
CONTROLS.

  A. Tense stops ㅃㄸㄲ (spikes/b_vot.py's cached VOTs, no model): English p/t/k "puff" vs Korean tense; control =
     English s+p/t/k ("spin": no puff).
  B. ㄹ between vowels (model run): English ɹ / l vs Korean tap; control = English flap t/d.
     Detectors: model margin (R or L tokens vs tap tokens, peak in the aligned window, as in scoring.py)
     and the F3 dip (backend/acoustics.py) for R.
Score = AUC: the chance that a random error scores more "wrong" than a random correct sound (0.5 = useless).
A detector SURVIVES only if AUC >= 0.80 against Korean AND against the English controls. It is a rule-out
test only: nothing here sets a threshold or turns a Korean check on.
"""
import argparse
import copy
import csv
import io
import json
import time
from pathlib import Path

import pyarrow.parquet as pq
import soundfile as sf

from backend.acoustics import Formants, f3_dip, f3_reference
from backend.align import align, emissions
from backend.g2p import expected_phonemes
from backend.scoring import L_TOKENS, R_TOKENS, _ids, _peak
from backend.sequence_align import is_vowel
from eval.sim_validate import CMU, CMU_SPEAKERS, _ranks, prompts

ZEROTH_TEST = Path("data/zeroth/data/test-00000-of-00001.parquet")
VOT_CACHE = Path("data/cache/spike_b_vot.csv")
OUT = Path("data/cache/korean_carryover.csv")
RESULTS = Path("results/korean_carryover.json")
TAP_TOKENS = {"ɾ", "r"}   # the model writes Korean ㄹ as r (spikes/a_vowels.py) and the English flap as ɾ
BAR = 0.80
ARPA_VOWEL = set("AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW".split())


# ---------- small helpers ----------
def auc(neg, pos):
    """P(a random pos scores higher than a random neg); ties count half (Mann-Whitney U / n_pos n_neg)."""
    if not neg or not pos:
        return None
    ranks = _ranks(list(neg) + list(pos))
    r_pos = sum(ranks[len(neg):])
    return round((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)), 4)


def survives(auc_vs_korean, auc_vs_control):
    if auc_vs_korean is None or auc_vs_control is None:
        return None
    return auc_vs_korean >= BAR and auc_vs_control >= BAR


def flap_spot(arpa, i):
    """American English flaps t/d between a vowel and an UNSTRESSED vowel (better, city). Approximate rule."""
    if arpa[i].rstrip("012") not in ("T", "D") or i == 0 or i + 1 >= len(arpa):
        return False
    prev, nxt = arpa[i - 1], arpa[i + 1]
    return prev.rstrip("012") in ARPA_VOWEL and nxt.rstrip("012") in ARPA_VOWEL and nxt.endswith("0")


def intervocalic(phonemes, i):
    return 0 < i < len(phonemes) - 1 and is_vowel(phonemes[i - 1]) and is_vowel(phonemes[i + 1])


def stop_groups(rows):
    """Spike b rows -> VOT lists: English stressed p/t/k (en_asp), s+p/t/k (en_sp), b/d/g (en_vcd), Korean tense."""
    keys = {("en", "asp"): "en_asp", ("en", "sp"): "en_sp", ("en", "vcd"): "en_vcd", ("ko", "tense"): "ko_tense"}
    out = {k: [] for k in keys.values()}
    for r in rows:
        k = keys.get((r["lang"], r["cat"]))
        if k and r["vot"] != "":
            out[k].append(float(r["vot"]))
    return out


# ---------- B. measuring the ㄹ windows ----------
def _measure(audio, sr, aligned, picks, lang, speaker, utt):
    """picks = [(word_index, phoneme_index, kind)] -> rows with model margins and the F3 dip."""
    em_probs = aligned["em"].log_probs.exp()
    spf, n_frames = aligned["em"].sec_per_frame, em_probs.shape[0]
    words = aligned["words"]
    fm = Formants(audio, sr)
    ref = f3_reference([fm.f3(p["start"], p["end"]) for w in words for p in w["phonemes"]
                        if is_vowel(p["ipa"]) and "ɹ" not in p["ipa"] and p["ipa"] != "ɚ"])
    rows = []
    for wi, pi, kind in picks:
        p = words[wi]["phonemes"][pi]
        f0 = min(int(round(p["start"] / spf)), n_frames - 1)
        f1 = max(f0 + 1, min(int(round(p["end"] / spf)), n_frames))
        tap = _peak(em_probs, f0, f1, _ids(TAP_TOKENS))
        rows.append(dict(lang=lang, speaker=speaker, utt=utt, word=words[wi]["word"], kind=kind,
                         start=p["start"], end=p["end"],
                         margin_r=round(_peak(em_probs, f0, f1, _ids(R_TOKENS)) - tap, 4),
                         margin_l=round(_peak(em_probs, f0, f1, _ids(L_TOKENS)) - tap, 4),
                         f3_dip=f3_dip(fm.f3(p["start"], p["end"]), ref)))
    return rows


def english_rows(spk, utt, text):
    audio, sr = sf.read(CMU / f"cmu_us_{spk}_arctic" / "wav" / f"{utt}.wav", dtype="float32")
    expected = expected_phonemes(text, "en")
    picks = []
    for wi, w in enumerate(expected):
        arpa, ph = w["pron"].split(), w["phonemes"]
        for pi, p in enumerate(ph):
            if p == "ɹ" and intervocalic(ph, pi):
                picks.append((wi, pi, "en_r"))
            elif p == "l" and intervocalic(ph, pi):
                picks.append((wi, pi, "en_l"))
            elif len(arpa) == len(ph) and flap_spot(arpa, pi):
                picks.append((wi, pi, "en_flap"))
    if not picks:
        return []
    # Align every picked sound as the KOREAN target symbol (ㄹ -> the model's "r"), as the app would for a
    # learner reading Korean. (Run 1 aligned them as ɹ / l / t, which put the window on the English sound's
    # own spike and gave AUCs of ~1.0: too good to be true. Fixed 2026-11-12.)
    target = copy.deepcopy(expected)
    for wi, pi, _ in picks:
        target[wi]["phonemes"][pi] = "r"
    em = emissions(audio, sr)
    words = align(em, target, "en")
    return _measure(audio, sr, dict(em=em, words=words), picks, "en", spk, utt)


def korean_rows(r):
    audio, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
    expected = expected_phonemes(" ".join(r["text"].split()), "ko")
    em = emissions(audio, sr)
    words = align(em, expected, "ko")
    picks = [(wi, pi, "ko_tap") for wi, w in enumerate(expected) for pi, p in enumerate(w["phonemes"])
             if p == "ɾ" and intervocalic(w["phonemes"], pi)]
    return _measure(audio, sr, dict(em=em, words=words), picks, "ko", f"z{r['speaker_id']}", r["id"]) if picks else []


# ---------- the report ----------
def _vals(rows, kind, key, sign=1):
    return [sign * r[key] for r in rows if r["kind"] == kind and r[key] is not None]


def report(rows, vot):
    out = {}
    for error, detector, key, sign in [("ㄹ said as English R", "model margin (R vs tap)", "margin_r", 1),
                                       ("ㄹ said as English R", "F3 dip (lower = R-like)", "f3_dip", -1),
                                       ("ㄹ said as English L", "model margin (L vs tap)", "margin_l", 1)]:
        pos_kind = "en_r" if "R" in error.split()[-1] else "en_l"
        pos = _vals(rows, pos_kind, key, sign)
        a_ko, a_ctrl = auc(_vals(rows, "ko_tap", key, sign), pos), auc(_vals(rows, "en_flap", key, sign), pos)
        out[f"{error} | {detector}"] = dict(errors=len(pos), korean_correct=len(_vals(rows, "ko_tap", key)),
                                            controls=len(_vals(rows, "en_flap", key)),
                                            auc_vs_korean=a_ko, auc_vs_controls=a_ctrl, survives=survives(a_ko, a_ctrl))
    a_ko, a_ctrl = auc(vot["ko_tense"], vot["en_asp"]), auc(vot["en_sp"], vot["en_asp"])
    out["ㅃㄸㄲ said with an English-p puff | VOT"] = dict(
        errors=len(vot["en_asp"]), korean_correct=len(vot["ko_tense"]), controls=len(vot["en_sp"]),
        auc_vs_korean=a_ko, auc_vs_controls=a_ctrl, survives=survives(a_ko, a_ctrl))
    a_ko = auc([-v for v in vot["ko_tense"]], [-v for v in vot["en_vcd"]])  # English b/d/g: SHORTER VOT
    out["ㅃㄸㄲ said like English b/d/g | VOT (lower)"] = dict(
        errors=len(vot["en_vcd"]), korean_correct=len(vot["ko_tense"]), controls=0,
        auc_vs_korean=a_ko, auc_vs_controls=None, survives=None, note="reported only: no clean control")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="prompts / Korean recordings (quick check)")
    args = ap.parse_args()
    t0, rows = time.time(), []
    for utt, text in prompts(args.limit):
        for spk in CMU_SPEAKERS:
            if (CMU / f"cmu_us_{spk}_arctic" / "wav" / f"{utt}.wav").exists():
                rows += english_rows(spk, utt, text)
    for i, r in enumerate(pq.read_table(ZEROTH_TEST).to_pylist()):
        if args.limit and i >= args.limit:
            break
        try:
            rows += korean_rows(r)
        except ValueError as e:
            print(f"skip {r['id']}: {e}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    vot = stop_groups(list(csv.DictReader(open(VOT_CACHE))))
    res = report(rows, vot)
    RESULTS.write_text(json.dumps(dict(
        source="eval/korean_carryover.py : native English sounds as simulated Korean errors",
        warning="SIMULATED errors (native English sounds), native Korean correct sounds: rule-out test only.",
        bar=BAR, limit=args.limit, checks=res), ensure_ascii=False, indent=1))
    print(f"done: {len(rows)} windows in {time.time() - t0:.0f} s -> {OUT}, {RESULTS}")
    print("| error | detector | errors | Korean correct | controls | AUC vs Korean | AUC vs controls | survives |")
    print("|---|---|---|---|---|---|---|---|")
    for name, v in res.items():
        e, d = name.split(" | ")
        print(f"| {e} | {d} | {v['errors']} | {v['korean_correct']} | {v['controls']} | {v['auc_vs_korean']} | "
              f"{v['auc_vs_controls']} | {v['survives']} |")


if __name__ == "__main__":
    main()
