"""Spike (d): does forced alignment give sensible per-phoneme times?

For each L2-ARCTIC sentence:
  1. text -> expected phonemes (g2p_en, ARPAbet -> IPA)
  2. audio -> wav2vec2 phoneme model -> per-frame probabilities (20 ms frames)
  3. torchaudio forced_align -> start/end time for every expected phoneme
  4. compare our times with the HUMAN-marked times in L2-ARCTIC's annotation files

Run:  python spikes/d_align.py
Throwaway feasibility code. Not part of the app.
"""
import re
import statistics
import sys
from pathlib import Path

import soundfile as sf
import torch
import torchaudio.functional as F
from g2p_en import G2p
from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

MODEL = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"  # multilingual IPA phoneme recognizer
DATA = Path("data/l2arctic")
SENTENCES = [("HKK", "arctic_a0003"), ("HKK", "arctic_a0005"), ("HKK", "arctic_a0020")]
MAX_EXTEND = 0.15  # seconds; a guess for the 'capped' rule, not tuned (tuning on 3 sentences would overfit)

# ARPAbet (what g2p_en gives) -> IPA (what the model's vocabulary uses)
ARPA2IPA = {
    "AA": "ɑː", "AE": "æ", "AH": "ʌ", "AO": "ɔː", "AW": "aʊ", "AY": "aɪ", "B": "b", "CH": "tʃ",
    "D": "d", "DH": "ð", "EH": "ɛ", "ER": "ɚ", "EY": "eɪ", "F": "f", "G": "ɡ", "HH": "h",
    "IH": "ɪ", "IY": "iː", "JH": "dʒ", "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ",
    "OW": "oʊ", "OY": "ɔɪ", "P": "p", "R": "ɹ", "S": "s", "SH": "ʃ", "T": "t", "TH": "θ",
    "UH": "ʊ", "UW": "uː", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}


def to_ipa(arpa):
    """'AH0' -> 'ə' (unstressed AH is schwa); otherwise drop the stress digit and look it up."""
    if arpa == "AH0":
        return "ə"
    return ARPA2IPA[re.sub(r"\d", "", arpa)]


def read_tier(textgrid_path, tier_name):
    """Return [(start, end, label), ...] for one tier of a Praat TextGrid, skipping empty labels."""
    text = Path(textgrid_path).read_text(encoding="utf-8", errors="replace")
    tier = text.split(f'name = "{tier_name}"')[1].split("item [")[0]
    rows = re.findall(r'xmin = ([\d.]+)\s*xmax = ([\d.]+)\s*text = "([^"]*)"', tier)
    return [(float(a), float(b), lab.strip()) for a, b, lab in rows if lab.strip() not in ("", "sil", "sp")]


def main():
    print(f"Loading {MODEL} (first run downloads about 1.3 GB)...")
    extractor = Wav2Vec2FeatureExtractor.from_pretrained(MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    vocab = {tok: i for i, tok in enumerate(_vocab_list(model))}
    blank = model.config.pad_token_id
    g2p = G2p()

    errors = {"word starts": [], "phone starts": []}
    errors.update({f"word ends ({r})": [] for r in ("blip", "to_next", "capped")})
    for speaker, utt in SENTENCES:
        wav_path = DATA / speaker / "wav" / f"{utt}.wav"
        text = (DATA / speaker / "transcript" / f"{utt}.txt").read_text().strip()

        # 1. Expected phonemes, remembering which word each phoneme belongs to
        phones, word_of_phone, words = [], [], []
        for w in text.split():
            words.append(w)
            for p in g2p(w):
                if p[0].isalpha():
                    phones.append(to_ipa(p))
                    word_of_phone.append(len(words) - 1)

        # 2. Audio -> 16 kHz -> model -> log-probabilities per 20 ms frame
        audio, sr = sf.read(wav_path, dtype="float32")
        audio16 = F.resample(torch.from_numpy(audio), sr, 16000)
        inputs = extractor(audio16.numpy(), sampling_rate=16000, return_tensors="pt")
        with torch.inference_mode():
            log_probs = model(inputs.input_values).logits.log_softmax(-1)
        sec_per_frame = len(audio16) / 16000 / log_probs.shape[1]

        # What the model hears on its own (greedy decode), for comparison
        best = log_probs[0].argmax(-1).tolist()
        heard = [inv for i, t in enumerate(best) if t != blank and (i == 0 or t != best[i - 1])
                 for inv in [_vocab_list(model)[t]]]

        # 3. Forced alignment: force the EXPECTED phonemes onto the audio
        targets = torch.tensor([[vocab[p] for p in phones]], dtype=torch.int32)
        frame_labels, frame_scores = F.forced_align(log_probs, targets, blank=blank)
        spans = F.merge_tokens(frame_labels[0], frame_scores[0].exp())

        print(f"\n=== {speaker}/{utt}: \"{text}\"")
        print("expected:", " ".join(phones))
        print("heard:   ", " ".join(heard))
        starts = [s.start * sec_per_frame for s in spans]
        blip_ends = [s.end * sec_per_frame for s in spans]
        ends_by_rule = {
            # end = where the model's blip stops (run 1)
            "blip": blip_ends,
            # end = the next phone's start (fills the gap; but a pause gets glued onto the phone before it)
            "to_next": starts[1:] + [blip_ends[-1]],
            # same, but a phone can't run more than MAX_EXTEND past its blip (so pauses aren't swallowed)
            "capped": [min(nxt, be + MAX_EXTEND) for nxt, be in zip(starts[1:] + [blip_ends[-1]], blip_ends)],
        }

        print(f"{'phone':>6} {'word':<12} {'start':>6} {'end':>6} {'conf':>5}   (end = 'capped' rule)")
        for p, wi, st, en, s in zip(phones, word_of_phone, starts, ends_by_rule["capped"], spans):
            flag = "  <- low" if s.score < 0.5 else ""
            print(f"{p:>6} {words[wi]:<12} {st:6.2f} {en:6.2f} {s.score:5.2f}{flag}")

        # 4. Compare with the human annotation: word starts, word ends (per rule), phone starts
        human_words = read_tier(DATA / speaker / "annotation" / f"{utt}.TextGrid", "words")
        first = [word_of_phone.index(wi) for wi in range(len(words))]
        last = [len(word_of_phone) - 1 - word_of_phone[::-1].index(wi) for wi in range(len(words))]
        if len(human_words) == len(words):
            errors["word starts"] += [abs(starts[f] - h[0]) * 1000 for f, h in zip(first, human_words)]
            for rule, ends in ends_by_rule.items():
                errors[f"word ends ({rule})"] += [abs(ends[l] - h[1]) * 1000 for l, h in zip(last, human_words)]
        else:
            print(f"(word counts differ: human {len(human_words)} vs ours {len(words)}; skipped)")
        human_phones = read_tier(DATA / speaker / "annotation" / f"{utt}.TextGrid", "phones")
        if len(human_phones) == len(phones):
            errors["phone starts"] += [abs(st - h[0]) * 1000 for st, h in zip(starts, human_phones)]
        else:
            print(f"(phone counts differ: human {len(human_phones)} vs ours {len(phones)}; phone starts skipped)")

    print("\nBoundary error vs human annotation (ms):")
    print(f"{'what':<22} {'n':>4} {'median':>7} {'<=50ms':>7} {'max':>5}")
    for what, e in errors.items():
        if e:
            print(f"{what:<22} {len(e):>4} {statistics.median(e):7.0f} {sum(x <= 50 for x in e) / len(e):7.0%} {max(e):5.0f}")


_VOCAB = None


def _vocab_list(model):
    """Model's token list in id order (read from the tokenizer's vocab.json, no phonemizer needed)."""
    global _VOCAB
    if _VOCAB is None:
        import json
        from huggingface_hub import hf_hub_download
        v = json.load(open(hf_hub_download(MODEL, "vocab.json")))
        _VOCAB = [tok for tok, _ in sorted(v.items(), key=lambda kv: kv[1])]
    return _VOCAB


if __name__ == "__main__":
    sys.exit(main())
