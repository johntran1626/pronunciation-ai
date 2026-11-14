"""Scoring v1: the red/green verdict (conservative: no soft hints).

In brief: we only ever accuse a learner of the specific mistakes we teach (the MVP pairs), and only
when the model's evidence for the WRONG sound clearly beats its evidence for the RIGHT one. Every other
sound is green. How "clearly" is a number per pair (the margin), tuned by eval/run.py so that correct
speech from speakers we never tuned on is wrongly flagged at most ~1% of the time.

Two steps:
  1. candidates(): for each sound that belongs to an MVP pair, measure the evidence:
       margin = (peak probability of the wrong sound) - (peak probability of the right sound),
                inside the time window the forced aligner gave that sound. Range -1..+1.
                Example: "right" with R -> margin about -0.9. "right" said "light" -> about +0.9.
       heard_agrees = the free recognizer (recognize.py) also wrote the wrong sound in that place.
     Extra vowel ("bus-eu"): candidate = every word-final consonant; margin = the recognizer's
     confidence in an extra vowel heard right after it (-1 if none).
  2. score_words(): red if margin > the pair's tuned margin (variant A), and for variant B also
     heard_agrees. Variant F (F3 tie-breaker): red if margin > margin (the recognizer is sure), OR
     margin > m_lo AND the F3 dip < dip (borderline, and the waveform also looks R-like). The same rule
     with another waveform feature, named by "feature" (V/B: fric or closure, backend/acoustics.py). F needs the audio;
     without it only the "sure" path can fire. A pair without a tuned, enabled threshold is never red.
     No thresholds file = all green.
     Variant D: a trained detector (backend/detector.py). The candidate also gets the 13 waveform
     measurements of its window (backend/features.py, the same numbers the eval scored), and it is red if the
     model's probability of "this is the mistake" is over the tuned threshold. No audio = no measurements = green.

Why peak probabilities in the window (spikes/c_rl.py): the model's evidence for a sound is a 1-2 frame spike,
so the peak is the cleanest summary. Why the aligner's window, not a fixed ±20 ms: windows don't overlap,
so a neighbouring R can't leak into an L's window (the "already" problem found in spikes/c_rl.py).
"""
import copy
import json
from pathlib import Path

from backend.acoustics import f3_dip, rl_f3, vb_features
from backend.align import vocab
from backend.detector import predict, vectorize
from backend.listener import thresholds_file
from backend.features import MEASURED, sound_features
from backend.sequence_align import is_vowel

THRESHOLDS_FILE = Path(__file__).with_name("thresholds.json")  # written by eval/run.py

# Model tokens that count as each sound. R/L sets come from spikes/c_rl.py (validated there).
R_TOKENS = {"ɹ", "ɚ", "ɻ", "ɑːɹ", "ɔːɹ", "oːɹ", "ɛɹ", "ɪɹ", "ʊɹ", "aɪɚ"}
L_TOKENS = {"l", "əl", "ɫ", "l̩", "lː", "ɭ", "ɭʲ"}

# MVP pairs, learning English. target = our textbook IPA; right/wrong = model tokens;
# human_wrong = how L2-ARCTIC annotators write the error (ARPAbet), used only by the eval.
PAIRS = {
    "r_as_l":   dict(target="ɹ",  right=R_TOKENS,          wrong=L_TOKENS,          produced="l",  human_wrong={"L"}),
    "l_as_r":   dict(target="l",  right=L_TOKENS,          wrong=R_TOKENS,          produced="ɹ",  human_wrong={"R"}),
    "f_as_p":   dict(target="f",  right={"f", "ɸ"},        wrong={"p", "pʰ"},       produced="p",  human_wrong={"P"}),
    "v_as_b":   dict(target="v",  right={"v"},             wrong={"b", "β"},        produced="b",  human_wrong={"B"}),
    "th_as_s":  dict(target="θ",  right={"θ"},             wrong={"s", "t", "tʰ"},  produced="s",  human_wrong={"S", "T"}),
    "dh_as_d":  dict(target="ð",  right={"ð"},             wrong={"d", "t"},        produced="d",  human_wrong={"D", "T"}),
    "ih_as_iy": dict(target="ɪ",  right={"ɪ", "ᵻ", "ɨ"},   wrong={"iː", "i"},       produced="iː", human_wrong={"IY"}),
    "iy_as_ih": dict(target="iː", right={"iː", "i"},       wrong={"ɪ"},             produced="ɪ",  human_wrong={"IH"}),
}
EXTRA_VOWEL = "extra_vowel"
PAIR_OF_TARGET = {p["target"]: name for name, p in PAIRS.items()}


def _ids(tokens):
    v = vocab()
    return [v[t] for t in tokens if t in v]


def _peak(probs, f0, f1, ids):
    """Highest summed probability of these tokens in frames f0..f1-1."""
    return probs[f0:f1, ids].sum(-1).max().item()


def candidates(em, words, lang, audio=None, sr=None):
    """Every checkable sound with its evidence. words = align() output after compare.attach_heard().
    With audio, R/L candidates also get f3_dip (backend/acoustics.py; None if it can't be measured)."""
    if lang != "en":
        return []  # v1: Korean checks need acoustics + learner data before they may turn anything red 
    probs = em.log_probs.exp()
    n_frames = probs.shape[0]
    out, f3_of, ref, vb = [], None, None, None
    for wi, w in enumerate(words):
        for pi, p in enumerate(w["phonemes"]):
            name = PAIR_OF_TARGET.get(p["ipa"])
            if name:
                pair = PAIRS[name]
                f0 = min(int(round(p["start"] / em.sec_per_frame)), n_frames - 1)
                f1 = max(f0 + 1, min(int(round(p["end"] / em.sec_per_frame)), n_frames))
                margin = _peak(probs, f0, f1, _ids(pair["wrong"])) - _peak(probs, f0, f1, _ids(pair["right"]))
                agrees = p.get("op") == "sub" and p.get("heard") in pair["wrong"]
                out.append(dict(word_index=wi, phoneme_index=pi, pair=name, margin=round(margin, 4),
                                heard_agrees=agrees))
                if audio is not None and name in ("r_as_l", "l_as_r"):
                    if f3_of is None:
                        f3_of, ref = rl_f3(audio, sr, words)  # once per sentence, only if there is an R/L
                    out[-1]["f3_dip"] = f3_dip(f3_of.get((wi, pi)), ref)
                if audio is not None and name == "v_as_b":  # frication + closure dip
                    if vb is None:
                        vb = vb_features(audio, sr, words)  # once per sentence, only if there is a V
                    out[-1].update(vb.get((wi, pi), {"fric": None, "closure": None}))
            if pi == len(w["phonemes"]) - 1 and not is_vowel(p["ipa"]):  # a word-final consonant
                confs = [c for s, c in zip(p.get("extra_after", []), p.get("extra_after_conf", [])) if is_vowel(s)]
                out.append(dict(word_index=wi, phoneme_index=pi, pair=EXTRA_VOWEL,
                                margin=round(max(confs), 4) if confs else -1.0, heard_agrees=bool(confs)))
    return out


def is_red(cand, thresholds):
    t = thresholds.get("pairs", {}).get(cand["pair"])
    if not t or not t.get("enabled"):
        return False
    if t["variant"] == "D":  # trained detector; needs the waveform measurements (score_words adds them)
        if any(n not in cand for n in MEASURED):
            return False
        return float(predict(t["model"], vectorize([cand], t["model"]["names"]))[0]) > t["threshold"]
    if t["variant"] == "F":  # tie-breaker on a waveform feature: f3_dip (R/L) or fric/closure (V/B)
        dip = cand.get(t.get("feature", "f3_dip"))
        return cand["margin"] > t["margin"] or (cand["margin"] > t["m_lo"] and dip is not None and dip < t["dip"])
    return cand["margin"] > t["margin"] and (t["variant"] == "A" or cand["heard_agrees"])


def load_thresholds(name=None):
    """The per-pair thresholds tuned for this listener (None = the original model: THRESHOLDS_FILE)."""
    path = thresholds_file("sound", name)
    return json.loads(path.read_text()) if path.exists() else {"pairs": {}}


def score_words(em, words, lang, thresholds=None, audio=None, sr=None):
    """-> a copy of words where every phoneme and word has status 'green' or 'red'.
    A red phoneme also gets pair (which mistake), produced (what we think was said) and margin."""
    thresholds = load_thresholds() if thresholds is None else thresholds
    words = copy.deepcopy(words)
    for w in words:
        for p in w["phonemes"]:
            p["status"] = "green"
    cands = candidates(em, words, lang, audio, sr)
    detector_pairs = {p for p, t in thresholds.get("pairs", {}).items() if t.get("enabled") and t.get("variant") == "D"}
    slots = sorted({(c["word_index"], c["phoneme_index"]) for c in cands if c["pair"] in detector_pairs})
    if audio is not None and slots:          # measured once per sentence, only the sounds a live detector checks
        feats = sound_features(audio, sr, words, slots=slots)
        for c in cands:
            if c["pair"] in detector_pairs:
                c.update(feats[(c["word_index"], c["phoneme_index"])])
    for c in cands:
        if is_red(c, thresholds):
            p = words[c["word_index"]]["phonemes"][c["phoneme_index"]]
            p["status"], p["pair"], p["margin"] = "red", c["pair"], c["margin"]
            p["produced"] = "extra vowel after" if c["pair"] == EXTRA_VOWEL else PAIRS[c["pair"]]["produced"]
    for w in words:
        w["status"] = "red" if any(p["status"] == "red" for p in w["phonemes"]) else "green"
    return words
