"""Training data for the listener fine-tune: every labelled recording -> (16 kHz audio, the sounds ACTUALLY said).

    python -m eval.ft_data --build            # all corpora -> data/ft/ (audio + manifest.csv + summary.json)
    python -m eval.ft_data --build --limit 20 # quick check: 20 recordings per corpus

The idea: the current listener was trained to write down speech the way a dictionary would. We want it to write
down what a LEARNER actually said. So the training target for "light" said with an R is `ɹ aɪ t`, not `l aɪ t`.

Where "actually said" comes from:
  - L2-ARCTIC + suitcase: the phones tier. "L,R,s" = L said as R -> R; "R,sil,d" = R dropped -> nothing;
    "sil,AH,a" = an extra vowel -> a schwa; a plain "AH0" = said right -> the dictionary sound.
  - speechocean762: experts mark a sound wrong but NOT what was said. So only recordings where every sound was
    said right (3 of 5 experts) are used; the dictionary sounds are then the truth.
  - Speech Accent Archive: a phonetician's narrow IPA transcription of the whole paragraph.
All of them are mapped onto the listener's own symbols (the same ones backend/g2p.py's ARPA2IPA uses).

Who is in which set (decided by SPEAKER, never by recording, so one voice is never on both sides):
  - test  = Korean speakers (L2-ARCTIC HJK HKK YDCK YKWK, SAA Korean). NEVER written to data/ft/ at all (they are the held-out test).
  - dev   = DEV_FRAC of the other speakers. The listener never trains on them. Used to pick the best checkpoint and
            to retune the detectors on the new listener's numbers, which must come from unseen voices.
  - train = everyone else.
"""
import argparse
import csv
import hashlib
import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from backend.align import vocab
from backend.g2p import ARPA2IPA
from eval.saa import MODIFIERS, segments

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "ft"
DEV_FRAC = 0.2       # share of non-Korean speakers held out of training
# L2-ARCTIC dev = one speaker per first language: SKA + MBMPS (what the hash had picked), then the first
# alphabetically for the other three. 5 of 20 = 25%.
L2ARCTIC_DEV = {"SKA": "Arabic", "MBMPS": "Spanish", "BWC": "Mandarin", "ASI": "Hindi", "HQTV": "Vietnamese"}
MAX_SECONDS = 40.0  # longer recordings are skipped (memory; 61 SAA files are over 45 s)
MIN_SECONDS = 0.5
SR = 16000
SPECIAL = {"<pad>", "<s>", "</s>", "<unk>"}


# ---------- 1. ARPAbet labels (L2-ARCTIC, suitcase, speechocean) ----------
def _arpa_sym(tok):
    """'AH0' -> 'ə' · 'AA*' -> 'ɑː' (a distorted AA: closest sound) · 'V8' / 'D_' / 'ER)' -> typos, keep the letters
    · 'ERR' / 'SPN' / 'err' / 'acc' / 'None' -> None (we don't know what was said)."""
    t = tok.strip()
    if t.upper().startswith("AH0") or t.upper() in ("AX", "AX*"):
        return "ə"
    return ARPA2IPA.get(re.sub(r"[^A-Z]", "", t))   # lowercase err/acc/sil and unknown codes -> None


def arpa_actual(labels):
    """L2-ARCTIC-style labels -> the model symbols actually said, or None if any sound is unknown."""
    out = []
    for lab in labels:
        parts = [p.strip() for p in lab.split(",")]
        if len(parts) == 1:
            sym = _arpa_sym(parts[0])
        else:
            perceived = parts[1]
            kind = parts[2].lower() if len(parts) > 2 else "s"
            if kind == "d" or perceived.lower() == "sil":
                continue                                    # dropped sound: nothing was said
            if kind == "a" and re.sub(r"[^A-Z]", "", perceived) in ("AH", "AX"):
                sym = "ə"                                   # an added AH is a schwa
            else:
                sym = _arpa_sym(perceived)
        if sym is None:
            return None
        out.append(sym)
    return out or None


# ---------- 2. Speech Accent Archive narrow IPA ----------
LOOKALIKE = {"ӕ": "æ", "ә": "ə", "ǝ": "ə", "і": "i", "а": "a", "đ": "d", "∫": "ʃ", "ᶴ": "ʃ", "ⅼ": "l", "I": "ɪ",
             "ʀ": "ʁ", "ᵊ": "ə", "g": "ɡ"}  # Cyrillic / look-alike letters some transcribers typed
MARKS = set("ˠˤˈˌ˳ˢǀǂ:") | {"", ""}   # marks (velarized, stress, a private-use glyph...), not sounds
# English sounds written narrowly -> the broad symbol the ARPAbet corpora use for the same English sound
BROAD = {"i": "iː", "u": "uː", "ɑ": "ɑː", "ɒ": "ɑː", "ɔ": "ɔː", "ɝ": "ɚ", "ɫ": "l", "ɭ": "l", "ʎ": "l", "ɻ": "ɹ",
         "ɽ": "ɾ"}
DIPHTHONG = {("a", "ɪ"): "aɪ", ("a", "ʊ"): "aʊ", ("e", "ɪ"): "eɪ", ("o", "ʊ"): "oʊ", ("ɔ", "ɪ"): "ɔɪ"}
R_COLOUR = "˞"


def _bare(seg):
    s = "".join(c for c in unicodedata.normalize("NFD", seg) if not unicodedata.combining(c) and c not in MODIFIERS)
    return LOOKALIKE.get(s, s)


def saa_actual(transcription):
    """'bɹɪ̃ŋ ðiz' -> ['b','ɹ','ɪ','ŋ','ð','iː','z'], or None if a sound isn't in the model's vocabulary."""
    v = vocab()
    out = []
    for word in transcription.split():
        pieces = [_bare(s) for s in segments(word)]
        pieces = [p for p in pieces if p not in MARKS]
        merged = []
        for p in pieces:            # e+ɪ -> eɪ (one diphthong); ɜ/ə + r-colour -> ɚ; other vowel + r-colour -> +ɹ
            if merged and (merged[-1], p) in DIPHTHONG:
                merged[-1] = DIPHTHONG[(merged[-1], p)]
            elif p == R_COLOUR:
                if merged and merged[-1] in ("ɜ", "ə"):
                    merged[-1] = "ɚ"
                else:
                    merged.append("ɹ")
            else:
                merged.append(p)
        for p in merged:
            sym = BROAD.get(p, p)
            if sym not in v or sym in SPECIAL:
                return None
            out.append(sym)
    return out or None


# ---------- 3. the split ----------
def split_of(corpus, speaker, korean, dev_frac=DEV_FRAC):
    """'test' for Korean speakers; else 'dev' or 'train' from a fixed hash of the speaker (same answer every run).
    suitcase speakers are L2-ARCTIC speakers, so both corpora hash under the same name."""
    if korean:
        return "test"
    family = "l2arctic" if corpus in ("l2arctic", "suitcase") else corpus
    if family == "l2arctic":   # only 20 speakers: pick one per first language by hand instead of by chance
        return "dev" if speaker.upper() in L2ARCTIC_DEV else "train"
    h = int(hashlib.sha1(f"{family}:{speaker.upper()}".encode()).hexdigest(), 16) % 10000
    return "dev" if h < dev_frac * 10000 else "train"


# ---------- 4. reading every corpus ----------
def _l2arctic():
    from eval.l2arctic import KOREAN, _phones_tier, other_utterances  # other_utterances skips KOREAN itself
    for spk in KOREAN:          # Korean speakers: only counted, never read into training
        yield "l2arctic", spk, None, None, None, True
    for _, spk, utt, tg, _, wav in other_utterances(None):
        yield "l2arctic", spk, utt, arpa_actual(_phones_tier(tg)), wav, False


def _suitcase():
    from eval.extra_corpora import suitcase_items
    for group, spk, utt, labels, _, audio in suitcase_items():
        korean = group == "suitcase_korean"
        yield "suitcase", spk, utt, None if korean else arpa_actual(labels), None if korean else audio, korean


def _speechocean():
    from eval.extra_corpora import speechocean_items
    for _, spk, uid, labels, _, wav in speechocean_items():
        yield "speechocean", spk, uid, arpa_actual(labels), wav, False


def _saa():
    for r in csv.DictReader(open(ROOT / "data" / "saa_all" / "speakers.csv", encoding="utf-8")):
        if not r["transcription"]:
            continue
        korean = r["language"] == "korean"
        wav = ROOT / "data" / "saa_all" / "audio" / f"{r['speaker']}.mp3"
        yield "saa", r["speaker"], "paragraph", None if korean else saa_actual(r["transcription"]), wav, korean


SOURCES = {"l2arctic": _l2arctic, "suitcase": _suitcase, "speechocean": _speechocean, "saa": _saa}


def _load16k(src):
    import soundfile as sf
    import torch
    import torchaudio.functional as F
    if isinstance(src, tuple):
        audio, sr = src
    else:
        audio, sr = sf.read(src, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SR:
        audio = F.resample(torch.from_numpy(np.ascontiguousarray(audio)), sr, SR).numpy()
    return audio


FIELDS = ["id", "corpus", "speaker", "split", "seconds", "path", "targets"]


def build(out=OUT, limit=None):
    """Write data/ft/audio/<corpus>/<id>.npy (int16, 16 kHz), manifest.csv and summary.json. Korean = skipped."""
    out = Path(out)
    rows, dropped, korean_speakers = [], Counter(), defaultdict(set)
    t0 = time.time()
    for corpus, gen in SOURCES.items():
        n = 0
        for corpus_, spk, utt, targets, src, korean in gen():
            if korean:
                korean_speakers[corpus_].add(spk)
                continue
            if targets is None:
                dropped[f"{corpus}: unknown sound"] += 1
                continue
            audio = _load16k(src)
            sec = len(audio) / SR
            if not MIN_SECONDS <= sec <= MAX_SECONDS:
                dropped[f"{corpus}: length {'>' if sec > MAX_SECONDS else '<'} limit"] += 1
                continue
            uid = f"{corpus}_{spk}_{utt}"
            path = out / "audio" / corpus / f"{uid}.npy"
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, (np.clip(audio, -1, 1) * 32767).astype(np.int16))
            rows.append(dict(id=uid, corpus=corpus, speaker=spk, split=split_of(corpus, spk, False),
                             seconds=round(sec, 3), path=str(path.relative_to(ROOT)), targets=" ".join(targets)))
            n += 1
            if limit and n >= limit:
                break
        print(f"{corpus}: {n} recordings ({time.time() - t0:.0f} s so far)", flush=True)
    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    hours = defaultdict(float)
    speakers = defaultdict(set)
    for r in rows:
        hours[f"{r['corpus']}/{r['split']}"] += r["seconds"] / 3600
        speakers[f"{r['corpus']}/{r['split']}"].add(r["speaker"])
    summary = {"hours": {k: round(v, 2) for k, v in sorted(hours.items())},
               "speakers": {k: len(v) for k, v in sorted(speakers.items())},
               "recordings": len(rows), "dropped": dict(dropped),
               "korean_speakers_left_out": {k: sorted(v) for k, v in korean_speakers.items()},
               "dev_frac": DEV_FRAC, "max_seconds": MAX_SECONDS}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def load_manifest(path=OUT / "manifest.csv"):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for r in rows:
        r["seconds"] = float(r["seconds"])
        r["targets"] = r["targets"].split()
        r["path"] = str(ROOT / r["path"])
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    if a.build:
        build(Path(a.out), a.limit)
