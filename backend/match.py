"""Did the learner actually say THIS sentence, and each word in it?

Why it exists: forced alignment always places every expected sound somewhere in the audio, even in silence,
a beep or nonsense. The sound checks (scoring.py) only ask "was this R heard as L?", so before this module
anything that wasn't an R-said-as-L came out green.

Two evidence numbers, from what the pipeline already computes:
  heard = share of expected sounds the free recognizer heard as exactly that sound (compare.py op == "match")
  conf  = the aligner's average confidence for those sounds (align.py conf, 0..1)

  1. sentence_check(): BEFORE any coloring. Too little heard or too little confidence over the whole
     sentence -> matched = False ("no_speech" if the recognizer heard nothing at all, else "mismatch").
     The UI then shows "couldn't match your recording" and no colors.
  2. word check (in finalize()): a word is "not heard" (skipped, or a different word) when it has at least
     min_sounds sounds AND heard <= max_heard AND conf <= max_conf. All its sounds turn red.
  3. finalize(): honest colors. A sound is green only if a live SOUND check for its pair looked at it and
     passed (passing the word check alone used to make it green, which overclaimed).
     Otherwise its status is "unchecked" (shown as plain text). A "not heard" word is still red.

Thresholds: backend/match_thresholds.json, written by eval/match_tune.py (tuned on non-Korean L2-ARCTIC
speakers, tested on the Korean ones). No file = both checks off (everything passes, nothing claims green
beyond the sound checks).
"""
import copy
import json
from pathlib import Path

from backend.listener import thresholds_file
from backend.scoring import PAIR_OF_TARGET

MATCH_FILE = Path(__file__).with_name("match_thresholds.json")
OFF = {"sentence": {"enabled": False}, "word": {"enabled": False}}
NOT_HEARD = "word_not_heard"


def load_match_thresholds(name=None):
    """The "did you say it?" thresholds tuned for this listener (None = the original model: MATCH_FILE)."""
    path = thresholds_file("match", name)
    return json.loads(path.read_text()) if path.exists() else {}


def _rules(match_t, lang):
    return (match_t or {}).get(lang, OFF)


# ---------- evidence ----------
def _features(phonemes):
    n = len(phonemes)
    if n == 0:
        return {"n": 0, "heard": 0.0, "missing": 0.0, "conf": 0.0}
    ops = [p.get("op") for p in phonemes]
    return {"n": n, "heard": ops.count("match") / n, "missing": ops.count("del") / n,
            "conf": sum(p.get("conf", 0.0) for p in phonemes) / n}


def word_features(w):
    return _features(w["phonemes"])


def sentence_features(words):
    return _features([p for w in words for p in w["phonemes"]])


# ---------- 1. the sentence ----------
def sentence_check(words, n_heard, t):
    """-> (matched, reason). n_heard = how many sounds the free recognizer heard in the whole recording."""
    if not t.get("enabled"):
        return True, None
    if n_heard == 0:
        return False, "no_speech"
    f = sentence_features(words)
    if f["heard"] < t["min_heard"] or f["conf"] < t["min_conf"]:
        return False, "mismatch"
    return True, None


# ---------- 2. each word ----------
def is_not_heard(f, rule):
    return bool(rule.get("enabled")) and f["n"] >= rule["min_sounds"] and f["heard"] <= rule["max_heard"] \
        and f["conf"] <= rule["max_conf"]


# ---------- 3. honest colors ----------
def _live_pairs(sound_t, lang):
    if lang != "en":
        return set()  # sound checks are English-only in v1 (scoring.candidates)
    return {name for name, t in sound_t.get("pairs", {}).items() if t.get("enabled")}


def active_checks(lang, sound_t, match_t):
    """Names of the checks that can change a result right now, for the UI's honesty line."""
    rules = _rules(match_t, lang)
    names = []
    s = rules["sentence"]
    if s.get("enabled"):
        # thresholds at 0 only reject a recording with no speech in it: say that, not "you read the sentence"
        names.append("sentence_match" if s.get("min_heard", 0) > 0 or s.get("min_conf", 0) > 0 else "speech_heard")
    if rules["word"].get("enabled"):
        names.append("word_heard")
    return names + sorted(_live_pairs(sound_t, lang))


def finalize(words, lang, sound_t, match_t):
    """After scoring.score_words(): apply the word check, mark what was checked, set honest statuses.
    -> a copy; every phoneme gets `checked`, every word gets `not_heard`."""
    words = copy.deepcopy(words)
    word_rule = _rules(match_t, lang)["word"]
    pairs = _live_pairs(sound_t, lang)
    for w in words:
        w["not_heard"] = is_not_heard(word_features(w), word_rule)
        for p in w["phonemes"]:
            # Only a SOUND check counts. The word check can turn a word red ("not heard"), but passing it
            # only means "we heard the word", not "it sounded right", so it never makes a sound green.
            p["checked"] = PAIR_OF_TARGET.get(p["ipa"]) in pairs
            if w["not_heard"]:
                p["status"], p["pair"], p["produced"] = "red", NOT_HEARD, None
            elif p["status"] != "red" and not p["checked"]:
                p["status"] = "unchecked"
        statuses = [p["status"] for p in w["phonemes"]]
        w["status"] = "red" if "red" in statuses else "green" if "green" in statuses else "unchecked"
    return words


def mark_unchecked(words):
    """The sentence didn't match: no verdict on anything."""
    words = copy.deepcopy(words)
    for w in words:
        w["status"], w["not_heard"] = "unchecked", False
        for p in w["phonemes"]:
            p["status"], p["checked"] = "unchecked", False
    return words
