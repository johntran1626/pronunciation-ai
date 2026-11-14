"""Which listener (wav2vec2 phoneme recognizer) the pipeline loads. No torch here, so light scripts can import it.

Unset PC_LISTENER = the original MODEL (what the live app uses). Set it to a folder written by eval/finetune.py
(e.g. data/models/listener_v1/best) to run the SAME pipeline with the fine-tuned listener.
The fine-tune kept MODEL's symbol set, so backend/align.py's vocab() is the same for both.
"""
import os
from pathlib import Path

MODEL = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
LISTENER_ENV = "PC_LISTENER"


def listener():
    """The listener to load: the PC_LISTENER folder if set, else the original MODEL."""
    return os.environ.get(LISTENER_ENV) or MODEL


def listener_tag(name=None):
    """'' for the original MODEL; else a short name for file paths ('.../listener_v1/best' -> 'listener_v1')."""
    name = listener() if name is None else name
    if name == MODEL:
        return ""
    p = Path(name)
    return p.parent.name if p.name == "best" else p.name
