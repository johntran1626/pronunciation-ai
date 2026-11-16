"""The Korean-trained listener: how far each Korean sound is from what a native says.

    rows = measure(audio, sr, expected_phonemes(text, "ko"))
    -> [{"wi", "pi", "check", "position", "margin", "heard_said"}, ...]   one row per (sound, possible mistake)

Why a second model: the app's main listener was trained on many languages. It writes Korean ㅂ, ㅃ and ㅍ all
as "p" and native ㅓ as "ɔ" in our early tests, so it can't judge Korean. This one (slplab, Apache-2.0)
was trained on native Korean read speech only and has a separate symbol for every Korean sound: B ㅂ, BB ㅃ, Ph ㅍ,
EO ㅓ, O ㅗ, EU ㅡ, U ㅜ. An early feasibility test showed it tells native Korean stop types apart far better than timing.

How one sound is measured (like asking "which of these two did you hear, and how sure are you?"):
  1. The model listens once: for every 20 ms frame, a probability for every Korean symbol.
  2. Forced alignment with THIS model puts each expected symbol on the audio -> a time window per sound.
  3. margin = best frame of the MISTAKE symbol - best frame of the RIGHT symbol, inside that window (-1..1).
     Natives score low; someone saying ㅗ where ㅓ belongs scores high.
  4. heard_said = the model's own free transcription has the mistake symbol in that place.
A sound turns red only when BOTH hold: margin above the cut AND heard_said (fires()). The cut per check comes
from native speakers (eval/korean_checks.py), and a check is used only if it passed its four bars.

Which sounds get a check (candidates()): only the big confusions, and only sounds the SPELLING shows. A ㄲ that
only a sound rule creates (학교 said 학꾜) or a ㅌ made by merging with ㅎ (좋다 said 조타) is never checked:
natives don't always apply those rules, so a "mistake" there may just be another correct way to say it.
"""
import json
from functools import cache

import numpy as np

from backend.g2p import TENSE
from backend.sequence_align import align_sequences
from backend.text_map import korean_sources

MODEL = "slplab/wav2vec2-xls-r-300m_phone-mfa_korean"
REVISION = "e26ff9dfb62169acf445d0060ef56863c018b20e"   # pinned: the same weights every run
SR = 16000
MAX_EXTEND_FRAMES = 7                                     # a window reaches at most ~0.15 s past its own frames

# ---------- 1. our IPA -> the model's symbols ----------
# Uppercase = released consonants and vowels; lowercase k t p = unreleased final stops; a glide + vowel is ONE
# symbol (iEO = ㅕ). ㅐ and ㅔ are both E (the model merges them, like most Seoul speakers).
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

# ---------- 2. the ten candidate checks (fixed before any run) ----------
# name -> (target symbol(s), mistake symbol(s)). Stops are pooled over ㅂ/ㄷ/ㄱ because each alone is rare.
STOPS = {"lenis": {"p": "B", "t": "D", "k": "G"},
         "tense": {"p" + TENSE: "BB", "t" + TENSE: "DD", "k" + TENSE: "GG"},
         "asp": {"pʰ": "Ph", "tʰ": "Th", "kʰ": "Kh"}}
PLACE = {ipa: ipa[0] for kind in STOPS.values() for ipa in kind}                 # 'p͈' -> 'p'
SYMBOL = {(kind, ipa[0]): sym for kind, m in STOPS.items() for ipa, sym in m.items()}
VOWEL_CHECKS = {"ㅓ_as_ㅗ": ("ʌ", "o"), "ㅗ_as_ㅓ": ("o", "ʌ"), "ㅡ_as_ㅜ": ("ɯ", "u"), "ㅜ_as_ㅡ": ("u", "ɯ")}
STOP_CHECKS = {f"{a}_as_{b}": (a, b) for a in STOPS for b in STOPS if a != b}
CHECKS = {**VOWEL_CHECKS, **STOP_CHECKS}
# The jamo the spelling must show for the sound to be checked
SPELLED = {"ʌ": "ㅓ", "o": "ㅗ", "ɯ": "ㅡ", "u": "ㅜ",
           "p": "ㅂ", "t": "ㄷ", "k": "ㄱ", "p" + TENSE: "ㅃ", "t" + TENSE: "ㄸ", "k" + TENSE: "ㄲ",
           "pʰ": "ㅍ", "tʰ": "ㅌ", "kʰ": "ㅋ"}


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


def _spelled(words):
    """(wi, pi) -> the jamo the spelling has for that sound (None when spelling and sound don't line up)."""
    out = {}
    for wi, w in enumerate(words):
        if not w["phonemes"]:
            continue
        for pi, src in enumerate(korean_sources(w["word"], w["pron"])):
            out[(wi, pi)] = src["jamo"]
    return out


def candidates(words):
    """Every (sound, possible mistake) the app may check, with the symbols to compare.
    -> [{"wi", "pi", "check", "target_tok", "said_tok", "position"}, ...]"""
    tok_at = {key: tok for tok, cover in to_mfa(words) if len(cover) == 1 for key in cover}
    spelled = _spelled(words)
    out = []
    for wi, w in enumerate(words):
        for pi, p in enumerate(w["phonemes"]):
            tok = tok_at.get((wi, pi))
            if tok is None or SPELLED.get(p) is None or spelled.get((wi, pi)) != SPELLED[p]:
                continue      # glide symbol, not a checked sound, or the spelling doesn't show this sound
            position = "initial" if pi == 0 else "inside"
            for name, (target, said) in VOWEL_CHECKS.items():
                if p == target and tok == VOW[p]:
                    out.append(dict(wi=wi, pi=pi, check=name, target_tok=tok, said_tok=VOW[said], position=position))
            for name, (kind, other) in STOP_CHECKS.items():
                if p in STOPS[kind] and tok == STOPS[kind][p]:      # a released stop (not a final 밥's ㅂ)
                    out.append(dict(wi=wi, pi=pi, check=name, target_tok=tok, said_tok=SYMBOL[(other, PLACE[p])],
                                    position=position))
    return out


def fires(row, cut):
    """Red only when the model is far from native AND wrote the specific wrong sound itself."""
    return float(row["margin"]) > cut and int(row["heard_said"]) == 1


# ---------- 3. the model ----------
@cache
def _model():
    from huggingface_hub import hf_hub_download
    from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC
    vocab = json.load(open(hf_hub_download(MODEL, "vocab.json", revision=REVISION), encoding="utf-8"))
    assert MFA_VOCAB <= set(vocab), MFA_VOCAB - set(vocab)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL, revision=REVISION).eval()
    return Wav2Vec2FeatureExtractor.from_pretrained(MODEL, revision=REVISION), model, vocab


def emissions(audio, sr):
    """-> log probabilities [frames, symbols]. Same steps as backend/align.py, other model."""
    import torch
    import torchaudio.functional as F
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    wav = torch.from_numpy(audio)
    if sr != SR:
        wav = F.resample(wav, sr, SR)
    fe, model, _ = _model()
    inputs = fe(wav.numpy(), sampling_rate=SR, return_tensors="pt")
    with torch.inference_mode():
        return model(inputs.input_values).logits.log_softmax(-1)[0]


def _force(lp, words):
    """Forced alignment with THIS model. -> (pairs from to_mfa, one merged span per symbol, with .score 0..1)."""
    import torch
    import torchaudio.functional as F
    _, model, vocab = _model()
    pairs = to_mfa(words)
    ids = [vocab[t] for t, _ in pairs]
    if not ids:
        raise ValueError("no Korean sounds in this sentence")
    if lp.shape[0] < len(ids) + sum(a == b for a, b in zip(ids, ids[1:])):
        raise ValueError("recording too short for this sentence")
    blank = model.config.pad_token_id
    labels, scores = F.forced_align(lp.unsqueeze(0), torch.tensor([ids], dtype=torch.int32), blank=blank)
    # blank= matters: merge_tokens assumes blank id 0, but in THIS model id 0 is the vowel A (blank is 42).
    spans = F.merge_tokens(labels[0], scores[0].exp(), blank=blank)
    assert len(spans) == len(ids), (len(spans), len(ids))
    return pairs, spans


def align_ko(lp, words):
    """Forced alignment with THIS model. -> (frame window per (wi, pi), symbol index per (wi, pi), symbols)."""
    pairs, spans = _force(lp, words)
    toks = [t for t, _ in pairs]
    # Window = the gap between the neighbours' spans (capped at ~0.15 s each side), not just this symbol's own
    # frames: when the target is wrong, the aligner parks it on a frame NEXT TO the real sound (spike e).
    win, tok_of = {}, {}
    for i, ((_, cover), sp) in enumerate(zip(pairs, spans)):
        prev = spans[i - 1].end if i else 0
        nxt = spans[i + 1].start if i + 1 < len(spans) else lp.shape[0]
        f0 = max(prev, sp.start - MAX_EXTEND_FRAMES)
        f1 = max(f0 + 1, min(nxt, sp.end + MAX_EXTEND_FRAMES))
        for key in cover:
            win[key], tok_of[key] = (f0, f1), i
    return win, tok_of, toks


def greedy(lp):
    """The model's own transcription: best symbol per frame, repeats merged, blanks dropped."""
    _, model, vocab = _model()
    inv = {i: t for t, i in vocab.items()}
    best = lp.argmax(-1).tolist()
    blank = model.config.pad_token_id
    out = [inv[b] for i, b in enumerate(best) if (i == 0 or b != best[i - 1]) and b != blank]
    return [t for t in out if t in MFA_VOCAB]


def _seq_key(t):
    # align_sequences treats a symbol as a vowel if it starts with a vowel letter; keep each symbol unique
    return ("a" if t in VOW.values() or t in DIPH.values() else "C") + t


def heard_per_token(expected_toks, heard_toks):
    """For each expected symbol, what the free transcription has in its place (None = nothing)."""
    out = []
    for op, e, h in align_sequences([_seq_key(t) for t in expected_toks], [_seq_key(t) for t in heard_toks]):
        if op != "ins":
            out.append(h[1:] if h else None)
    return out


def measure_lp(lp, words):
    """Rows for every candidate check, from the model output of one recording."""
    cands = candidates(words)
    if not cands:
        return []
    probs = lp.exp()
    win, tok_of, toks = align_ko(lp, words)
    in_place = heard_per_token(toks, greedy(lp))
    vocab = _model()[2]
    rows = []
    for c in cands:
        f0, f1 = win[(c["wi"], c["pi"])]
        peak = lambda t: probs[f0:f1, vocab[t]].max().item()
        rows.append(dict(wi=c["wi"], pi=c["pi"], check=c["check"], position=c["position"],
                         margin=round(peak(c["said_tok"]) - peak(c["target_tok"]), 4),
                         heard_said=int(in_place[tok_of[(c["wi"], c["pi"])]] == c["said_tok"])))
    return rows


def measure(audio, sr, words):
    return measure_lp(emissions(audio, sr), words)


# ---------- 4. "did you say it?" evidence from this model ----------
# The same two numbers backend/match.py uses with the main listener, per word:
#   heard = share of the word's symbols the free transcription has in their place (exactly that symbol)
#   conf  = the aligner's average confidence for those symbols (0..1)
# plus missing = share with nothing in their place. A symbol that covers a glide + vowel (iA) counts once.
def pool_evidence(pairs, scores, in_place, n_words):
    """pairs = to_mfa(words); scores = each symbol's alignment score; in_place = heard_per_token(). -> one dict per word."""
    per = [dict(n=0, heard=0.0, missing=0.0, conf=0.0) for _ in range(n_words)]
    for (tok, cover), sc, h in zip(pairs, scores, in_place):
        f = per[cover[0][0]]
        f["n"] += 1
        f["heard"] += h == tok
        f["missing"] += h is None
        f["conf"] += float(sc)
    for f in per:
        if f["n"]:
            for k in ("heard", "missing", "conf"):
                f[k] /= f["n"]
    return per


def sentence_evidence(per):
    """The whole sentence: every symbol counts the same (words weighted by their number of symbols)."""
    n = sum(f["n"] for f in per)
    if not n:
        return dict(n=0, heard=0.0, missing=0.0, conf=0.0)
    return dict(n=n, **{k: sum(f[k] * f["n"] for f in per) / n for k in ("heard", "missing", "conf")})


def word_evidence(lp, words, heard=None):
    """-> (pool_evidence per word, how many symbols the free transcription has). heard: greedy(lp), if already known."""
    pairs, spans = _force(lp, words)
    heard = greedy(lp) if heard is None else heard
    in_place = heard_per_token([t for t, _ in pairs], heard)
    return pool_evidence(pairs, [sp.score for sp in spans], in_place, len(words)), len(heard)
