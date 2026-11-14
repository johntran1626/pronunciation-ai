"""Spike (c): does the phoneme recognizer tell R from L in non-native English?

For every English R and L consonant in the annotated L2-ARCTIC utterances:
  1. take the human-marked time window for that sound (oracle timing, so this tests
     the RECOGNIZER only, not our aligner; the real app will be a bit worse)
  2. inside that window, how strongly does the model hear "R-ish" vs "L-ish"?
  3. flag the sound as wrong if the OTHER sound wins by more than a margin
  4. compare with the human label: correct, or swapped (R said as L / L said as R)

Run:  python spikes/c_rl.py                 (the 4 Korean speakers in data/l2arctic, a few min on CPU)
      python spikes/c_rl.py --limit 5       (quick smoke test)
      python spikes/c_rl.py --others        (the 20 NON-Korean speakers, read straight from the
                                             full download zip; nothing is extracted; ~20-30 min)
Every scored sound is also saved to data/cache/spike_c_<group>.csv (git-ignored), so
margins can be re-tuned later without re-running the model.
Throwaway feasibility code. Not part of the app.
"""
import csv
import io
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import soundfile as sf
import torch
import torchaudio.functional as F
from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

from d_align import DATA, MODEL, _vocab_list

KOREAN = ["HJK", "HKK", "YDCK", "YKWK"]
FULL_ZIP = Path.home() / "Downloads" / "l2arctic_release_v5.0.zip"
CACHE = Path("data/cache")
# Model tokens counted as "R-ish" / "L-ish". The tap ɾ (Korean ㄹ between vowels) is in NEITHER:
# it is the in-between sound, so we keep it out of both and report it separately.
R_TOKENS = {"ɹ", "ɚ", "ɻ", "ɑːɹ", "ɔːɹ", "oːɹ", "ɛɹ", "ɪɹ", "ʊɹ", "aɪɚ"}
L_TOKENS = {"l", "əl", "ɫ", "l̩", "lː", "ɭ", "ɭʲ"}
MARGINS = [-0.5, -0.25, 0.0, 0.25, 0.5]  # flag if score(other) - score(target) > margin
PAD = 0.02  # seconds added on each side of the human window (one model frame)

# Annotation spellings -> R / L (labels mix ARPAbet, IPA and case)
NORM = {"r": "R", "ɹ": "R", "l": "L"}


def tier(textgrid_text, name):
    """[(start, end, label), ...] for one tier, skipping empty/silence. Use 'phones', NOT 'ISU'
    (some files have an extra ISU tier that repeats the labels)."""
    part = textgrid_text.split(f'name = "{name}"')[1].split("item [")[0]
    rows = re.findall(r'xmin = ([\d.]+)\s*xmax = ([\d.]+)\s*text = "([^"]*)"', part)
    return [(float(a), float(b), lab.strip()) for a, b, lab in rows if lab.strip() not in ("", "sil", "sp")]


def classify(label):
    """'L' -> ('L', 'correct'); 'L,R,s' -> ('L', 'swap'); 'R,sil,d' -> ('R', 'deleted'); else other."""
    parts = [p.strip() for p in label.split(",")]
    target = NORM.get(parts[0].lower())
    if target is None:
        return None, None
    if len(parts) == 1:
        return target, "correct"
    perceived = parts[1].lower()
    if perceived == "sil":
        return target, "deleted"
    if NORM.get(perceived) not in (None, target):
        return target, "swap"
    return target, "other:" + parts[1]  # tap ɾ, schwa, accented R*, 'err' (hard to judge)


def utterances_from_folder(speakers, limit):
    """Yield (speaker, utt, textgrid_text, wav_file) from the extracted Korean data."""
    for spk in speakers:
        grids = sorted((DATA / spk / "annotation").glob("*.TextGrid"))[:limit]
        print(f"{spk}: {len(grids)} utterances", flush=True)
        for g in grids:
            yield spk, g.stem, g.read_text(encoding="utf-8", errors="replace"), DATA / spk / "wav" / f"{g.stem}.wav"


def utterances_from_zip(limit):
    """Yield the same for the 20 non-Korean speakers, reading the nested zips in memory."""
    outer = zipfile.ZipFile(FULL_ZIP)
    names = sorted(n for n in outer.namelist() if re.fullmatch(r"[A-Z]+\.zip", n))
    for name in names:
        spk = name[:-4]
        if spk in KOREAN or name == "suitcase_corpus.zip":
            continue
        inner = zipfile.ZipFile(io.BytesIO(outer.read(name)))
        grids = sorted(m for m in inner.namelist() if "/annotation/" in m and m.endswith(".TextGrid"))[:limit]
        print(f"{spk}: {len(grids)} utterances", flush=True)
        for g in grids:
            utt = Path(g).stem
            wav = g.replace("/annotation/", "/wav/").replace(".TextGrid", ".wav")
            yield spk, utt, inner.read(g).decode("utf-8", "replace"), io.BytesIO(inner.read(wav))


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    group = "others" if "--others" in sys.argv else "korean"
    source = utterances_from_zip(limit) if group == "others" else utterances_from_folder(KOREAN, limit)

    print(f"Loading {MODEL}...")
    extractor = Wav2Vec2FeatureExtractor.from_pretrained(MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    vocab = _vocab_list(model)
    r_ids = [i for i, t in enumerate(vocab) if t in R_TOKENS]
    l_ids = [i for i, t in enumerate(vocab) if t in L_TOKENS]

    cases = []  # (speaker, utt, word, target, kind, start, end, score_target, score_other)
    skipped = Counter()
    for speaker, utt, grid_text, wav in source:
        targets = [(st, en, *classify(lab)) for st, en, lab in tier(grid_text, "phones")]
        targets = [t for t in targets if t[2] is not None]
        if not targets:
            continue
        words = tier(grid_text, "words")

        audio, sr = sf.read(wav, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(1)
        audio16 = F.resample(torch.from_numpy(audio), sr, 16000)
        inputs = extractor(audio16.numpy(), sampling_rate=16000, return_tensors="pt")
        with torch.inference_mode():
            probs = model(inputs.input_values).logits.softmax(-1)[0]  # (frames, vocab)
        sec_per_frame = len(audio16) / 16000 / probs.shape[0]
        r_prob = probs[:, r_ids].sum(-1)  # per frame: total chance of any R-ish token
        l_prob = probs[:, l_ids].sum(-1)

        for st, en, target, kind in targets:
            if kind == "deleted":
                skipped["deleted (no sound to score)"] += 1
                continue
            a = max(0, int((st - PAD) / sec_per_frame))
            b = min(probs.shape[0], int((en + PAD) / sec_per_frame) + 1)
            # CTC is peaky (one spike per sound), so take the PEAK in the window, not the mean
            score_r, score_l = r_prob[a:b].max().item(), l_prob[a:b].max().item()
            s_t, s_o = (score_r, score_l) if target == "R" else (score_l, score_r)
            mid = (st + en) / 2
            word = next((w for ws, we, w in words if ws <= mid <= we), "?")
            cases.append((speaker, utt, word, target, kind, st, en, s_t, s_o))

    if limit is None:
        CACHE.mkdir(parents=True, exist_ok=True)
        out = CACHE / f"spike_c_{group}.csv"
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["speaker", "utt", "word", "target", "kind", "start", "end", "score_target", "score_other"])
            w.writerows(cases)
        print(f"Saved {len(cases)} rows to {out}")
    report(cases, skipped)


def report(cases, skipped):
    print(f"\nScored {len(cases)} R/L sounds. Skipped: {dict(skipped)}")
    kinds = Counter((c[3], c[4] if not c[4].startswith("other") else "other") for c in cases)
    print("Human labels:", {f"{t} {k}": n for (t, k), n in sorted(kinds.items())})

    print("\nDetection = share of real swaps flagged.  False alarm = share of CORRECT sounds flagged.")
    print(f"{'target':<7} {'margin':>6} {'detected':>13} {'false alarms':>17}")
    for target in ("R", "L"):
        swaps = [c for c in cases if c[3] == target and c[4] == "swap"]
        good = [c for c in cases if c[3] == target and c[4] == "correct"]
        for m in MARGINS:
            d = sum(c[-1] - c[-2] > m for c in swaps)
            fa = sum(c[-1] - c[-2] > m for c in good)
            print(f"{target:<7} {m:>6.2f} {d:>4}/{len(swaps):<4} {d / max(1, len(swaps)):>4.0%}"
                  f" {fa:>5}/{len(good):<5} {fa / max(1, len(good)):>5.1%}")

    others = [c for c in cases if c[4].startswith("other")]
    print(f"\n'Other' labels (tap, schwa, accented, err): {len(others)}; "
          f"flagged at margin 0: {sum(c[-1] - c[-2] > 0 for c in others)}")

    fa_words = defaultdict(int)
    for c in cases:
        if c[4] == "correct" and c[-1] - c[-2] > 0:
            fa_words[f"{c[3]} in '{c[2]}'"] += 1
    print("Most common false alarms at margin 0:", sorted(fa_words.items(), key=lambda kv: -kv[1])[:10])


if __name__ == "__main__":
    sys.exit(main())
