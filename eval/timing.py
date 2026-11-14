"""Processing time per sentence: the app's whole analysis, timed on real learner recordings.

    python -m eval.timing            # about 5 minutes on a laptop CPU; writes results/timing.json

What is timed: backend.app._run_pipeline, the exact function /analyze calls once the upload is read
(expected sounds, the listener, alignment, recognition, the sentence and word checks, the sound checks,
the text mapping). Not timed: the network, reading the upload, and loading the model, which happens once
when the server starts (one warm-up sentence absorbs it and is not counted).
Data: every reading by L2-ARCTIC's 4 Korean speakers, English, on the listener the app runs for English.
"""
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path

import soundfile as sf
import torch

from backend.app import _run_pipeline
from backend.listener import listener_id, live_listener
from eval.l2arctic import KOREAN, korean_utterances

OUT = Path("results/timing.json")
LANG = "en"


def summarize(values):
    """n, median, the slowest-5% line (same rule as eval/run.py, so old and new numbers compare) and max."""
    if not values:
        raise ValueError("no timings to summarize")
    v = sorted(values)
    return {"n": len(v), "median": round(statistics.median(v), 3),
            "p95": round(v[int(0.95 * (len(v) - 1))], 3), "max": round(v[-1], 3)}


def machine():
    """'Apple M3 Pro, 12 CPU cores': the time only means something next to the hardware it ran on."""
    try:
        chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        chip = platform.processor() or platform.machine()
    return f"{chip}, {torch.get_num_threads()} CPU threads"


def _load(wav):
    audio, sr = sf.read(wav, dtype="float32")
    return (audio.mean(axis=1) if audio.ndim > 1 else audio), sr


def main():
    readings = list(korean_utterances(None))
    first = readings[0]
    _run_pipeline(*_load(first[5]), first[4], LANG)   # warm-up: loads the model, not counted

    secs, audio_secs = [], []
    for i, (_, spk, utt, _, text, wav) in enumerate(readings, 1):
        audio, sr = _load(wav)
        t0 = time.perf_counter()
        try:
            _run_pipeline(audio, sr, text, LANG)
        except ValueError as e:   # the app answers 400 for these; nothing to time
            print(f"skip {spk}/{utt}: {e}")
            continue
        secs.append(time.perf_counter() - t0)
        audio_secs.append(len(audio) / sr)
        if i % 100 == 0:
            print(f"{i}/{len(readings)}  median so far {statistics.median(secs):.3f} s")

    result = {
        "listener": listener_id(live_listener(LANG)), "lang": LANG, "device": "cpu", "machine": machine(),
        "data": f"L2-ARCTIC, every reading by its {len(KOREAN)} Korean speakers ({', '.join(KOREAN)})",
        "timed": "backend.app._run_pipeline (the whole /analyze analysis), model already loaded",
        "seconds_per_sentence": summarize(secs),
        "audio_seconds": summarize(audio_secs),
        "skipped": len(readings) - len(secs),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    s = result["seconds_per_sentence"]
    print(f"{result['listener']} on {result['machine']}: median {s['median']} s, p95 {s['p95']} s, "
          f"max {s['max']} s (n={s['n']}); wrote {OUT}")


if __name__ == "__main__":
    main()
