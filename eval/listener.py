"""Run the eval pipeline with ANOTHER listener without touching the old listener's results.

Two environment variables, read when a script starts:
    PC_LISTENER=data/models/listener_v1/best   which listener backend/align.py loads (unset = the original model)
    PC_SPEAKERS=heldout                        only run speakers the new listener never trained on

In brief:
  - tagged(): every cache file gets its own folder per listener, data/cache/listener_v1/eval_l2arctic.csv instead
    of data/cache/eval_l2arctic.csv. Like writing a second exam's answers on a new sheet, not over the first one.
  - keep_speaker(): the fine-tuned listener has already HEARD the training speakers, so its numbers on them would
    flatter it (it partly memorised those voices). We only need dev speakers (to tune the detectors) and the Korean
    test speakers (to judge), so the training speakers are skipped: ~25% of the audio, ~4x faster.
"""
import os
from pathlib import Path

from backend.listener import listener_tag

SPEAKERS_ENV = "PC_SPEAKERS"
MODES = ("all", "heldout")


def tagged(path, tag=None):
    """data/cache/x.csv -> data/cache/<tag>/x.csv (unchanged for the original listener, tag '')."""
    tag = listener_tag() if tag is None else tag
    path = Path(path)
    return path.parent / tag / path.name if tag else path


def keep_speaker(corpus, speaker, korean, mode=None):
    """False only for a TRAINING speaker of the fine-tune, and only when PC_SPEAKERS=heldout."""
    mode = mode or os.environ.get(SPEAKERS_ENV, "all")
    if mode not in MODES:
        raise ValueError(f"{SPEAKERS_ENV}={mode!r}; use one of {MODES}")
    if mode == "all":
        return True
    if not listener_tag():
        raise ValueError(f"{SPEAKERS_ENV}=heldout with the old listener would overwrite its full caches with a "
                         f"partial run; set PC_LISTENER too")
    from eval.ft_data import split_of   # the SAME split the fine-tune used (by speaker, fixed hash)
    return split_of(corpus, speaker, korean) != "train"
