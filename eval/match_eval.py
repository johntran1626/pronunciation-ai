"""Collect evidence for "did they say this sentence / this word?" (eval/match_tune.py picks thresholds).

    python -m eval.match_eval              # all of it (~25-40 min on CPU)
    python -m eval.match_eval --limit 3    # quick check: 3 sentences per speaker

Every recording is real speech; the errors are made by editing it, so we KNOW the right answer:
  orig   the recording + its own text                      -> every word was said (must pass, must be green)
  cut    one word's audio CUT OUT (English: L2-ARCTIC's hand-marked word times; Korean: our aligner's times
         on the native reading) + the full text             -> that word was NOT said
  swap   the recording + its text with ONE word replaced by a word from another sentence -> that word wasn't said
  other  the recording + a DIFFERENT sentence's text        -> the sentence doesn't match
  noise  silence / white noise / a beep + a real text       -> no speech

English: L2-ARCTIC, 24 non-native speakers (groups as in eval/l2arctic.py: "others" = tuning, "korean" = test).
Korean: Zeroth test split, 10 NATIVE speakers (no labelled learner Korean is available).

Output (git-ignored): data/cache/match_words.csv (one row per word) and data/cache/match_sentences.csv.
"""
import argparse
import csv
import itertools
import io
import random
import re
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf

from backend.align import align, emissions
from backend.compare import attach_heard
from backend.g2p import expected_phonemes
from backend.match import sentence_features, word_features
from backend.recognize import recognize
from eval.l2arctic import korean_utterances, other_utterances

WORDS_OUT = Path("data/cache/match_words.csv")
SENT_OUT = Path("data/cache/match_sentences.csv")
ZEROTH_TEST = Path("data/zeroth/data/test-00000-of-00001.parquet")
ZEROTH_TUNE_SPEAKERS = {118, 121, 105, 132, 112}  # 5 of the 10 test-split speakers; the other 5 are the test


# ---------- TextGrid: words with times, and which words a human marked an error in ----------
def _tier(textgrid, name):
    part = textgrid.split(f'name = "{name}"')[1].split("item [")[0]
    return [(float(a), float(b), t.strip())
            for a, b, t in re.findall(r'xmin = ([\d.]+)\s*xmax = ([\d.]+)\s*text = "([^"]*)"', part)]


def textgrid_words(textgrid):
    """-> [(start, end, word, human)] for spoken words; human = 'error' if any phone inside has an error mark."""
    phones = _tier(textgrid, "phones")
    out = []
    for a, b, t in _tier(textgrid, "words"):
        if t.lower() in ("", "sil", "sp"):
            continue
        err = any("," in lab for pa, pb, lab in phones if pa >= a - 1e-6 and pb <= b + 1e-6)
        out.append((a, b, t, "error" if err else "correct"))
    return out


def _norm(word):
    return re.sub(r"[^\w']", "", word.lower())


# ---------- one recording, all conditions ----------
def _aligned(em, heard, text, lang):
    words = align(em, expected_phonemes(text, lang), lang)
    words, _ = attach_heard(words, heard, lang)
    return words


def _sentence_row(base, cond, words, heard):
    f = sentence_features(words)
    return {**base, "cond": cond, "n": f["n"], "heard": round(f["heard"], 4), "conf": round(f["conf"], 4),
            "n_heard": len(heard)}


def _word_rows(base, cond, words, target=None, human=None):
    rows = []
    for i, w in enumerate(words):
        f = word_features(w)
        rows.append({**base, "cond": cond, "word_index": i, "word": w["word"], "n": f["n"],
                     "heard": round(f["heard"], 4), "missing": round(f["missing"], 4), "conf": round(f["conf"], 4),
                     "is_target": int(i == target), "dist": "" if target is None else abs(i - target),
                     "human": (human[i] if human else "")})
    return rows


def run_recording(base, audio, sr, text, lang, rng, other_text, pool, cut_times=None, human=None):
    """All conditions for one real recording. cut_times = [(start, end)] per word (None: use our aligner's)."""
    srows, wrows = [], []
    em = emissions(audio, sr)
    heard = recognize(em)
    orig = _aligned(em, heard, text, lang)
    srows.append(_sentence_row(base, "orig", orig, heard))
    wrows += _word_rows(base, "orig", orig, human=human)

    # swap one word of the TEXT (same audio, same model output)
    written = text.split()
    k = rng.randrange(len(written))
    replacement = rng.choice([w for w in pool if _norm(w) != _norm(written[k])])
    swapped = " ".join(written[:k] + [replacement] + written[k + 1:])
    try:
        sw = _aligned(em, heard, swapped, lang)
        if len(sw) == len(orig):
            srows.append(_sentence_row(base, "swap", sw, heard))
            wrows += _word_rows(base, "swap", sw, target=k)
    except ValueError:
        pass

    # a different sentence's text
    try:
        srows.append(_sentence_row(base, "other", _aligned(em, heard, other_text, lang), heard))
    except ValueError:
        srows.append({**base, "cond": "other", "n": 0, "heard": 0, "conf": 0, "n_heard": len(heard), "error": 1})

    # cut one word out of the AUDIO
    times = cut_times or [(w["start"], w["end"]) for w in orig]
    if len(times) == len(orig):
        k = rng.randrange(len(orig))
        a, b = int(times[k][0] * sr), int(times[k][1] * sr)
        cut_audio = np.concatenate([audio[:a], audio[b:]])
        try:
            em2 = emissions(cut_audio, sr)
            heard2 = recognize(em2)
            cut = _aligned(em2, heard2, text, lang)
            srows.append(_sentence_row(base, "cut", cut, heard2))
            wrows += _word_rows(base, "cut", cut, target=k, human=human)
        except ValueError:
            pass
    return srows, wrows


# ---------- the corpora ----------
def english(limit):
    prompts = [line.split('"')[1] for line in Path("data/l2arctic/PROMPTS").read_text().splitlines() if '"' in line]
    pool = sorted({w.strip(".,;:!?\"'") for p in prompts for w in p.split() if len(w.strip(".,;:!?\"'")) >= 3})
    for source in (korean_utterances(limit), other_utterances(limit)):
        for group, spk, utt, grid, text, wav in source:
            audio, sr = sf.read(wav, dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            tg = textgrid_words(grid)
            ours = [w["word"] for w in expected_phonemes(text, "en")]
            same = len(tg) == len(ours) and all(_norm(t[2]) == _norm(o) for t, o in zip(tg, ours))
            rng = random.Random(f"{spk}/{utt}")
            other = rng.choice([p for p in prompts if p != text])
            yield ({"lang": "en", "group": group, "speaker": spk, "utt": utt}, audio, sr, text, "en", rng, other, pool,
                   [(a, b) for a, b, _, _ in tg] if same else None, [h for *_, h in tg] if same else None)


def korean(limit):
    rows = pq.read_table(ZEROTH_TEST, columns=["id", "speaker_id", "audio", "text"]).to_pylist()
    pool = sorted({w for r in rows for w in r["text"].split() if len(w) >= 2})
    per_speaker = {}
    for r in rows:
        n = per_speaker[r["speaker_id"]] = per_speaker.get(r["speaker_id"], 0) + 1
        if limit and n > limit:
            continue
        audio, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
        rng = random.Random(r["id"])
        other = rng.choice([x["text"] for x in rows if x["text"] != r["text"]])
        group = "tune" if r["speaker_id"] in ZEROTH_TUNE_SPEAKERS else "test"
        yield ({"lang": "ko", "group": group, "speaker": r["speaker_id"], "utt": r["id"]}, audio, sr, r["text"], "ko",
               rng, other, pool, None, None)


def noise_rows():
    """No speech at all: must never pass the sentence check."""
    rng = np.random.default_rng(0)
    sr, out = 16000, []
    texts = {"en": ["From now on we're pals.", "Clubs and balls and cities grew to be only memories."],
             "ko": ["강아지가 용변을 보도록 유도하는 말을 가르칠 수도 있다", "돌고래는 주로 오징어 물고기 갑각류 등을 먹고 삽니다"]}
    for seconds in (2, 4, 8):
        n = sr * seconds
        t = np.arange(n) / sr
        for kind, x in [("silence", np.zeros(n)), ("white_noise", 0.05 * rng.standard_normal(n)),
                        ("beep", 0.3 * np.sin(2 * np.pi * 440 * t)), ("hum", 0.2 * np.sin(2 * np.pi * 60 * t))]:
            em = emissions(x.astype("float32"), sr)
            heard = recognize(em)
            for lang, ts in texts.items():
                for text in ts:
                    try:
                        words = _aligned(em, heard, text, lang)
                    except ValueError:
                        continue  # "too short for this sentence": the API already refuses it
                    out.append(_sentence_row({"lang": lang, "group": "noise", "speaker": kind, "utt": f"{seconds}s"},
                                             "noise", words, heard))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="sentences per speaker (quick check)")
    args = ap.parse_args()
    WORDS_OUT.parent.mkdir(parents=True, exist_ok=True)
    start, n = time.time(), 0
    sfields = ["lang", "group", "speaker", "utt", "cond", "n", "heard", "conf", "n_heard", "error"]
    wfields = ["lang", "group", "speaker", "utt", "cond", "word_index", "word", "n", "heard", "missing", "conf",
               "is_target", "dist", "human"]
    with open(SENT_OUT, "w", newline="") as fs, open(WORDS_OUT, "w", newline="") as fw:
        sout = csv.DictWriter(fs, fieldnames=sfields, restval="")
        wout = csv.DictWriter(fw, fieldnames=wfields, restval="")
        sout.writeheader()
        wout.writeheader()
        sout.writerows(noise_rows())
        for job in itertools.chain(english(args.limit), korean(args.limit)):
            srows, wrows = run_recording(*job)
            sout.writerows(srows)
            wout.writerows(wrows)
            n += 1
            if n % 100 == 0:
                print(f"{n} recordings, {time.time() - start:.0f} s", flush=True)
    print(f"done: {n} recordings in {time.time() - start:.0f} s -> {SENT_OUT}, {WORDS_OUT}")


if __name__ == "__main__":
    main()
