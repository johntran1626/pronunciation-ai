"""Spike (a): do native Korean ㅓ and ㅗ separate on an F1/F2 chart?

For each Zeroth-Korean test recording (10 native speakers):
  1. text -> pronounced form (g2pk) -> IPA phones (our jamo table below)
  2. audio -> wav2vec2 phoneme model -> forced alignment -> a time window per phone
  3. for each plain vowel (ㅏ ㅓ ㅗ ㅜ ㅡ ㅣ ㅐ ㅔ): F1 and F2 in the middle of its window (parselmouth)
  4. normalize per speaker (Lobanov z-scores), so a high-voiced and a low-voiced speaker are comparable
  5. plot, and test: train on 9 speakers, classify the 10th speaker's ㅓ/ㅗ (leave-one-speaker-out)

Run:  python spikes/a_vowels.py             (test split, model's symbols, measured at the blip)
      python spikes/a_vowels.py --parquet data/zeroth/data/train-00000-of-00006.parquet --per-speaker 60
                                            (confirmation run on 16 unseen speakers)
      python spikes/a_vowels.py --symbols espeak   (run 1: textbook IPA symbols for alignment)
      python spikes/a_vowels.py --limit 5   (quick check)
      python spikes/a_vowels.py --plot-only (re-analyse data/cache/spike_a_vowels.csv)
Throwaway feasibility code. Not part of the app; the production formant code is backend/acoustics.py.
"""
import argparse
import csv
import io
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import parselmouth
import pyarrow.parquet as pq
import soundfile as sf
import torch
import torchaudio.functional as F
from g2pk import G2p
from huggingface_hub import hf_hub_download
from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

MODEL = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
PARQUET = Path("data/zeroth/data/test-00000-of-00001.parquet")  # default; --parquet picks another file
CACHE = Path("data/cache/spike_a_vowels.csv")
PLOT = Path("spikes/out/a_vowels.png")
MAX_VOWEL = 0.35  # s; a vowel window can't run longer than this (stops a pause being glued on)
MIN_VOWEL = 0.04  # s; shorter windows are too short to measure formants reliably

# Hangul syllable = onset (19) x vowel (21) x coda (28). Index tables in Unicode order.
# Tense ㄲ ㄸ ㅃ ㅆ ㅉ map to plain: the model has no tense symbols.
# The aligner only needs to find where each sound is, so this is fine for vowels.
ONSET = ["k", "k", "n", "t", "t", "ɾ", "m", "p", "p", "s", "s", None, "tɕ", "tɕ", "tɕh", "kʰ", "tʰ", "pʰ", "h"]
VOWEL = [("ㅏ", ["a"]), ("ㅐ", ["ɛ"]), ("ㅑ", ["j", "a"]), ("ㅒ", ["j", "ɛ"]), ("ㅓ", ["ʌ"]), ("ㅔ", ["e"]),
         ("ㅕ", ["j", "ʌ"]), ("ㅖ", ["j", "e"]), ("ㅗ", ["o"]), ("ㅘ", ["w", "a"]), ("ㅙ", ["w", "ɛ"]),
         ("ㅚ", ["w", "e"]), ("ㅛ", ["j", "o"]), ("ㅜ", ["u"]), ("ㅝ", ["w", "ʌ"]), ("ㅞ", ["w", "e"]),
         ("ㅟ", ["w", "i"]), ("ㅠ", ["j", "u"]), ("ㅡ", ["ɯ"]), ("ㅢ", ["ɯ", "i"]), ("ㅣ", ["i"])]
# Codas are pronounced as one of 7 sounds (g2pk mostly outputs those already).
CODA = [None, "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l",
        "m", "p", "p", "t", "t", "ŋ", "t", "t", "k", "t", "p", "t"]
PLAIN = ["ㅏ", "ㅓ", "ㅗ", "ㅜ", "ㅡ", "ㅣ", "ㅐ", "ㅔ"]  # the vowels we measure (no glides)
IPA = {"ㅏ": "a", "ㅓ": "ʌ", "ㅗ": "o", "ㅜ": "u", "ㅡ": "ɯ", "ㅣ": "i", "ㅐ": "ɛ", "ㅔ": "e"}
# Run 2: the model writes Korean with its own (mostly non-Korean) symbols. Measured on 153 Zeroth
# recordings (greedy decode vs expected, run 1): ㅓ is heard as ɔ 28% / ʌ ~0%, ㅡ as ə 21%,
# ㅈ as dʒ 25%, ㅊ as tʃ 34%, ㄹ as r 31%, ㅐ as e 33%, and aspirated ㅋㅌㅍ as plain k t p 60%+.
# Forcing symbols the model never uses gives bad windows. For ALIGNMENT ONLY, use the model's own symbol.
# (Formants are still measured from the audio, so ㅐ and ㅔ both aligning as 'e' doesn't merge them.)
HEARD_AS = {"ʌ": "ɔ", "ɯ": "ə", "tɕ": "dʒ", "tɕh": "tʃ", "ɾ": "r", "ɛ": "e", "kʰ": "k", "tʰ": "t", "pʰ": "p"}
PAIRS = [("ㅏ", "ㅣ", "sanity check: should be ~100%"),
         ("ㅓ", "ㅗ", "THE SPIKE QUESTION"),
         ("ㅗ", "ㅜ", "known to be close for some Seoul speakers"),
         ("ㅐ", "ㅔ", "many Seoul speakers merge these: expect ~50%")]


def to_phones(pron):
    """'몯 빧꼬' -> (['m','o','t','p','a','t','k','o'], [None,'ㅗ',None,...]): IPA phones + which are plain vowels."""
    phones, labels, prev_coda = [], [], None
    for ch in pron:
        o = ord(ch) - 0xAC00
        if not 0 <= o < 11172:
            continue  # spaces; keep prev_coda so ㄹ+ㄹ across a word gap still gives [l l]
        onset, (name, vowels), coda = ONSET[o // 588], VOWEL[(o % 588) // 28], CODA[o % 28]
        if onset == "ɾ" and prev_coda == "l":
            onset = "l"  # ㄹㄹ is [ll], not a tap
        if onset:
            phones.append(onset); labels.append(None)
        for v in vowels:
            phones.append(v); labels.append(name if name in PLAIN else None)
        if coda:
            phones.append(coda); labels.append(None)
        prev_coda = coda
    return phones, labels


def measure(limit, symbols, parquet, at, per_speaker, tag):
    rows = pq.read_table(parquet).to_pylist()
    if per_speaker:  # first N recordings per speaker, in file order (so big speakers don't dominate run time)
        seen = defaultdict(int)
        rows = [r for r in rows if (seen.__setitem__(r["speaker_id"], seen[r["speaker_id"]] + 1) or True)
                and seen[r["speaker_id"]] <= per_speaker]
    if limit:
        rows = rows[:limit]
    print(f"{len(rows)} recordings from {parquet}")
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Loading {MODEL} on {device}...")
    extractor = Wav2Vec2FeatureExtractor.from_pretrained(MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval().to(device)
    vocab = json.load(open(hf_hub_download(MODEL, "vocab.json")))
    blank = model.config.pad_token_id
    g2p = G2p()

    # Formant ceiling per speaker: 5000 Hz for low voices, 5500 Hz for high voices (standard Praat advice).
    # Zeroth has no gender column, so we decide from each speaker's median pitch.
    audio_of, pitch_of = {}, defaultdict(list)
    for r in rows:
        audio, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
        assert sr == 16000
        audio_of[r["id"]] = audio
        f0 = parselmouth.Sound(audio, 16000).to_pitch().selected_array["frequency"]
        pitch_of[r["speaker_id"]] += list(f0[f0 > 0])
    ceiling = {s: (5500 if np.median(f) >= 165 else 5000) for s, f in pitch_of.items()}
    for s in sorted(ceiling):
        print(f"speaker {s}: median pitch {np.median(pitch_of[s]):.0f} Hz -> formant ceiling {ceiling[s]} Hz")

    out = []
    for n, r in enumerate(rows, 1):
        audio, spk = audio_of[r["id"]], r["speaker_id"]
        phones, labels = to_phones(g2p(r["text"]))
        if symbols == "heard":
            phones = [HEARD_AS.get(p, p) for p in phones]
        inputs = extractor(audio, sampling_rate=16000, return_tensors="pt")
        with torch.inference_mode():
            log_probs = model(inputs.input_values.to(device)).logits.log_softmax(-1).cpu()
        sec_per_frame = len(audio) / 16000 / log_probs.shape[1]
        targets = torch.tensor([[vocab[p] for p in phones]], dtype=torch.int32)
        frame_labels, frame_scores = F.forced_align(log_probs, targets, blank=blank)
        spans = F.merge_tokens(frame_labels[0], frame_scores[0].exp())
        starts = [s.start * sec_per_frame for s in spans]
        nexts = starts[1:] + [len(audio) / 16000]

        formant = parselmouth.Sound(audio, 16000).to_formant_burg(
            time_step=0.005, max_number_of_formants=5, maximum_formant=ceiling[spk])
        for lab, span, st, nx in zip(labels, spans, starts, nexts):
            if lab is None:
                continue
            en = min(nx, st + MAX_VOWEL)
            if en - st < MIN_VOWEL:
                continue
            # median over the middle 40% of the window (edges are pulled by neighbouring consonants)
            if at == "blip":  # where the model fires: the first 20 ms (spikes/a_window_test.py)
                ts = np.linspace(st, st + 0.02, 5)
            else:  # "middle": middle 40% of blip -> next phone (runs 1-2)
                ts = np.linspace(st + 0.3 * (en - st), st + 0.7 * (en - st), 7)
            f1 = np.nanmedian([formant.get_value_at_time(1, t) for t in ts])
            f2 = np.nanmedian([formant.get_value_at_time(2, t) for t in ts])
            if np.isnan(f1) or np.isnan(f2):
                continue
            out.append(dict(utt=r["id"], speaker=spk, vowel=lab, start=round(st, 3), end=round(en, 3),
                            conf=round(span.score, 3), f1=round(f1), f2=round(f2), ceiling=ceiling[spk]))
        if n % 50 == 0 or n == len(rows):
            print(f"  {n}/{len(rows)} recordings, {len(out)} vowels so far")

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path(tag), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader(); w.writerows(out)
    print(f"wrote {cache_path(tag)} ({len(out)} vowels)")


def cache_path(tag):
    return CACHE.with_name(f"{CACHE.stem}_{tag}.csv")


def analyse(tag):
    rows = list(csv.DictReader(open(cache_path(tag))))
    for r in rows:
        r["f1"], r["f2"] = float(r["f1"]), float(r["f2"])

    # Lobanov: per speaker, z = (value - speaker mean) / speaker SD, for F1 and F2 separately
    by_spk = defaultdict(list)
    for r in rows:
        by_spk[r["speaker"]].append(r)
    for spk_rows in by_spk.values():
        for k in ("f1", "f2"):
            v = np.array([r[k] for r in spk_rows])
            for r in spk_rows:
                r["z" + k] = (r[k] - v.mean()) / v.std()
    kept = [r for r in rows if abs(r["zf1"]) <= 3 and abs(r["zf2"]) <= 3]  # drop formant-tracking blunders
    print(f"\n{len(rows)} vowels measured, {len(rows) - len(kept)} dropped as outliers (|z| > 3), {len(kept)} kept")

    print(f"\n{'vowel':<6}{'n':>6}{'F1 Hz':>8}{'F2 Hz':>8}   (raw means: low-voice speakers / high-voice speakers)")
    for v in PLAIN:
        line = f"{v} {IPA[v]:<3}{sum(r['vowel'] == v for r in kept):>6}"
        for c in ("5000", "5500"):
            g = [r for r in kept if r["vowel"] == v and r["ceiling"] == c]
            line += f"  {np.mean([r['f1'] for r in g]):5.0f} {np.mean([r['f2'] for r in g]):5.0f}" if g else "    -     -"
        print(line)

    # Leave-one-speaker-out: centroids from 9 speakers, classify the 10th speaker's tokens
    speakers = sorted(by_spk)
    print("\nLeave-one-speaker-out accuracy (nearest centroid in normalized F1/F2; balanced, so 50% = chance)")
    results = {}
    for a, b, note in PAIRS:
        per_spk = []
        for held in speakers:
            train = [r for r in kept if r["speaker"] != held and r["vowel"] in (a, b)]
            test = [r for r in kept if r["speaker"] == held and r["vowel"] in (a, b)]
            if not all(any(r["vowel"] == v for r in train) for v in (a, b)):
                continue  # not enough other speakers yet (e.g. a --limit run)
            cen = {v: np.mean([[r["zf1"], r["zf2"]] for r in train if r["vowel"] == v], axis=0) for v in (a, b)}
            accs = []
            for v in (a, b):
                t = [r for r in test if r["vowel"] == v]
                if t:
                    pts = np.array([[r["zf1"], r["zf2"]] for r in t])
                    d = {u: np.linalg.norm(pts - cen[u], axis=1) for u in (a, b)}
                    other = b if v == a else a
                    accs.append(np.mean(d[v] < d[other]))
            if len(accs) == 2:
                per_spk.append(np.mean(accs))
        results[(a, b)] = per_spk
        if not per_spk:
            print(f"  {a} vs {b}: needs at least 2 speakers")
            continue
        print(f"  {a} vs {b}: mean {np.mean(per_spk):.1%}, speakers {min(per_spk):.0%}-{max(per_spk):.0%} "
              f"(n speakers {len(per_spk)})  <- {note}")
    return kept, results


def plot(kept, results, tag):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["AppleGothic", "DejaVu Sans"]  # AppleGothic has Hangul on macOS
    colors = dict(zip(PLAIN, ["#4269d0", "#efb118", "#ff725c", "#6cc5b0", "#3ca951", "#ff8ab7", "#a463f2", "#97bbf5"]))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
    for v in PLAIN:
        g = [r for r in kept if r["vowel"] == v]
        x, y = [r["zf2"] for r in g], [r["zf1"] for r in g]
        ax1.scatter(x, y, s=4, alpha=0.15, color=colors[v])
        ax1.text(np.mean(x), np.mean(y), f"{v} {IPA[v]}", fontsize=15, ha="center", va="center",
                 color=colors[v], bbox=dict(facecolor="white", edgecolor=colors[v], alpha=0.85, boxstyle="round"))
    n_spk = len({r["speaker"] for r in kept})
    ax1.set_title(f"All {n_spk} speakers: every vowel token (dots) and each vowel's average (label)")
    # Per speaker: line from that speaker's ㅓ average to their ㅗ average
    for spk in sorted({r["speaker"] for r in kept}):
        m = {}
        for v in ("ㅓ", "ㅗ"):
            g = [r for r in kept if r["speaker"] == spk and r["vowel"] == v]
            m[v] = (np.mean([r["zf2"] for r in g]), np.mean([r["zf1"] for r in g]))
        ax2.plot([m["ㅓ"][0], m["ㅗ"][0]], [m["ㅓ"][1], m["ㅗ"][1]], color="#999", lw=1)
        for v in ("ㅓ", "ㅗ"):
            ax2.scatter(*m[v], color=colors[v], s=40, zorder=3)
        ax2.annotate(spk, m["ㅓ"], fontsize=7, color="#666", xytext=(3, 3), textcoords="offset points")
    acc = results[("ㅓ", "ㅗ")]
    acc = f"{np.mean(acc):.0%}" if acc else "n/a"
    ax2.set_title(f"Each speaker's ㅓ (orange) and ㅗ (red) average\nleave-one-speaker-out accuracy {acc}")
    ax2.scatter([], [], color=colors["ㅓ"], label="ㅓ ʌ"); ax2.scatter([], [], color=colors["ㅗ"], label="ㅗ o")
    ax2.legend()
    for ax in (ax1, ax2):
        ax.invert_xaxis(); ax.invert_yaxis()  # phonetics convention: front vowels left, high vowels top
        ax.set_xlabel("F2, normalized (left = tongue more front)")
        ax.set_ylabel("F1, normalized (top = tongue higher)")
        ax.grid(alpha=0.3)
    split = "test split" if tag.startswith("test") else "train split, unseen speakers"
    where = "at the model's spike" if tag.endswith("blip") else "in the middle of the vowel window"
    fig.suptitle(f"Native Korean vowels, Zeroth-Korean {split}, measured {where} (formants estimated from audio)")
    fig.tight_layout()
    PLOT.parent.mkdir(parents=True, exist_ok=True)
    out = PLOT.with_name(f"{PLOT.stem}_{tag}.png")
    fig.savefig(out, dpi=130)
    print(f"\nsaved {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only the first N recordings (0 = all)")
    ap.add_argument("--plot-only", action="store_true", help="skip measuring; re-analyse the cached CSV")
    ap.add_argument("--symbols", choices=["heard", "espeak"], default="heard",
                    help="alignment symbols: 'heard' = the model's own symbols (run 2), 'espeak' = textbook IPA (run 1)")
    ap.add_argument("--parquet", type=Path, default=PARQUET, help="which Zeroth parquet file")
    ap.add_argument("--at", choices=["blip", "middle"], default="blip",
                    help="where to measure in each vowel: 'blip' = where the model fires (default), 'middle' = runs 1-2")
    ap.add_argument("--per-speaker", type=int, default=0, help="only the first N recordings per speaker (0 = all)")
    args = ap.parse_args()
    split = args.parquet.stem.split("-")[0] + ("" if args.parquet == PARQUET else args.parquet.stem.split("-")[1])
    tag = f"{split}_{args.symbols}_{args.at}"  # e.g. test_heard_blip, train00000_heard_blip
    if not args.plot_only:
        measure(args.limit, args.symbols, args.parquet, args.at, args.per_speaker, tag)
    plot(*analyse(tag), tag)
