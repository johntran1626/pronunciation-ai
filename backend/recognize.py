"""'What was said': the phonemes the model hears, with NO expected text forced on it.

    heard = recognize(emissions(audio, sr))   # same Emissions as align(): the model runs once
    -> [{"symbol": "k", "start": 0.02, "end": 0.06, "conf": 0.91}, ...]

Greedy CTC decoding: (1) take the most likely symbol in every 20 ms frame, (2) merge runs of the same
symbol, (3) drop blanks. A blank between two identical symbols keeps both ('n _ n' = two n's).
Symbols are the MODEL's (ㅓ comes out as ɔ, ㅐ and ㅔ both as e); compare against
align.model_symbol(expected), not the textbook IPA. The model is multilingual and unrestricted, so it
can hear symbols from other languages; that is information, not an error.
"""
from backend.align import _model, vocab

SPECIAL = {"<s>", "</s>", "<unk>", "<pad>"}  # <pad> is the CTC blank


def recognize(em):
    symbol_of = {i: s for s, i in vocab().items()}
    probs = em.log_probs.exp()
    best = probs.argmax(-1).tolist()          # (1) top symbol per frame
    blank = _model(em.model)[1].config.pad_token_id

    heard, i = [], 0
    while i < len(best):
        j = i
        while j < len(best) and best[j] == best[i]:
            j += 1                            # (2) frames i..j-1 are one run of the same symbol
        sym = symbol_of[best[i]]
        if best[i] != blank and sym not in SPECIAL:   # (3) blanks and special tokens aren't sounds
            conf = probs[i:j, best[i]].mean().item()
            heard.append({"symbol": sym, "start": round(i * em.sec_per_frame, 3),
                          "end": round(j * em.sec_per_frame, 3), "conf": round(conf, 3)})
        i = j
    return heard
