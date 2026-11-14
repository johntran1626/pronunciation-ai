"""Forced-alignment wrapper: audio + expected phonemes -> a start/end time per phoneme and per word.

    em = emissions(audio, sr)                                   # run the model ONCE per recording
    words = align(em, expected_phonemes(text, lang), lang)      # force the expected phonemes onto it
    -> [{"word", "pron", "start", "end", "phonemes": [{"ipa", "start", "end", "conf"}, ...]}, ...]

How it works (validated in spikes/d_align.py):
  1. wav2vec2 (multilingual phoneme recognizer) turns 16 kHz audio into "emissions": for every 20 ms
     frame, a log-probability for each of its 392 symbols.
  2. torchaudio's forced_align finds the most likely path through those frames that says EXACTLY the
     expected phonemes, in order (CTC: the model may also output 'blank' between them).
  3. Each phoneme lands on a short spike of 1-2 frames (CTC is "peaky"). Start = the spike's start.
     End = the next phoneme's start, but no more than 150 ms past the spike, so a pause isn't glued on.
  4. conf = the model's average probability for that phoneme over its spike frames (0..1).

Accuracy (spikes/d_align.py, English, 3 sentences): word starts are a median of 42 ms off the L2-ARCTIC times.
"""
import json
from dataclasses import dataclass
from functools import cache

import numpy as np
import torch
import torchaudio.functional as F

from backend.listener import LISTENER_ENV, MODEL, listener, listener_tag  # noqa: F401 (re-exported)

SR = 16000          # the model was trained on 16 kHz audio
MAX_EXTEND = 0.15   # s; a phoneme can't run more than this past its spike (the 'capped' rule from spikes/d_align.py, untuned)
MIN_SECONDS = 0.1   # shorter clips are too short for the model's first layers

# Korean textbook IPA -> the symbol the model actually uses, FOR ALIGNMENT ONLY (found in spikes/a_vowels.py).
# The model writes ㅓ as ɔ, ㅡ as ə, ㅈ as dʒ, ㅊ as tʃ, ㄹ as r, ㅐ as e, and has no tense or ʰ-aspirated
# Korean symbols. Forcing symbols it never uses gave poor alignment confidence. Scoring still
# uses the textbook IPA, so the target stays "ㅃ" even though alignment searched for "p".
T = "͈"  # tense mark
KO_MODEL_SYMBOL = {
    "ʌ": "ɔ", "ɯ": "ə", "ɰ": "ə", "ɛ": "e", "ɾ": "r",
    "tɕ": "dʒ", "tɕʰ": "tʃ", "kʰ": "k", "tʰ": "t", "pʰ": "p",
    "k" + T: "k", "t" + T: "t", "p" + T: "p", "s" + T: "s", "t" + T + "ɕ": "dʒ",
}


@dataclass
class Emissions:
    log_probs: torch.Tensor   # (frames, 392) log-probabilities
    sec_per_frame: float      # about 0.02
    duration: float           # seconds of audio


@cache
def _model():
    """Load the model once (1.26 GB; slow the first time), on CPU (no GPU needed at this scale)."""
    from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC
    name = listener()
    model = Wav2Vec2ForCTC.from_pretrained(name).eval()
    if model.config.vocab_size != len(vocab()):   # a listener with other symbols would make every id wrong
        raise ValueError(f"{name} has {model.config.vocab_size} output symbols, the vocab has {len(vocab())}")
    return Wav2Vec2FeatureExtractor.from_pretrained(name), model


@cache
def vocab():
    """Symbol -> id, read from the model's vocab.json (no phonemizer/espeak install needed)."""
    from huggingface_hub import hf_hub_download
    return json.load(open(hf_hub_download(MODEL, "vocab.json"), encoding="utf-8"))


def model_symbol(ipa, lang):
    """Textbook IPA -> the model's symbol. English IPA from g2p.py already uses the model's symbols."""
    return KO_MODEL_SYMBOL.get(ipa, ipa) if lang == "ko" else ipa


def emissions(audio, sr):
    """Raw samples (any rate, mono or stereo) -> Emissions. This is the slow part (~1 s per sentence on CPU)."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)  # stereo -> mono
    wav = torch.from_numpy(audio)
    if sr != SR:
        wav = F.resample(wav, sr, SR)
    duration = len(wav) / SR
    if duration < MIN_SECONDS:
        raise ValueError(f"recording is {duration:.2f} s; too short to analyze")
    extractor, model = _model()
    inputs = extractor(wav.numpy(), sampling_rate=SR, return_tensors="pt")  # normalizes volume
    with torch.inference_mode():
        log_probs = model(inputs.input_values).logits.log_softmax(-1)[0]
    return Emissions(log_probs, duration / log_probs.shape[0], duration)


def align(em, words, lang):
    """Force the expected phonemes (from g2p.expected_phonemes) onto the audio. Returns new dicts with times."""
    flat = [(wi, p) for wi, w in enumerate(words) for p in w["phonemes"]]
    ids = [vocab()[model_symbol(p, lang)] for _, p in flat]

    # CTC needs one frame per phoneme, plus a blank frame between two identical phonemes in a row.
    needed = len(ids) + sum(a == b for a, b in zip(ids, ids[1:]))
    if em.log_probs.shape[0] < needed:
        raise ValueError(f"recording ({em.duration:.1f} s) is too short for this sentence")

    blank = _model()[1].config.pad_token_id
    targets = torch.tensor([ids], dtype=torch.int32)
    frame_labels, frame_scores = F.forced_align(em.log_probs.unsqueeze(0), targets, blank=blank)
    spans = F.merge_tokens(frame_labels[0], frame_scores[0].exp())  # one span per expected phoneme

    starts = [s.start * em.sec_per_frame for s in spans]
    spike_ends = [s.end * em.sec_per_frame for s in spans]
    ends = [min(nxt, se + MAX_EXTEND) for nxt, se in zip(starts[1:], spike_ends)] + [spike_ends[-1]]

    out = [{"word": w["word"], "pron": w["pron"], "phonemes": []} for w in words]
    for (wi, ipa), st, en, span in zip(flat, starts, ends, spans):
        out[wi]["phonemes"].append({"ipa": ipa, "start": round(st, 3), "end": round(en, 3),
                                    "conf": round(float(span.score), 3)})
    for w in out:
        w["start"], w["end"] = w["phonemes"][0]["start"], w["phonemes"][-1]["end"]
    return out
