"""Spike (b): does voice onset time (VOT) separate English pin/bin/spin and Korean ㅂ/ㅃ/ㅍ?

For each recording:
  1. text -> expected phones (English: g2p_en; Korean: g2pk + our jamo table, model's own symbols)
  2. wav2vec2 forced alignment -> rough time of each word-initial stop and the vowel after it
  3. in that region, from the waveform itself:
       burst          = first sharp rise in high-frequency energy after the closure (lips/tongue release)
       voicing onset  = first moment the vocal folds vibrate steadily (Praat pitch says "voiced")
       VOT            = voicing onset - burst  (negative = voicing started before the release)
       F0             = pitch of the next vowel's first 50 ms, in semitones vs the speaker's median
  4. leave-one-speaker-out: learn a cut-off (or centroids) on the other speakers, test on the held-out one

Data: English = CMU ARCTIC bdl rms slt clb (native US). Korean = Zeroth test (10 speakers) +
train-00000 (16 speakers, first 60 recordings each).

Run:  python spikes/b_vot.py               (both languages, ~15 min)
      python spikes/b_vot.py --limit 10    (quick check: 10 recordings per language)
      python spikes/b_vot.py --plot-only   (re-analyse the cached CSV)
Throwaway feasibility code. Not part of the app.
"""
import argparse
import csv
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import parselmouth
import pyarrow.parquet as pq
import soundfile as sf
import torch
import torchaudio.functional as F
from g2p_en import G2p as G2pEn
from g2pk import G2p as G2pKo
from huggingface_hub import hf_hub_download
from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

sys.path.insert(0, str(Path(__file__).parent))
from a_vowels import CODA, HEARD_AS, ONSET, VOWEL  # Korean jamo -> phone tables (a_vowels.py)
from d_align import to_ipa  # ARPAbet -> IPA (d_align.py)

MODEL = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
CMU = Path("data/cmu_arctic")
CMU_SPEAKERS = ["bdl", "rms", "slt", "clb"]
ZEROTH = [(Path("data/zeroth/data/test-00000-of-00001.parquet"), 0),
          (Path("data/zeroth/data/train-00000-of-00006.parquet"), 60)]  # (file, max recordings per speaker; 0 = all)
EN_PER_SPEAKER = 300  # CMU ARCTIC recordings per speaker (run time; not tuned)
CACHE = Path("data/cache/spike_b_vot.csv")
PLOT = Path("spikes/out/b_vot.png")

# English: word-initial stops. 'asp' = voiceless before a stressed vowel (pin), 'vcd' = voiced (bin),
# 'sp' = after s in the same word (spin). Voiceless before an UNSTRESSED vowel is kept apart ('asp_unstr').
EN_VOICELESS, EN_VOICED = {"P": "lab", "T": "alv", "K": "vel"}, {"B": "lab", "D": "alv", "G": "vel"}
# Function words are unstressed in sentences, but g2p_en (one word at a time) gives them citation stress. Skip them.
EN_FUNCTION = {"to", "too", "do", "does", "did", "done", "but", "be", "been", "being", "by", "can", "could",
               "get", "got", "go", "goes", "going", "gone", "came", "come", "comes", "did", "don't", "didn't",
               "can't", "couldn't", "doesn't", "paid", "put", "piece", "per", "toward", "towards", "till", "than",
               "then", "the", "this", "that", "though", "together", "today", "tonight", "back", "before", "because",
               "between", "both", "down", "during", "dear", "guess", "gave", "give", "kept", "keep", "kind", "know"}
# Korean onset index (Unicode order) -> (category, place). Category is from g2pk's PRONOUNCED form.
KO_STOP = {7: ("lenis", "lab"), 8: ("tense", "lab"), 17: ("asp", "lab"),    # ㅂ ㅃ ㅍ
           3: ("lenis", "alv"), 4: ("tense", "alv"), 16: ("asp", "alv"),    # ㄷ ㄸ ㅌ
           0: ("lenis", "vel"), 1: ("tense", "vel"), 15: ("asp", "vel")}    # ㄱ ㄲ ㅋ


# ---------- alignment ----------
class Aligner:
    def __init__(self):
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        print(f"Loading {MODEL} on {self.device}...")
        self.ext = Wav2Vec2FeatureExtractor.from_pretrained(MODEL)
        self.model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval().to(self.device)
        self.vocab = json.load(open(hf_hub_download(MODEL, "vocab.json")))
        self.blank = self.model.config.pad_token_id

    def starts(self, audio, phones):
        """Start time (s) of each phone's CTC spike."""
        x = self.ext(audio, sampling_rate=16000, return_tensors="pt").input_values.to(self.device)
        with torch.inference_mode():
            lp = self.model(x).logits.log_softmax(-1).cpu()
        spf = len(audio) / 16000 / lp.shape[1]
        labels, scores = F.forced_align(lp, torch.tensor([[self.vocab[p] for p in phones]], dtype=torch.int32),
                                        blank=self.blank)
        return [s.start * spf for s in F.merge_tokens(labels[0], scores[0].exp())]


# ---------- expected phones + which ones are target stops ----------
def english_targets(text, g2p):
    """-> phones, [(stop_phone_index, category, place, word)]"""
    phones, targets = [], []
    for raw in text.split():
        word = re.sub(r"[^a-z']", "", raw.lower())
        if not word:
            continue
        arpa = [p for p in g2p(word) if p[0].isalpha()]
        if not arpa:
            continue
        base = len(phones)
        phones += [to_ipa(p) for p in arpa]
        a0 = re.sub(r"\d", "", arpa[0])
        if word in EN_FUNCTION:
            continue
        if len(arpa) >= 2 and arpa[1][-1].isdigit() and (a0 in EN_VOICELESS or a0 in EN_VOICED):
            stressed = arpa[1][-1] in "12"
            if a0 in EN_VOICED:
                cat = "vcd" if stressed else "vcd_unstr"
            else:
                cat = "asp" if stressed else "asp_unstr"
            targets.append((base, cat, {**EN_VOICELESS, **EN_VOICED}[a0], word))
        elif (len(arpa) >= 3 and a0 == "S" and re.sub(r"\d", "", arpa[1]) in EN_VOICELESS
              and arpa[2][-1].isdigit()):
            targets.append((base + 1, "sp", EN_VOICELESS[re.sub(r"\d", "", arpa[1])], word))
    return phones, targets


def korean_targets(text, g2p):
    """-> phones (model's symbols), [(stop_phone_index, category, place, word, utterance_initial)]"""
    pron = g2p(text)
    orig_words, pron_words = text.split(), pron.split()
    phones, targets, prev_coda = [], [], None
    for wi, pw in enumerate(pron_words):
        for si, ch in enumerate(pw):
            o = ord(ch) - 0xAC00
            if not 0 <= o < 11172:
                continue
            on_i, (_, vowels), coda = o // 588, VOWEL[(o % 588) // 28], CODA[o % 28]
            onset = ONSET[on_i]
            if onset == "ɾ" and prev_coda == "l":
                onset = "l"
            if si == 0 and on_i in KO_STOP and len(orig_words) == len(pron_words):
                # only if the WRITTEN word also starts with a stop (not a coda moved over by liaison)
                oc = ord(orig_words[wi][0]) - 0xAC00
                if 0 <= oc < 11172 and (oc // 588) in KO_STOP:
                    cat, place = KO_STOP[on_i]
                    targets.append((len(phones), cat, place, orig_words[wi], wi == 0))
            if onset:
                phones.append(onset)
            phones += vowels
            if coda:
                phones.append(coda)
            prev_coda = coda
    return [HEARD_AS.get(p, p) for p in phones], targets


# ---------- acoustic measurement ----------
def measure_vot(audio, pitch, t_stop, t_next):
    """Burst, voicing onset, VOT (ms) and early-vowel F0 for one stop, or None if it can't be measured.
    t_stop / t_next = aligner spike times of the stop and of the phone after it.
    Order of work: closure (quietest point) -> voicing onset after it -> burst = first big rise BEFORE that onset.
    (v1 looked for the burst first and sometimes found it after voicing had started.)"""
    sr = 16000
    lo, hi = max(0.0, t_stop - 0.06), min(len(audio) / sr, t_next + 0.06)
    seg = audio[int(lo * sr):int(hi * sr)]
    if len(seg) < int(0.03 * sr):
        return None
    pre = np.append(seg[0], seg[1:] - 0.97 * seg[:-1])  # pre-emphasis: boosts the hiss of a burst
    hop, win = int(0.001 * sr), int(0.003 * sr)  # 1 ms steps, 3 ms windows
    e = np.array([10 * np.log10(np.mean(pre[i:i + win] ** 2) + 1e-10) for i in range(0, len(pre) - win, hop)])
    t = lo + np.arange(len(e)) * 0.001 + 0.0015
    search = t < t_next
    if search.sum() < 5:
        return None
    ci = int(np.argmin(np.where(search, e, np.inf)))  # closure = quietest point before the next phone
    tc = t[ci]
    pt, f0 = pitch.xs(), pitch.selected_array["frequency"]
    voiced = f0 > 0
    k = int(np.searchsorted(pt, tc))
    if k >= len(pt) - 4:
        return None
    if voiced[max(k - 1, 0)] and voiced[k]:
        # voicing runs through the closure (voice bar / voiced stop): VOT is negative
        rise = np.where((t > tc) & (e >= e[ci] + 12))[0]
        if len(rise) == 0:
            return None
        burst = t[rise[0]]
        j = k
        while j > 0 and voiced[j - 1] and pt[j - 1] >= lo:
            j -= 1
        onset = pt[j]
        vot = max((onset - burst) * 1000, -100.0)  # capped: voicing carried over from the previous vowel
    else:
        onset = None
        for j in range(k, len(pt) - 4):
            if pt[j] > hi:
                break
            if voiced[j:j + 4].all():  # first run of >= 4 voiced frames (8 ms) after the closure
                onset = pt[j]
                break
        if onset is None:
            return None
        rise = np.where((t > tc) & (t <= onset) & (e >= e[ci] + 15))[0]
        if len(rise):
            burst = t[rise[0]]
        else:  # no 15 dB jump (weak burst, seen by eye on 태즈메이니아): use the steepest 2 ms rise instead
            w = np.where((t > tc) & (t <= onset))[0]
            if len(w) < 3:
                burst = onset
            else:
                d = e[w[2:]] - e[w[:-2]]
                burst = t[w[int(np.argmax(d)) + 1]]
        vot = (onset - burst) * 1000
    after = max(onset, burst)
    vf = f0[(pt >= after) & (pt <= after + 0.05) & voiced]
    return dict(burst=round(burst, 4), onset=round(onset, 4), vot=round(vot, 1),
                f0=round(float(np.median(vf)), 1) if len(vf) else "")


EMPTY = dict(burst="", onset="", vot="", f0="")  # a stop we tried but couldn't measure (kept, so we can count drops)


def measure(limit):
    al = Aligner()
    out = []
    # English
    g2p_en = G2pEn()
    for spk in CMU_SPEAKERS:
        lines = (CMU / f"cmu_us_{spk}_arctic/etc/txt.done.data").read_text().splitlines()
        items = [re.match(r'\( (\S+) "(.*)" \)', l).groups() for l in lines if l.strip()]
        items = items[:limit or EN_PER_SPEAKER]
        for n, (utt, text) in enumerate(items, 1):
            audio, sr = sf.read(CMU / f"cmu_us_{spk}_arctic/wav/{utt}.wav", dtype="float32")
            phones, targets = english_targets(text, g2p_en)
            if not targets:
                continue
            st = al.starts(audio, phones)
            pitch = parselmouth.Sound(audio, 16000).to_pitch(time_step=0.002, pitch_floor=75, pitch_ceiling=500)
            for pi, cat, place, word in targets:
                m = measure_vot(audio, pitch, st[pi], st[pi + 1]) or EMPTY
                if True:
                    out.append(dict(lang="en", speaker=spk, utt=utt, word=word, cat=cat, place=place,
                                    initial="", t_stop=round(st[pi], 3), **m))
        print(f"  English {spk}: {len(items)} recordings, {sum(r['speaker'] == spk for r in out)} stops")
    # Korean
    g2p_ko = G2pKo()
    for path, per_spk in ZEROTH:
        rows, seen = [], defaultdict(int)
        for r in pq.read_table(path).to_pylist():
            seen[r["speaker_id"]] += 1
            if not per_spk or seen[r["speaker_id"]] <= per_spk:
                rows.append(r)
        rows = rows[:limit] if limit else rows
        for n, r in enumerate(rows, 1):
            audio, _ = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
            phones, targets = korean_targets(r["text"], g2p_ko)
            if not targets:
                continue
            st = al.starts(audio, phones)
            pitch = parselmouth.Sound(audio, 16000).to_pitch(time_step=0.002, pitch_floor=75, pitch_ceiling=500)
            for pi, cat, place, word, initial in targets:
                m = measure_vot(audio, pitch, st[pi], st[pi + 1]) or EMPTY
                if True:
                    out.append(dict(lang="ko", speaker=f"z{r['speaker_id']}", utt=r["id"], word=word, cat=cat,
                                    place=place, initial=int(initial), t_stop=round(st[pi], 3), **m))
            if n % 200 == 0 or n == len(rows):
                print(f"  Korean {path.name}: {n}/{len(rows)} recordings, "
                      f"{sum(o['lang'] == 'ko' for o in out)} stops so far")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader(); w.writerows(out)
    print(f"wrote {CACHE} ({len(out)} stops)")


# ---------- analysis ----------
def loso(rows, a, b, feats):
    """Leave-one-speaker-out balanced accuracy for category a vs b. feats = ['vot'] or ['vot', 'f0st'].
    1 feature: best cut-off on the training speakers. 2 features: nearest centroid on z-scored features."""
    speakers = sorted({r["speaker"] for r in rows})
    accs = []
    for held in speakers:
        tr = [r for r in rows if r["speaker"] != held and r["cat"] in (a, b)]
        te = [r for r in rows if r["speaker"] == held and r["cat"] in (a, b)]
        if not all(any(r["cat"] == c for r in tr) for c in (a, b)) or \
           not all(any(r["cat"] == c for r in te) for c in (a, b)):
            continue
        X = lambda rs: np.array([[r[f] for f in feats] for r in rs], dtype=float)
        mu, sd = X(tr).mean(0), X(tr).std(0) + 1e-9
        cen = {c: ((X([r for r in tr if r["cat"] == c]) - mu) / sd).mean(0) for c in (a, b)}
        acc = []
        for c in (a, b):
            Z = (X([r for r in te if r["cat"] == c]) - mu) / sd
            o = b if c == a else a
            acc.append(np.mean(np.linalg.norm(Z - cen[c], axis=1) < np.linalg.norm(Z - cen[o], axis=1)))
        accs.append(np.mean(acc))
    return accs


def summarize(rows, label):
    print(f"\n{label}")
    print(f"  {'category':<12}{'n':>6}{'median VOT ms':>15}{'25-75%':>14}{'prevoiced':>11}{'F0 st':>8}")
    for c in ("vcd", "vcd_unstr", "sp", "asp", "asp_unstr", "tense", "lenis"):
        g = [r for r in rows if r["cat"] == c]
        if not g:
            continue
        v = np.array([r["vot"] for r in g])
        f = [r["f0st"] for r in g if r["f0st"] is not None]
        print(f"  {c:<12}{len(g):>6}{np.median(v):>15.0f}{np.percentile(v, 25):>8.0f}-{np.percentile(v, 75):<5.0f}"
              f"{np.mean(v < 0):>11.0%}{(np.median(f) if f else float('nan')):>8.1f}")


def analyse():
    allrows = list(csv.DictReader(open(CACHE)))
    rows = [r for r in allrows if r["vot"] != ""]
    print(f"{len(allrows)} stops found, {len(allrows) - len(rows)} could not be measured "
          f"({(len(allrows) - len(rows)) / len(allrows):.0%}); by category:",
          {c: f"{sum(r['vot'] == '' for r in allrows if r['cat'] == c)}/{sum(r['cat'] == c for r in allrows)}"
           for c in sorted({r['cat'] for r in allrows})})
    for r in rows:
        r["vot"] = float(r["vot"])
        r["f0"] = float(r["f0"]) if r["f0"] else None
    # F0 in semitones relative to each speaker's median early-vowel F0 (so men/women are comparable)
    med = {s: np.median([r["f0"] for r in rows if r["speaker"] == s and r["f0"]]) for s in {r["speaker"] for r in rows}}
    for r in rows:
        r["f0st"] = 12 * np.log2(r["f0"] / med[r["speaker"]]) if r["f0"] else None
    en = [r for r in rows if r["lang"] == "en"]
    ko = [r for r in rows if r["lang"] == "ko"]
    ko_init = [r for r in ko if r["initial"] == "1"]
    ko_med = [r for r in ko if r["initial"] == "0"]
    summarize(en, f"ENGLISH (CMU ARCTIC, {len({r['speaker'] for r in en})} speakers), word-initial stops")
    summarize(ko_init, f"KOREAN, utterance-initial (first word of the recording; {len({r['speaker'] for r in ko_init})} speakers)")
    summarize(ko_med, "KOREAN, word-initial inside the sentence")

    def report(rs, a, b, feats, note, bar=None):
        rs = [r for r in rs if all(r[f] is not None for f in feats)]
        n = {c: sum(r["cat"] == c for r in rs) for c in (a, b)}
        accs = loso(rs, a, b, feats)
        if not accs or min(n.values()) < 20:
            print(f"  {a} vs {b} [{'+'.join(feats)}]: too few (n {n[a]}/{n[b]}, speakers {len(accs)})  <- {note}")
            return
        verdict = "" if bar is None else ("  PASS" if np.mean(accs) >= bar else "  FAIL") + f" (bar {bar:.0%})"
        print(f"  {a} vs {b} [{'+'.join(feats)}]: {np.mean(accs):.1%} (speakers {min(accs):.0%}-{max(accs):.0%}, "
              f"n {n[a]}/{n[b]}, {len(accs)} speakers){verdict}  <- {note}")

    print("\nLeave-one-speaker-out balanced accuracy (50% = chance)")
    lab = lambda rs: [r for r in rs if r["place"] == "lab"]
    report(en, "asp", "vcd", ["vot"], "SANITY: English p/t/k vs b/d/g (stressed)", 0.90)
    report(lab(en), "asp", "vcd", ["vot"], "English pin vs bin (p vs b only)", 0.90)
    report(en, "asp", "sp", ["vot"], "English pin vs spin: s-p should be unaspirated")
    report(en, "vcd", "sp", ["vot"], "English bin vs spin: expected to be close")
    for name, rs in (("utterance-initial", ko_init), ("inside the sentence", ko_med)):
        bars = (0.90, 0.80, 0.80) if rs is ko_init else (None, None, None)
        print(f" Korean, {name}:")
        report(rs, "tense", "asp", ["vot"], "ㅃ vs ㅍ (all places pooled)", bars[0])
        report(rs, "lenis", "asp", ["vot"], "ㅂ vs ㅍ, VOT only (expected to overlap for young Seoul speakers)")
        report(rs, "lenis", "asp", ["vot", "f0st"], "ㅂ vs ㅍ, VOT + pitch", bars[1])
        report(rs, "tense", "lenis", ["vot", "f0st"], "ㅃ vs ㅂ, VOT + pitch", bars[2])
        report(lab(rs), "lenis", "asp", ["vot", "f0st"], "lips only: ㅂ vs ㅍ, VOT + pitch")
    return en, ko_init, ko_med


def plot(en, ko_init, ko_med):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["AppleGothic", "DejaVu Sans"]
    col = {"vcd": "#4269d0", "sp": "#6cc5b0", "asp": "#ff725c", "asp_unstr": "#ffb3a7",
           "tense": "#3ca951", "lenis": "#a463f2"}
    name = {"vcd": "b/d/g (bin)", "sp": "s+p/t/k (spin)", "asp": "p/t/k stressed (pin)",
            "asp_unstr": "p/t/k unstressed", "tense": "tense ㅃㄸㄲ", "lenis": "lenis ㅂㄷㄱ", }
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.5))
    bins = np.arange(-120, 161, 5)
    for c in ("vcd", "sp", "asp"):
        axes[0].hist([r["vot"] for r in en if r["cat"] == c], bins=bins, alpha=0.55, color=col[c],
                     label=f"{name[c]} (n={sum(r['cat'] == c for r in en)})", density=True)
    axes[0].set_title("English (native, CMU ARCTIC): VOT of word-initial stops")
    name["asp"] = "aspirated ㅍㅌㅋ"
    for c in ("tense", "lenis", "asp"):
        axes[1].hist([r["vot"] for r in ko_med if r["cat"] == c], bins=bins, alpha=0.55, color=col[c],
                     label=f"{name[c]} (n={sum(r['cat'] == c for r in ko_med)})", density=True)
    axes[1].set_title("Korean (native, Zeroth): VOT, word-initial inside the sentence")
    for ax in axes[:2]:
        ax.set_xlabel("VOT (ms)   negative = voicing before the release"); ax.legend(); ax.grid(alpha=0.3)
    for c in ("tense", "lenis", "asp"):
        g = [r for r in ko_init if r["cat"] == c and r["f0st"] is not None]
        axes[2].scatter([r["vot"] for r in g], [r["f0st"] for r in g], s=10, alpha=0.6, color=col[c],
                        label=f"{name[c]} (n={len(g)})")
    axes[2].set_title("Korean, utterance-initial: VOT vs pitch of the next vowel")
    axes[2].set_xlabel("VOT (ms)"); axes[2].set_ylabel("F0 (semitones vs speaker median)")
    axes[2].legend(); axes[2].grid(alpha=0.3)
    fig.suptitle("Spike (b): voice onset time, estimated from audio (automatic burst + voicing detection)")
    fig.tight_layout()
    PLOT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLOT, dpi=130)
    print(f"\nsaved {PLOT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="quick check: N recordings per speaker/file")
    ap.add_argument("--plot-only", action="store_true")
    args = ap.parse_args()
    if not args.plot_only:
        measure(args.limit)
    plot(*analyse())
