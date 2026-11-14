"""Acoustic measurements taken straight from the waveform (not from the neural model).

F3, the third formant, as a second witness for R vs L.

In brief: the mouth is a tube that rings at a few frequencies (formants). English R curls or bunches
the tongue and pulls the THIRD ring (F3) way down, roughly to 1,500-2,000 Hz for an adult man; L leaves F3
up near 2,500-3,000 Hz (approximate textbook values). So a low F3 inside an R/L window says "R-like".

Voices differ (a smaller vocal tract rings higher), so a raw Hz value means different things for different
people. We compare each R/L window with THIS recording's own vowels:
    dip = (F3 in the window - median F3 of the recording's vowels) / robust spread of those vowels
Negative dip = lower than this speaker's usual F3 = R-like. It needs only the one recording the app gets.

    fm = Formants(audio, sr)                  # Praat (parselmouth) analysis, once per recording
    ref = f3_reference([fm.f3(s, e) for s, e in vowel_windows])
    dip = f3_dip(fm.f3(start, end), ref)

Settings (same as spikes/a_vowels.py): Burg formant tracking, 5 formants, ceiling 5000 Hz for low voices and 5500 Hz
for high voices (median pitch >= 165 Hz; standard Praat advice). Only voiced frames count, so silence or a
hiss gives None, never a made-up number.
"""
import numpy as np
import parselmouth

PITCH_FLOOR, PITCH_CEILING = 75, 500
HIGH_VOICE_HZ = 165   # median pitch at or above this -> 5500 Hz formant ceiling, else 5000
TIME_STEP = 0.005     # s between formant frames
MIN_VOWELS = 3        # fewer vowels than this -> no reference (the dip would be noise)


class Formants:
    def __init__(self, audio, sr):
        audio = np.asarray(audio, dtype=np.float64)
        if audio.ndim == 2:
            audio = audio.mean(axis=1)
        snd = parselmouth.Sound(audio, sampling_frequency=sr)
        self.pitch = snd.to_pitch(time_step=TIME_STEP, pitch_floor=PITCH_FLOOR, pitch_ceiling=PITCH_CEILING)
        f0 = self.pitch.selected_array["frequency"]
        voiced = f0[f0 > 0]
        ceiling = 5500 if voiced.size and np.median(voiced) >= HIGH_VOICE_HZ else 5000
        self.formant = snd.to_formant_burg(time_step=TIME_STEP, max_number_of_formants=5, maximum_formant=ceiling)

    def f3(self, start, end):
        """Median F3 (Hz) over the VOICED frames between start and end (s). None if there are none."""
        values = []
        for t in np.arange(start, end, TIME_STEP):
            if self.pitch.get_value_at_time(t) and not np.isnan(self.pitch.get_value_at_time(t)):
                v = self.formant.get_value_at_time(3, t)
                if not np.isnan(v):
                    values.append(v)
        return float(np.median(values)) if values else None


def f3_reference(vowel_f3s):
    """-> (median, robust spread) of a recording's vowel F3s, or None if fewer than MIN_VOWELS.
    Spread = 1.4826 x median absolute deviation: like a standard deviation, but one odd vowel can't wreck it."""
    xs = np.array([v for v in vowel_f3s if v is not None], dtype=float)
    if xs.size < MIN_VOWELS:
        return None
    med = float(np.median(xs))
    spread = 1.4826 * float(np.median(np.abs(xs - med)))
    return (med, spread) if spread > 0 else None


def f3_dip(value, ref):
    """How far below this speaker's usual F3 a window is, in spreads. Negative = R-like. None if unknown."""
    if value is None or ref is None:
        return None
    med, spread = ref
    return round((value - med) / spread, 4)


def rl_f3(audio, sr, words):
    """F3 in every R/L window of an aligned sentence, plus this recording's vowel reference.
    -> ({(word_index, phoneme_index): F3 or None}, reference or None). Rhotic vowels ('er', ɚ) are left out
    of the reference because they have a low F3 themselves. Used by the app (scoring) and the eval."""
    from backend.sequence_align import is_vowel
    fm = Formants(audio, sr)
    vowels = [fm.f3(p["start"], p["end"]) for w in words for p in w["phonemes"]
              if is_vowel(p["ipa"]) and "ɹ" not in p["ipa"] and p["ipa"] != "ɚ"]
    f3_of = {(wi, pi): fm.f3(p["start"], p["end"]) for wi, w in enumerate(words)
             for pi, p in enumerate(w["phonemes"]) if p["ipa"] in ("ɹ", "l")}
    return f3_of, f3_reference(vowels)


# ---------- frication, for V vs B ----------
# In brief: V is a fricative: the lower lip almost touches the top teeth and air HISSES through the gap, so there
# is noise above 3 kHz all the way through it, and the sound never stops. B is a stop: the lips close completely
# (the level DROPS: a "closure dip"), then pop open (a short burst). So inside an expected [v]:
#   fric    = median level from 3 to 7.5 kHz in the window, minus this recording's median vowel level (dB)
#   closure = lowest overall level in the window, minus the same vowel level (dB)
# Low fric or a low closure = B-like. Both are relative to the speaker's own vowels, so mic gain cancels out.
# 7.5 kHz keeps it inside what a 16 kHz recording (the app's) can hold (up to 8 kHz).
FRAME, HOP = 0.020, 0.005   # s: 20 ms analysis frames, every 5 ms
HF_BAND = (3000.0, 7500.0)  # Hz


class Levels:
    """Overall and high-band level (dB) of every frame of a recording, computed once (numpy FFT, Hann window)."""

    def __init__(self, audio, sr):
        x = np.asarray(audio, dtype=np.float64)
        if x.ndim == 2:
            x = x.mean(axis=1)
        n, hop = int(round(FRAME * sr)), int(round(HOP * sr))
        if len(x) < n:
            x = np.pad(x, (0, n - len(x)))
        frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
        power = np.abs(np.fft.rfft(frames, axis=1)) ** 2
        freqs = np.fft.rfftfreq(n, 1 / sr)
        band = (freqs >= HF_BAND[0]) & (freqs <= min(HF_BAND[1], sr / 2))
        self.total = 10 * np.log10(power.sum(axis=1) + 1e-12)
        self.hf = 10 * np.log10(power[:, band].sum(axis=1) + 1e-12)
        # Spectral centre of mass (kHz): where the energy sits. A hiss is bright (high), a vowel dark (low)
        self.centroid = (power * freqs).sum(axis=1) / (power.sum(axis=1) + 1e-12) / 1000
        self.t = (np.arange(len(frames)) * hop + n / 2) / sr   # frame centres (s)

    def mask(self, start, end):
        """Frames whose centre lies in [start, end); at least the one nearest the middle."""
        m = (self.t >= start) & (self.t < end)
        if not m.any():
            m[int(np.argmin(np.abs(self.t - (start + end) / 2)))] = True
        return m


def vb_features(audio, sr, words, targets=("v",)):
    """-> {(word_index, phoneme_index): {"fric": dB or None, "closure": dB or None}} for every expected [v]
    (or any sound in `targets`, e.g. θ ð f: same question, hiss vs a closed stop).
    None when the recording has fewer than MIN_VOWELS vowels (no reference)."""
    from backend.sequence_align import is_vowel
    slots = [(wi, pi, p) for wi, w in enumerate(words) for pi, p in enumerate(w["phonemes"]) if p["ipa"] in targets]
    if not slots:
        return {}
    lv = Levels(audio, sr)
    vowels = [p for w in words for p in w["phonemes"] if is_vowel(p["ipa"])]
    ref = None
    if len(vowels) >= MIN_VOWELS:
        m = np.zeros_like(lv.t, dtype=bool)
        for p in vowels:
            m |= lv.mask(p["start"], p["end"])
        ref = float(np.median(lv.total[m]))
    out = {}
    for wi, pi, p in slots:
        if ref is None:
            out[(wi, pi)] = {"fric": None, "closure": None}
            continue
        m = lv.mask(p["start"], p["end"])
        out[(wi, pi)] = {"fric": round(float(np.median(lv.hf[m])) - ref, 2),
                         "closure": round(float(lv.total[m].min()) - ref, 2)}
    return out
