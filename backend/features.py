"""ONE shared list of measurements for every checked sound (fixed before any tuning, so the list itself isn't tuned on the test data).

In brief: until now each mistake had its own hand-picked clue (F3 for R/L, hiss for V/B). Here every checked
sound gets the SAME 13 numbers, measured straight from the waveform inside the window the aligner gave it. A small
model per mistake (backend/detector.py) then learns which numbers matter for that mistake. Think of a doctor who
takes the same vital signs from every patient; which ones matter depends on the illness.

Everything "relative" is relative to THIS recording's own vowels, because voices differ (a child's formants are
higher, a quiet mic is quieter). That needs only the one recording the app gets, so the app can compute exactly
what the eval computed.

  heard_nothing  the free recognizer heard nothing where this sound should be (op = del), 0/1
  dur            log(sound duration / median vowel duration): long or short for THIS speaker's pace
                 (ship vs sheep: the long vowel is longer; an extra vowel can stretch a final consonant's window)
  f1_z f2_z f3_z formants vs this speaker's vowels, in robust spreads (like f3_dip). F1 up = tongue lower,
                 F2 up = tongue further front, F3 down = R-like. None when no frame in the window is voiced.
  voiced         share of voiced frames (vocal folds buzzing): ð is voiced, θ and s are not
  hiss           median 3-7.5 kHz level minus the vowel level (dB): fricatives hiss (acoustics.frication)
  centroid       median spectral centre of mass (kHz): s is bright (~5-7 kHz), θ is weak and flat, a vowel is low
  closure        lowest level minus the vowel level (dB): a stop closes the mouth completely
  burst          biggest 5 ms jump in level (dB): the 'pop' when a stop opens (p, b, d); fricatives have none
  after_voiced   share of voiced frames in the 60 ms right after the window: a vowel that shouldn't be there
  no_formants    1 if no voiced frame gave formants (then f1/f2/f3 are None)
  no_reference   1 if the recording has fewer than 3 vowels (then every relative number is None)

Settings: the same Praat formant settings as backend/acoustics.py (Formants), the same FFT frames as Levels.
"""
import math

import numpy as np
import parselmouth

from backend.acoustics import (HIGH_VOICE_HZ, MIN_VOWELS, PITCH_CEILING, PITCH_FLOOR, TIME_STEP, Levels,
                               f3_reference)

MEASURED = ("heard_nothing", "dur", "f1_z", "f2_z", "f3_z", "voiced", "hiss", "centroid", "closure",
            "burst", "after_voiced", "no_formants", "no_reference")
AFTER = 0.060  # s looked at after a window (after_voiced)


class Tracks:
    """Pitch (voiced or not) and F1-F3 on one 5 ms grid for the whole recording, computed once.
    (Formants in acoustics.py asks Praat frame by frame per window; for 13 numbers x every sound, one grid is
    much cheaper and gives the same values.)"""

    def __init__(self, audio, sr):
        x = np.asarray(audio, dtype=np.float64)
        if x.ndim == 2:
            x = x.mean(axis=1)
        snd = parselmouth.Sound(x, sampling_frequency=sr)
        pitch = snd.to_pitch(time_step=TIME_STEP, pitch_floor=PITCH_FLOOR, pitch_ceiling=PITCH_CEILING)
        f0 = pitch.selected_array["frequency"]
        ceiling = 5500 if (f0 > 0).any() and np.median(f0[f0 > 0]) >= HIGH_VOICE_HZ else 5000
        formant = snd.to_formant_burg(time_step=TIME_STEP, max_number_of_formants=5, maximum_formant=ceiling)
        self.t = np.asarray(pitch.xs())
        self.voiced = f0 > 0
        self.f = np.array([[formant.get_value_at_time(i, t) for t in self.t] for i in (1, 2, 3)])  # (3, frames)

    def mask(self, start, end):
        m = (self.t >= start) & (self.t < end)
        if not m.any() and self.t.size and start < self.t[-1] + TIME_STEP and end > self.t[0] - TIME_STEP:
            m[int(np.argmin(np.abs(self.t - (start + end) / 2)))] = True   # a very short window: nearest frame
        return m

    def formants(self, start, end):
        """-> [F1, F2, F3] medians over voiced frames with a value, each None if there is none."""
        m = self.mask(start, end) & self.voiced
        out = []
        for row in self.f:
            v = row[m]
            v = v[~np.isnan(v)]
            out.append(float(np.median(v)) if v.size else None)
        return out


def _z(value, ref):
    if value is None or ref is None:
        return None
    med, spread = ref
    return round((value - med) / spread, 4)


def _r(x, nd=4):
    return None if x is None else round(float(x), nd)


def sound_features(audio, sr, words, slots=None):
    """-> {(word_index, phoneme_index): {name: value or None for name in MEASURED}} for each slot
    (default: every sound). words = aligned words (each phoneme has ipa, start, end, and op if compared)."""
    from backend.sequence_align import is_vowel
    if slots is None:
        slots = [(wi, pi) for wi, w in enumerate(words) for pi in range(len(w["phonemes"]))]
    if not slots:
        return {}
    tr, lv = Tracks(audio, sr), Levels(audio, sr)

    vowels = [p for w in words for p in w["phonemes"] if is_vowel(p["ipa"])]
    has_ref = len(vowels) >= MIN_VOWELS
    level_ref = dur_ref = None
    f_refs = [None, None, None]
    if has_ref:
        m = np.zeros_like(lv.t, dtype=bool)
        for v in vowels:
            m |= lv.mask(v["start"], v["end"])
        level_ref = float(np.median(lv.total[m]))
        dur_ref = float(np.median([v["end"] - v["start"] for v in vowels]))
        plain = [tr.formants(v["start"], v["end"]) for v in vowels   # rhotic vowels have a low F3 of their own
                 if "ɹ" not in v["ipa"] and v["ipa"] != "ɚ"]
        f_refs = [f3_reference([f[i] for f in plain]) for i in range(3)]

    out = {}
    for wi, pi in slots:
        p = words[wi]["phonemes"][pi]
        s, e = p["start"], p["end"]
        fm = tr.formants(s, e)
        vm = tr.mask(s, e)
        am = (tr.t >= e) & (tr.t < e + AFTER)
        lm = lv.mask(s, e)
        idx = np.flatnonzero(lm)
        idx = np.r_[idx[0] - 1, idx] if idx[0] > 0 else idx          # one frame before: a rise AT the start counts
        burst = float(np.diff(lv.total[idx]).max()) if idx.size >= 2 else None
        out[(wi, pi)] = {
            "heard_nothing": int(p.get("op") == "del"),
            "dur": _r(math.log(max(e - s, 1e-3) / dur_ref)) if has_ref and dur_ref > 0 else None,
            "f1_z": _z(fm[0], f_refs[0]), "f2_z": _z(fm[1], f_refs[1]), "f3_z": _z(fm[2], f_refs[2]),
            "voiced": _r(tr.voiced[vm].mean()) if vm.any() else None,
            "hiss": _r(np.median(lv.hf[lm]) - level_ref, 2) if has_ref else None,
            "centroid": _r(np.median(lv.centroid[lm]), 3),
            "closure": _r(lv.total[lm].min() - level_ref, 2) if has_ref else None,
            "burst": _r(burst, 2),
            "after_voiced": _r(tr.voiced[am].mean()) if am.any() else 0.0,
            "no_formants": int(all(v is None for v in fm)),
            "no_reference": int(not has_ref),
        }
    return out
