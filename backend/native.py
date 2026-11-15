"""WHEN each word and sound happens in a native reference clip (the cached Azure WAV from backend/tts.py).

    from backend.native import native_timings
    t = native_timings(tts.clip_path("Very light.", "en"), "Very light.", "en")
    t["words"][0] -> {"word": "Very", "start": 0.21, "end": 0.55, "phonemes": [{"ipa": "v", "start", "end", "conf"}, ...]}

The detail card plays "You" (your recording, cut at /analyze's times) next to "Native" (this clip, cut at these
times). It's the SAME pipeline /analyze uses, run on the computer voice instead of the learner: the G2P gives the
expected sounds, the aligner places them. Same text + same G2P = the same words and sounds in the same order, so the
card finds the native part by position (word 3, sound 2).

The model is the slow part (~1 s per clip on CPU), so the result is saved once as <same name>.json next to the
WAV. A saved file from an older version (or a broken one) is simply rebuilt.
"""
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from backend import mixed
from backend.align import align, emissions
from backend.listener import listener_id, live_listener
from backend.g2p import expected_phonemes
from backend.tts import normalize_text

TIMINGS_VERSION = 2   # bump when the output changes (new aligner, new fields) so old saved files get rebuilt
                      # 2 = last sound runs to where the voice stops (voice_end)
QUIET_DB = 35         # "voice has stopped" = 35 dB below the loudest 10 ms of the clip (clean TTS: silence is far lower)
MAX_TAIL = 0.4        # s; never stretch the last sound further than this past the aligner's end


def timings_path(wav_path):
    """data/tts_cache/<hash>.wav -> data/tts_cache/<hash>.json (the WAV's name already fingerprints text+voice+speed)."""
    return Path(wav_path).with_suffix(".json")


def voice_end(samples, sr, frame_s=0.01):
    """Seconds where the voice goes quiet for good: the end of the last 10 ms frame within QUIET_DB of the loudest."""
    x = np.asarray(samples, dtype=np.float32)
    hop = int(frame_s * sr)
    n = len(x) // hop
    rms = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    db = 20 * np.log10(rms + 1e-9)
    loud = np.nonzero(db > db.max() - QUIET_DB)[0]
    return round((loud[-1] + 1) * frame_s, 3)


def align_clip(wav_path, text, lang):
    """Run the model: the expected sounds of `text`, placed on the clip. Returns (words, duration in seconds).

    The aligner ends the LAST sound at its short CTC spike (there's no next sound to end it), which can cut off a
    long final vowel (가요 lost its last 0.11 s). The native clip is clean speech then silence, so we stretch that
    last sound to where the voice stops, by at most MAX_TAIL. (Not done for learners: their audio has room noise,
    and scoring reads those windows.)"""
    samples, sr = sf.read(wav_path, dtype="float32")
    if lang == "mix":                                   # English + Korean: hybrid alignment (backend/mixed.py)
        words, duration = mixed.align_mixed(samples, sr, expected_phonemes(text, lang)), len(samples) / sr
    else:
        em = emissions(samples, sr, lang)
        words, duration = align(em, expected_phonemes(text, lang), lang), em.duration
    last, end = words[-1]["phonemes"][-1], voice_end(samples, sr)
    last["end"] = round(min(max(last["end"], end), last["end"] + MAX_TAIL), 3)
    words[-1]["end"] = last["end"]
    return words, duration


def native_timings(wav_path, text, lang):
    """Saved timings if they're current, otherwise align the clip and save the result. Raises ValueError for a
    text with no pronounceable words (same as /analyze)."""
    path = timings_path(wav_path)
    saved = _read(path)
    model = mixed.model_id() if lang == "mix" else listener_id(live_listener(lang))  # another listener: redone
    if saved and saved.get("version") == TIMINGS_VERSION and saved.get("model") == model and saved.get("lang") == lang:
        return saved
    words, duration = align_clip(wav_path, normalize_text(text), lang)
    out = {
        "version": TIMINGS_VERSION,
        "model": model,
        "lang": lang,
        "text": normalize_text(text),
        "duration_s": round(duration, 3),
        "words": [{"word": w["word"], **({"lang": w["lang"]} if "lang" in w else {}),   # mixed: each word's language
                   "start": w["start"], "end": w["end"], "phonemes": w["phonemes"]} for w in words],
    }
    _write(path, out)
    return out


def _read(path):
    """The saved JSON, or None if there isn't one or it can't be read (half-written, hand-edited...)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path, data):
    """All-or-nothing write (temp file, then rename), like the WAV cache: a crash never leaves half a JSON."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
