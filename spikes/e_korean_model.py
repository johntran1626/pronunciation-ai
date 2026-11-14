"""Feasibility check: does a KOREAN-trained phone recognizer hear ㅂ/ㅃ/ㅍ (and ㅓ/ㅗ, ㅡ/ㅜ)?
Plan + pass bars were fixed before any run.

    python -m spikes.e_korean_model            # ~25-35 min on CPU
    python -m spikes.e_korean_model --limit 3  # quick check: 3 recordings per speaker

In brief: our app's recognizer was trained on many languages and writes ㅂ, ㅃ and ㅍ all as "p", so it
can't tell them apart. This model (slplab, Apache-2.0) was trained only on native Korean with separate
symbols: B (ㅂ), BB (ㅃ), Ph (ㅍ). We ask two things:
  Part 1. On native speech, with "fake errors" made by swapping the target letter (eval/korean_sim.py's trick: a native
          says 불, we tell the app the target was 풀), does the model's margin flag the swaps while keeping
          false alarms on correct sounds at 0.5%?
  Part 2. English stops carried into Korean (eval/korean_carryover.py's set): does the model tell an English "p" puff or an
          English "b" from a native Korean ㅃ? That set used VOT; this is the same rows, scored by the model.
Nothing here changes the app.
"""
import argparse
import csv
import io
import json
import statistics
import time
from collections import Counter, defaultdict
from functools import cache
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf
import torch
import torchaudio.functional as F

from backend.g2p import TENSE, expected_phonemes
from backend.sequence_align import align_sequences
from eval.korean_sim import PAIRS, SEED, ZEROTH, _ipa, _sampled_variants, recordings
from eval.run import rate

MODEL = "slplab/wav2vec2-xls-r-300m_phone-mfa_korean"
SR = 16000
VOT_CACHE = Path("data/cache/spike_b_vot.csv")
CMU = Path("data/cmu_arctic")
OUT1, OUT2 = Path("data/cache/spike_e_part1.csv"), Path("data/cache/spike_e_part2.csv")
RESULTS = Path("results/spike_e.json")
CAP = 0.005                       # false-alarm cap: at most 0.5% of correct sounds red (tuned on the tune speakers)
MAX_EXTEND_FRAMES = 7             # ~0.15 s, like backend/align.py's MAX_EXTEND

# ---------- 1. our IPA -> the model's symbols ----------
# The model's vocab (vocab.json, checked at load time). Uppercase = released consonants and vowels;
# lowercase k t p = unreleased final stops; diphthongs are ONE symbol (iEO = ㅕ). ㅐ and ㅔ are both E.
MFA_VOCAB = {"A", "B", "BB", "CHh", "D", "DD", "E", "EO", "EU", "G", "GG", "H", "I", "J", "JJ", "Kh", "L", "M",
             "N", "NG", "O", "Ph", "R", "S", "SS", "Th", "U", "euI", "iA", "iE", "iEO", "iO", "iU", "k", "oA",
             "oE", "p", "t", "uEO", "uI"}
CONS = {"k": "G", "k" + TENSE: "GG", "kʰ": "Kh", "t": "D", "t" + TENSE: "DD", "tʰ": "Th",
        "p": "B", "p" + TENSE: "BB", "pʰ": "Ph", "s": "S", "s" + TENSE: "SS",
        "tɕ": "J", "t" + TENSE + "ɕ": "JJ", "tɕʰ": "CHh", "n": "N", "m": "M", "ŋ": "NG", "ɾ": "R", "l": "L",
        "h": "H"}
VOW = {"a": "A", "ɛ": "E", "e": "E", "ʌ": "EO", "o": "O", "u": "U", "ɯ": "EU", "i": "I"}
DIPH = {("j", "a"): "iA", ("j", "ɛ"): "iE", ("j", "e"): "iE", ("j", "ʌ"): "iEO", ("j", "o"): "iO",
        ("j", "u"): "iU", ("w", "a"): "oA", ("w", "ɛ"): "oE", ("w", "e"): "oE", ("w", "ʌ"): "uEO",
        ("w", "i"): "uI", ("ɰ", "i"): "euI"}
FINAL_STOP = {"k": "k", "t": "t", "p": "p"}
GLIDES = {"j", "w", "ɰ"}

# stop type of each jamo, and the model's symbol for each (place, type)
STOP_TYPE = {j: t for t, js in (("lenis", "ㅂㄷㄱ"), ("tense", "ㅃㄸㄲ"), ("asp", "ㅍㅌㅋ")) for j in js}
PLACE_TOKENS = {"lab": {"lenis": "B", "tense": "BB", "asp": "Ph"},
                "alv": {"lenis": "D", "tense": "DD", "asp": "Th"},
                "vel": {"lenis": "G", "tense": "GG", "asp": "Kh"}}


def to_mfa(words):
    """g2p.expected_phonemes output -> [(model symbol, [(word index, phoneme index), ...])].
    A glide + vowel (j ʌ) becomes one symbol (iEO) that covers both phonemes."""
    out = []
    for wi, w in enumerate(words):
        ph = w["phonemes"]
        pi = 0
        while pi < len(ph):
            p = ph[pi]
            nxt = ph[pi + 1] if pi + 1 < len(ph) else None
            if p in GLIDES and (p, nxt) in DIPH:
                out.append((DIPH[(p, nxt)], [(wi, pi), (wi, pi + 1)]))
                pi += 2
                continue
            if p in VOW:
                tok = VOW[p]
            elif p in FINAL_STOP and (nxt is None or (nxt not in VOW and nxt not in GLIDES)):
                tok = FINAL_STOP[p]   # no vowel after it: an unreleased final stop (밥's ㅂ)
            else:
                tok = CONS[p]
            out.append((tok, [(wi, pi)]))
            pi += 1
    return out


def pooled(pair):
    """'ㅃ_as_ㅂ' -> 'tense_as_lenis' (stops pooled across ㅂ/ㄷ/ㄱ, since ㅃ alone is rare); vowels unchanged."""
    target, said = pair.split("_as_")
    if target in STOP_TYPE:
        return f"{STOP_TYPE[target]}_as_{STOP_TYPE[said]}"
    return pair


def pick_threshold(correct_margins, cap):
    """The cut t such that at most cap x n correct sounds have margin > t (flag = margin > t)."""
    if not correct_margins:
        return None
    s = sorted(correct_margins, reverse=True)
    k = int(cap * len(s))       # how many correct sounds we may flag
    return s[k] if k < len(s) else s[-1]


def auc(errors, correct):
    """Chance that a random error scores higher than a random correct sound (ties count half)."""
    e, c = np.asarray(errors, float), np.asarray(correct, float)
    if not len(e) or not len(c):
        return None
    gt = (e[:, None] > c[None, :]).sum() + 0.5 * (e[:, None] == c[None, :]).sum()
    return float(gt / (len(e) * len(c)))


# ---------- 2. the model ----------
@cache
def _model():
    from huggingface_hub import hf_hub_download
    from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC
    vocab = json.load(open(hf_hub_download(MODEL, "vocab.json"), encoding="utf-8"))
    assert MFA_VOCAB <= set(vocab), MFA_VOCAB - set(vocab)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    return Wav2Vec2FeatureExtractor.from_pretrained(MODEL), model, vocab


def emissions(audio, sr):
    """-> (log_probs [frames, vocab], seconds per frame). Same steps as backend/align.py, other model."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    wav = torch.from_numpy(audio)
    if sr != SR:
        wav = F.resample(wav, sr, SR)
    fe, model, _ = _model()
    inputs = fe(wav.numpy(), sampling_rate=SR, return_tensors="pt")
    with torch.inference_mode():
        lp = model(inputs.input_values).logits.log_softmax(-1)[0]
    return lp, (len(wav) / SR) / lp.shape[0]


def align_ko(lp, words):
    """Forced alignment with THIS model. -> (window per (wi, pi) in frames, token index per (wi, pi), tokens)."""
    _, model, vocab = _model()
    pairs = to_mfa(words)
    toks = [t for t, _ in pairs]
    ids = [vocab[t] for t in toks]
    if lp.shape[0] < len(ids) + sum(a == b for a, b in zip(ids, ids[1:])):
        raise ValueError("recording too short for this sentence")
    labels, scores = F.forced_align(lp.unsqueeze(0), torch.tensor([ids], dtype=torch.int32),
                                    blank=model.config.pad_token_id)
    # blank= matters: merge_tokens assumes blank id 0, but in THIS model id 0 is the vowel A (blank is 42).
    # Without it every ㅏ vanished and all later windows slid onto the wrong sound (found in the quick check).
    spans = F.merge_tokens(labels[0], scores[0].exp(), blank=model.config.pad_token_id)
    assert len(spans) == len(ids), (len(spans), len(ids))
    # Window = the whole gap between the neighbours' spikes (capped at ~0.15 s each side), NOT just the frames
    # the aligner gave this symbol. Found in the quick check: when the target is swapped (ㅍ forced onto a
    # native ㅂ), the aligner parks ㅍ on a frame NEXT TO the real ㅂ spike, so a window of its own frames
    # missed the evidence. The neighbours (vowels) are placed reliably, so the gap between them is safe.
    win, tok_of = {}, {}
    for i, ((_, cover), sp) in enumerate(zip(pairs, spans)):
        prev = spans[i - 1].end if i else 0
        nxt = spans[i + 1].start if i + 1 < len(spans) else lp.shape[0]
        f0 = max(prev, sp.start - MAX_EXTEND_FRAMES)
        f1 = max(f0 + 1, min(nxt, sp.end + MAX_EXTEND_FRAMES))
        sp = type("S", (), {"start": f0})  # only .start is used below
        for key in cover:
            win[key], tok_of[key] = (sp.start, f1), i
    return win, tok_of, toks, pairs


def greedy(lp):
    """The model's own transcription: best symbol per frame, repeats merged, blanks dropped."""
    _, model, vocab = _model()
    inv = {i: t for t, i in vocab.items()}
    best = lp.argmax(-1).tolist()
    out = [inv[b] for i, b in enumerate(best) if (i == 0 or b != best[i - 1]) and b != model.config.pad_token_id]
    return [t for t in out if t in MFA_VOCAB]


def _seq_key(t):
    # align_sequences treats a symbol as a vowel if it starts with a vowel letter; keep each symbol unique
    return ("a" if t in VOW.values() or t in DIPH.values() else "C") + t


def heard_per_token(expected_toks, heard_toks):
    """For each expected symbol, what the greedy transcription has in its place (None = nothing)."""
    steps = align_sequences([_seq_key(t) for t in expected_toks], [_seq_key(t) for t in heard_toks])
    out = []
    for op, e, h in steps:
        if op != "ins":
            out.append(h[1:] if h else None)
    return out


def _peak(probs, f0, f1, tok):
    return probs[f0:f1, _model()[2][tok]].max().item()


# ---------- 3. Part 1: native speech + text swaps ----------
def _single_token(ipa):
    return CONS.get(ipa) or VOW.get(ipa)


def part1_rows(group, spk, utt, text, lp, probs, heard, rng):
    text = " ".join(text.split())
    orig = expected_phonemes(text, "ko")
    win, tok_of, toks, pairs = align_ko(lp, orig)
    said_in_place = heard_per_token(toks, heard)
    rows = []

    def add(human, pair, words, w, t, toks_, heard_, wi, pi):
        kind, said, target = PAIRS[pair]
        target_tok, said_tok = _single_token(_ipa(kind, target)), _single_token(_ipa(kind, said))
        ti = t[(wi, pi)]
        if toks_[ti] != target_tok:          # e.g. ʌ inside ㅕ (iEO), or a final unreleased ㅂ: not this pair
            return
        f0, f1 = w[(wi, pi)]
        rows.append(dict(group=group, speaker=spk, utt=utt, pair=pair, pooled=pooled(pair), human=human,
                         position="initial" if pi == 0 else "inside", word=words[wi]["word"],
                         margin=round(_peak(probs, f0, f1, said_tok) - _peak(probs, f0, f1, target_tok), 4),
                         baseline_flag=int(heard_[ti] != target_tok)))

    for wi, w in enumerate(orig):                                   # CORRECT: what the native said
        for pi, p in enumerate(w["phonemes"]):
            for pair, (kind, said, target) in PAIRS.items():
                if p == _ipa(kind, target):
                    add("correct", pair, orig, win, tok_of, toks, said_in_place, wi, pi)
    for v in _sampled_variants(text, orig, rng):                    # ERROR: same audio, swapped target
        vw = expected_phonemes(v["target_text"], "ko")
        vwin, vtok, vtoks, _ = align_ko(lp, vw)
        add("error", v["pair"], vw, vwin, vtok, vtoks, heard_per_token(vtoks, heard),
            v["word_index"], v["phoneme_index"])
    return rows


# ---------- 4. Part 2: English carry-over (b_vot.py's stop rows) ----------
def stop_scores(probs, spf, r):
    """Peak probability of the lenis / tense / aspirated symbol for this place, from the stop to vowel + 50 ms."""
    t_stop = float(r["t_stop"])
    t_end = (float(r["onset"]) if r["onset"] else t_stop + 0.08) + 0.05
    f0 = int(t_stop / spf)
    f1 = max(f0 + 1, min(probs.shape[0], int(t_end / spf) + 1))
    toks = PLACE_TOKENS[r["place"]]
    s = {k: round(_peak(probs, f0, f1, t), 4) for k, t in toks.items()}
    return dict(lang=r["lang"], speaker=r["speaker"], utt=r["utt"], word=r["word"], cat=r["cat"],
                place=r["place"], initial=r["initial"], p_lenis=s["lenis"], p_tense=s["tense"], p_asp=s["asp"],
                picked=max(s, key=s.get))


def _vot_rows():
    by_utt = defaultdict(list)
    for r in csv.DictReader(open(VOT_CACHE)):
        if r["cat"] in ("lenis", "tense", "asp", "vcd", "sp") and r["place"] in PLACE_TOKENS:
            by_utt[(r["lang"], r["speaker"], r["utt"])].append(r)
    return by_utt


# ---------- 5. report ----------
def summarize1(rows):
    out = {}
    keyed = defaultdict(list)
    for r in rows:
        keyed[(r["pooled"], r["position"])].append(r)
    for (name, pos), rs in sorted(keyed.items()):
        m = lambda g, h: [float(r["margin"]) for r in rs if r["group"] == g and r["human"] == h]
        t = pick_threshold(m("tune", "correct"), CAP)
        test_ok, test_err = m("test", "correct"), m("test", "error")
        err_rows = [r for r in rs if r["group"] == "test" and r["human"] == "error"]
        fa = sum(x > t for x in test_ok) if t is not None else None
        caught = sum(x > t for x in test_err) if t is not None else None
        b_fa = sum(int(r["baseline_flag"]) for r in rs if r["group"] == "test" and r["human"] == "correct")
        b_caught = sum(int(r["baseline_flag"]) for r in err_rows)
        n_spk = len({r["speaker"] for r in err_rows})
        s = dict(threshold=t, tune_correct=len(m("tune", "correct")), test_correct=len(test_ok),
                 test_errors=len(test_err), error_speakers=n_spk,
                 app=dict(false_alarms=fa, false_alarm=rate(fa, len(test_ok)) if t is not None else None,
                          caught=caught, detection=rate(caught, len(test_err)) if t is not None else None),
                 baseline=dict(false_alarms=b_fa, false_alarm=rate(b_fa, len(test_ok)),
                               caught=b_caught, detection=rate(b_caught, len(test_err))))
        if pos == "initial":
            if len(test_err) < 30 or n_spk < 5 or t is None:
                s["verdict"] = "too few"
            else:
                ok = fa / len(test_ok) <= 0.01 and caught / len(test_err) >= 0.5
                s["verdict"] = "pass" if ok else "fail"
        out[f"{name} ({pos})"] = s
    return out


def summarize2(rows):
    ko = lambda cat: [r for r in rows if r["lang"] == "ko" and r["cat"] == cat]
    en = lambda cat: [r for r in rows if r["lang"] == "en" and r["cat"] == cat]
    f = lambda r, key: float(r[key])
    tests = {
        "ㅃㄸㄲ with an English-p puff (asp - tense)": (
            lambda r: f(r, "p_asp") - f(r, "p_tense"), en("asp"), ko("tense"), en("sp"), "VOT: 0.920 / 0.947"),
        "ㅃㄸㄲ like English b/d/g (max(lenis, asp) - tense)": (
            lambda r: max(f(r, "p_lenis"), f(r, "p_asp")) - f(r, "p_tense"), en("vcd"), ko("tense"), None,
            "VOT: 0.591 / -"),
        "ㅂㄷㄱ like English b/d/g (tense - lenis)": (
            lambda r: f(r, "p_tense") - f(r, "p_lenis"), en("vcd"), ko("lenis"), None, "not in the VOT set"),
    }
    out = {}
    for name, (score, err, ok, ctrl, vot_set) in tests.items():
        a_ko = auc([score(r) for r in err], [score(r) for r in ok])
        a_ctrl = auc([score(r) for r in err], [score(r) for r in ctrl]) if ctrl else None
        survives = a_ko is not None and a_ko >= 0.80 and (a_ctrl is None or a_ctrl >= 0.80)
        out[name] = dict(errors=len(err), korean_correct=len(ok), controls=len(ctrl) if ctrl else None,
                         auc_vs_korean=round(a_ko, 3) if a_ko is not None else None,
                         auc_vs_controls=round(a_ctrl, 3) if a_ctrl is not None else None,
                         survives=survives if ctrl else (a_ko is not None and a_ko >= 0.80),
                         has_control=bool(ctrl), vot_set=vot_set)
    picked = {}
    for lang, cats in (("en", ("asp", "vcd", "sp")), ("ko", ("lenis", "tense", "asp"))):
        for cat in cats:
            rs = [r for r in rows if r["lang"] == lang and r["cat"] == cat]
            c = Counter(r["picked"] for r in rs)
            picked[f"{lang} {cat}"] = {k: round(c[k] / len(rs), 3) for k in ("lenis", "tense", "asp")} | {"n": len(rs)}
    return dict(tests=out, model_picks=picked)


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="recordings per speaker (quick check)")
    args = ap.parse_args()
    rng = __import__("random").Random(SEED)
    vot = _vot_rows()
    rows1, rows2, secs, n, t0 = [], [], [], 0, time.time()

    for group, spk, utt, text, audio, sr in recordings(args.limit):   # Zeroth: Part 1 + native half of Part 2
        try:
            t = time.time()
            lp, spf = emissions(audio, sr)
            secs.append(time.time() - t)
            probs, heard = lp.exp(), greedy(lp)
            rows1 += part1_rows(group, spk, utt, text, lp, probs, heard, rng)
            rows2 += [stop_scores(probs, spf, r) for r in vot.get(("ko", spk, utt), [])]
        except ValueError as e:
            print(f"skip {spk}/{utt}: {e}")
            continue
        n += 1
        if n % 100 == 0:
            print(f"{n} Zeroth recordings, {time.time() - t0:.0f} s", flush=True)

    en_utts = sorted({(s, u) for (lang, s, u) in vot if lang == "en"})
    if args.limit:
        en_utts = [k for k in en_utts if int(k[1][-4:]) <= args.limit]
    for spk, utt in en_utts:                                            # CMU: English half of Part 2
        audio, sr = sf.read(CMU / f"cmu_us_{spk}_arctic/wav/{utt}.wav", dtype="float32")
        lp, spf = emissions(audio, sr)
        rows2 += [stop_scores(lp.exp(), spf, r) for r in vot[("en", spk, utt)]]
    print(f"done: {n} Zeroth + {len(en_utts)} CMU recordings in {time.time() - t0:.0f} s")

    _write(OUT1, rows1)
    _write(OUT2, rows2)
    res = dict(source="spikes/e_korean_model.py", model=MODEL, limit_per_speaker=args.limit,
               warning="Part 1 = SIMULATED errors on NATIVE speech; Part 2 = English vs Korean natives. Optimistic.",
               zeroth_recordings=n, cmu_recordings=len(en_utts),
               seconds_per_recording=dict(median=round(statistics.median(secs), 3),
                                          p95=round(float(np.percentile(secs, 95)), 3)),
               part1=summarize1(rows1), part2=summarize2(rows2))
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
