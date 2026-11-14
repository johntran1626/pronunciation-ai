"""Which listener (wav2vec2 phoneme recognizer) runs, and which threshold files belong to it. No torch here.

Two users of this module:
  - Eval scripts call listener(): the original MODEL, or the folder in PC_LISTENER (e.g. data/models/listener_v1/best)
    to run the SAME pipeline with the fine-tuned listener.
  - The live app calls live_listener(lang): English uses the fine-tuned listener (it passed the false-alarm bar on
    more English pairs than the original, results/listeners.json); Korean stays on the original MODEL (the
    fine-tune trained on English speech only, and the Korean cut-offs were measured with the original).

In brief: thresholds are like the calibration of one particular scale. A cut-off tuned on one listener's
probabilities means nothing for another listener, so every listener has its own threshold files, and the
fine-tuned listener is only used when its weights AND both of its threshold files exist. Otherwise (e.g. a fresh
clone, where the git-ignored weights are missing) English quietly uses the original MODEL with its own files.
The fine-tune kept MODEL's symbol set, so backend/align.py's vocab() is the same for both.
"""
import os
from pathlib import Path

MODEL = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
LISTENER_ENV = "PC_LISTENER"
ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path(__file__).parent
FINE_TUNED = ROOT / "data" / "models" / "listener_v1" / "best"   # git-ignored weights (eval/finetune.py)
FINE_TUNED_LANGS = ("en",)
STEMS = {"sound": "thresholds", "match": "match_thresholds"}     # per-pair sound checks / "did you say it?"


def listener():
    """The listener eval scripts load: the PC_LISTENER folder if set, else the original MODEL."""
    return os.environ.get(LISTENER_ENV) or MODEL


def listener_tag(name=None):
    """'' for the original MODEL; else a short name for file paths ('.../listener_v1/best' -> 'listener_v1')."""
    name = listener() if name is None else name
    if name == MODEL:
        return ""
    p = Path(name)
    return p.parent.name if p.name == "best" else p.name


def listener_id(name):
    """What gets saved next to results: MODEL's hub name, or the short tag (no path from this machine)."""
    return listener_tag(name) or MODEL


def thresholds_file(kind, name=None):
    """backend/thresholds.json for the original MODEL (name None = MODEL), backend/thresholds_<tag>.json otherwise.
    kind: 'sound' (per-pair checks, backend/scoring.py) or 'match' (did you say it?, backend/match.py)."""
    tag = listener_tag(name or MODEL)
    return BACKEND / (f"{STEMS[kind]}_{tag}.json" if tag else f"{STEMS[kind]}.json")


def ready(folder):
    """True when the listener's weights and both of its threshold files exist."""
    return (Path(folder) / "config.json").exists() and all(thresholds_file(k, str(folder)).exists() for k in STEMS)


def live_listener(lang):
    """The listener the app runs for this language. PC_LISTENER still overrides (for testing the app with it)."""
    env = os.environ.get(LISTENER_ENV)
    if env:
        return env
    if lang in FINE_TUNED_LANGS and ready(FINE_TUNED):
        return str(FINE_TUNED)
    return MODEL
