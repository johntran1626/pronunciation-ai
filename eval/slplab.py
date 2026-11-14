"""slplab as a "second listener" for the trained detectors. PRIVATE TEST.

    python -m eval.slplab --run      # slow (hours, CPU), resumable: slplab once per recording -> data/cache/slplab_features.csv
    python -m eval.slplab            # seconds: detectors without vs with the 3 slplab numbers -> data/cache/detectors_slplab.json

PRIVATE: the model card (slplab/wav2vec2-large-robust-L2-english-phoneme-recognition) has no license. Nothing from
it ships in the app or gets published except aggregate numbers labelled "private test". Its outputs stay in
data/cache/ (git-ignored).

In brief: slplab's model was trained on Korean learners' English. For every sound we already check, we look at
what slplab heard INSIDE that sound's time window (the window comes from OUR alignment, already in the caches) and
write down 3 numbers:
  s_margin       how much more slplab believes the mistake than the right sound (log of the best frame of each;
                 > 0 = it leans to the mistake). Extra vowel has no "right sound", so it is the log of the best
                 'eu' frame just after the consonant.
  s_heard_wrong  1 if slplab's top choice in any frame of the window is the mistake (e.g. "r" where L was expected)
  s_err          the strongest "_err" frame: slplab's own "this sound was mispronounced" token
Then the same detector is trained twice, without and with these 3 numbers, on the same rows, same split
(tune = non-Korean speakers, test = Korean), same pass bar. Only if the "with" column is better on Korean speakers
has slplab helped. Like asking a second doctor who specialises in your exact condition: you only keep listening if
their opinion actually improves the diagnosis.
"""
import csv
import json
import math
import sys
import time
from functools import cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODEL = "slplab/wav2vec2-large-robust-L2-english-phoneme-recognition"
REVISION = "b303be3ece12153cc4e54f737e81a9807b635ace"   # the copy first downloaded (pinned: same model every run)
OUT = ROOT / "data/cache/slplab_features.csv"
REPORT = ROOT / "data/cache/detectors_slplab.json"
SR = 16000

# pair -> (right sound, mistake) in slplab's ARPAbet-style tokens. Extra vowel: Korean-style inserted vowel 'eu'.
PAIR_SOUNDS = {"l_as_r": ("l", "r"), "f_as_p": ("f", "p"), "v_as_b": ("v", "b"), "th_as_s": ("th", "s"),
               "dh_as_d": ("dh", "d"), "ih_as_iy": ("ih", "iy"), "iy_as_ih": ("iy", "ih"),
               "extra_vowel": (None, "eu")}
S_COLS = ("s_margin", "s_heard_wrong", "s_err")
KEY = ("source", "speaker", "utt", "word_index", "phoneme_index", "pair")
PAD = 0.02      # seconds added on both sides of our window (our times and slplab's frames can differ by a frame)
AFTER = 0.15    # extra vowel: the inserted vowel comes right AFTER the final consonant
EPS = 1e-6


def token_ids(vocab, base):
    """'r' -> ids of r, r_err and r* (slplab's variants of the same sound)."""
    return [i for t, i in vocab.items() if t in (base, f"{base}_err", f"{base}*")]


def window_features(log_probs, sec_per_frame, start, end, pair, vocab):
    """slplab's (frames, tokens) log-probs + one sound's start/end (s) -> the 3 S_COLS numbers."""
    right, wrong = PAIR_SOUNDS[pair]
    lo = max(0, int(math.floor((start - PAD) / sec_per_frame + 1e-9)))
    hi = min(len(log_probs), int(math.ceil((end + PAD + (AFTER if right is None else 0)) / sec_per_frame - 1e-9)))
    if hi <= lo:
        return {c: None for c in S_COLS}                  # window outside the audio: no evidence
    p = np.exp(np.asarray(log_probs, dtype=float)[lo:hi])
    w_ids = token_ids(vocab, wrong)
    best_wrong = p[:, w_ids].sum(axis=1).max()
    if right is None:
        margin = math.log(best_wrong + EPS)
    else:
        margin = math.log(best_wrong + EPS) - math.log(p[:, token_ids(vocab, right)].sum(axis=1).max() + EPS)
    err_ids = [i for t, i in vocab.items() if t.endswith("_err")]
    return {"s_margin": round(margin, 4),
            "s_heard_wrong": int(np.isin(p.argmax(axis=1), w_ids).any()),
            "s_err": round(float(p[:, err_ids].sum(axis=1).max()), 4)}


def _key(r):
    return (r["source"], r["speaker"].split(":", 1)[-1], r["utt"], int(r["word_index"]), int(r["phoneme_index"]),
            r["pair"])


def _used(r):
    return r["pair"] in PAIR_SOUNDS and r["human"] in ("correct", "error")


def recordings_needed(rows):
    """Rows (eval.combined.load_all shape) -> {(source, speaker, utt)} that have at least one slplab row."""
    return {_key(r)[:3] for r in rows if _used(r)}


def attach(rows, feats):
    """Give each row its slplab columns (as stored: strings). No match -> the row gets none (= missing)."""
    for r in rows:
        f = feats.get(_key(r))
        if f:
            r.update(f)
    return rows


def load(path=OUT):
    out = {}
    if Path(path).exists():
        for r in csv.DictReader(open(path, encoding="utf-8")):
            out[(r["source"], r["speaker"], r["utt"], int(r["word_index"]), int(r["phoneme_index"]), r["pair"])] = \
                {c: r[c] for c in S_COLS if r[c] != ""}
    return out


# ---------- the model (slow part) ----------
@cache
def _model():
    from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC
    return (Wav2Vec2FeatureExtractor.from_pretrained(MODEL, revision=REVISION),
            Wav2Vec2ForCTC.from_pretrained(MODEL, revision=REVISION).eval())


@cache
def vocab():
    from huggingface_hub import hf_hub_download
    return json.load(open(hf_hub_download(MODEL, "vocab.json", revision=REVISION), encoding="utf-8"))


def log_probs(audio, sr):
    """Samples -> ((frames, tokens) log-probs as numpy, seconds per frame)."""
    import torch
    import torchaudio.functional as F
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    wav = torch.from_numpy(audio)
    if sr != SR:
        wav = F.resample(wav, sr, SR)
    extractor, model = _model()
    inputs = extractor(wav.numpy(), sampling_rate=SR, return_tensors="pt")
    with torch.inference_mode():
        lp = model(inputs.input_values).logits.log_softmax(-1)[0].numpy()
    return lp, (len(wav) / SR) / lp.shape[0]


# ---------- the audio of every needed recording ----------
def _audio(needed):
    """Yields (source, speaker, utt, audio, sr) for each needed recording, corpus by corpus."""
    import soundfile as sf
    from eval import extra_corpora as xc
    from eval import l2arctic as la
    want = {s: {k[1:] for k in needed if k[0] == s} for s in ("l2arctic", "suitcase", "speechocean", "saa")}
    for spk, utt in sorted(want["l2arctic"]):
        p = ROOT / la.DATA / spk / "wav" / f"{utt}.wav"
        if p.exists():                                      # the 4 Korean speakers are unzipped
            yield ("l2arctic", spk, utt, *sf.read(p, dtype="float32"))
    for _g, spk, utt, _tg, _text, wav in la.other_utterances(None):   # the 20 others: straight from the zip
        if (spk, utt) in want["l2arctic"]:
            yield ("l2arctic", spk, utt, *sf.read(wav, dtype="float32"))
    for _g, spk, utt, _l, _t, (audio, sr) in xc.suitcase_items():
        if (spk, utt) in want["suitcase"]:
            yield "suitcase", spk, utt, audio, sr
    for _g, spk, utt, _l, _t, wav in xc.speechocean_items():
        if (spk, utt) in want["speechocean"]:
            yield ("speechocean", spk, utt, *sf.read(wav, dtype="float32"))
    for spk, utt in sorted(want["saa"]):
        yield ("saa", spk, utt, *sf.read(ROOT / "data/saa_all/audio" / f"{spk}.mp3", dtype="float32"))


def run():
    from eval.combined import CACHES, load_all
    rows, missing = load_all(CACHES)
    if missing:
        raise SystemExit(f"missing caches: {missing}")
    by_rec = {}
    for r in rows:
        if _used(r):
            by_rec.setdefault(_key(r)[:3], []).append(r)
    done = {k[:3] for k in load()}
    if OUT.exists():                                        # recordings written with all-blank values count too
        done |= {(r["source"], r["speaker"], r["utt"]) for r in csv.DictReader(open(OUT, encoding="utf-8"))}
    todo = set(by_rec) - done
    print(f"{len(by_rec)} recordings needed, {len(done & set(by_rec))} already done, {len(todo)} to go", flush=True)
    new = not OUT.exists()
    t0, n, failed = time.time(), 0, []
    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(KEY) + list(S_COLS))
        if new:
            w.writeheader()
        voc = vocab()
        for source, spk, utt, audio, sr in _audio(todo):
            try:
                lp, spf = log_probs(audio, sr)
            except Exception as e:                          # one bad file must not stop a 4-hour run
                failed.append(f"{source}:{spk}/{utt}")
                print(f"FAILED {source}:{spk}/{utt}: {e}", flush=True)
                continue
            for r in by_rec[(source, spk, utt)]:
                k = _key(r)
                w.writerow({**dict(zip(KEY, k)),
                            **window_features(lp, spf, float(r["start"]), float(r["end"]), r["pair"], voc)})
            f.flush()
            n += 1
            if n % 100 == 0:
                print(f"[{n}/{len(todo)}] {time.time() - t0:.0f} s", flush=True)
    print(f"done: {n} recordings in {time.time() - t0:.0f} s; failed: {failed}", flush=True)


# ---------- the comparison ----------
def report():
    from backend.detector import FEATURE_NAMES
    from eval.combined import CACHES, load_all
    from eval.detectors import PAIRS, attach_saa_features, evaluate_pair, load_saa_features
    from eval.run import cap_for
    rows, missing = load_all(CACHES)
    if missing or not OUT.exists():
        raise SystemExit(f"missing caches {missing} or {OUT.name}: run `python -m eval.slplab --run` first")
    rows = attach(attach_saa_features(rows, load_saa_features()), load())
    out = {"private": "private test: slplab model has no license; aggregate numbers only", "pairs": {}}
    for p in PAIRS:
        sub = [r for r in rows if r["pair"] == p]
        used = [r for r in sub if r["human"] in ("correct", "error")]
        out["pairs"][p] = {"rows": len(used), "rows with slplab": sum("s_margin" in r for r in used),
                           "without": evaluate_pair(sub, cap_for(p)),
                           "with": evaluate_pair(sub, cap_for(p), names=FEATURE_NAMES + S_COLS)}
    REPORT.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    def cell(r):
        if not r["feasible"]:
            return f"AUC {r['oof_auc'] or 0:.3f} (below 0.70, Korean not looked at)"
        k = r["test (korean)"]
        p = "—" if k["precision"] is None else f"{100 * k['precision']:.0f}%"
        return (f"AUC {r['oof_auc']:.3f}; caught {k['caught']['k']}/{k['caught']['n']}; FA {k['false_alarms']['k']}/"
                f"{k['false_alarms']['n']}; reds right {p}; {'PASS' if r['enabled'] else 'fail'}")

    print("| pair | rows (with slplab) | WITHOUT slplab | WITH slplab |\n|---|---|---|---|")
    for p, r in out["pairs"].items():
        print(f"| {p} | {r['rows']} ({r['rows with slplab']}) | {cell(r['without'])} | {cell(r['with'])} |")
    print(f"\nwrote {REPORT.relative_to(ROOT)} (private; backend/thresholds.json NOT changed)")


if __name__ == "__main__":
    run() if sys.argv[1:2] == ["--run"] else report()
