"""WHEN each word and sound happens in a mixed English + Korean native clip: hybrid alignment.

    words = align_mixed(samples, sr, expected_phonemes("I really want to eat 떡볶이 tonight.", "mix"))
    -> the same shape as align.align(), every word also tagged "lang"

Why not just run each language's model on its own words over the whole clip? Because the aligner MUST place every
word it is given somewhere. With Korean in the middle, the English-only run squeezed "to eat" into 떡볶이's audio,
and the Korean-only run stretched 떡볶이 over "want to eat" (both confident, both wrong, overlapping).

The hybrid, in three moves:
  1. One pass with the original multilingual model (it knows both languages' sounds) over ALL the words. Its
     times are good enough to say where each language run sits.
  2. Cut the clip in the gap between runs. Each piece gets a little extra audio on both sides (PAD) so the model
     sees the edges of its first and last sound in context.
  3. Align each piece with its OWN language's model (English: the fine-tuned listener when its files are present;
     Korean: the original), shift the times back by where the piece starts, and keep them inside the piece's own
     stretch [lo, hi], so two runs can never overlap.
If a piece's model can't align it (e.g. the piece is too short), that run keeps the one-pass times.
"""
from dataclasses import dataclass

from backend.align import align, emissions
from backend.listener import MODEL, listener_id, live_listener

PAD = 0.1   # s of extra audio either side of a piece (context for the model; times are clipped back to the piece)


def model_id():
    """Saved next to the timings: a change of either language's listener redoes them."""
    return f"hybrid:{listener_id(MODEL)}|en={listener_id(live_listener('en'))}|ko={listener_id(live_listener('ko'))}"


@dataclass
class Piece:
    lang: str
    words: list   # indexes into the sentence's word list
    lo: float     # this piece OWNS [lo, hi] of the clip: its times are kept inside it
    hi: float
    a: float      # the audio actually cut out: [lo - pad, hi + pad], inside the clip
    b: float


def plan_pieces(first, duration, pad=PAD):
    """One-pass words (each with "lang", "start", "end") -> one Piece per run of same-language words.
    The cut between two runs is the middle of the gap between them."""
    groups = []
    for i, w in enumerate(first):
        if groups and groups[-1][0] == w["lang"]:
            groups[-1][1].append(i)
        else:
            groups.append((w["lang"], [i]))
    cuts = [0.0] + [round((first[g[-1]]["end"] + first[h[0]]["start"]) / 2, 3)
                    for (_, g), (_, h) in zip(groups, groups[1:])] + [round(duration, 3)]
    return [Piece(lang, idx, lo, hi, round(max(0.0, lo - pad), 3), round(min(duration, hi + pad), 3))
            for (lang, idx), lo, hi in zip(groups, cuts, cuts[1:])]


def place(local, piece):
    """A piece's own times (0 = the piece's first sample) -> clip times, kept inside [lo, hi]."""
    def clip_time(t):
        return round(min(max(t + piece.a, piece.lo), piece.hi), 3)
    out = []
    for w in local:
        phonemes = [{**p, "start": clip_time(p["start"]), "end": clip_time(p["end"])} for p in w["phonemes"]]
        out.append({**w, "lang": piece.lang, "phonemes": phonemes,
                    "start": phonemes[0]["start"], "end": phonemes[-1]["end"]})
    return out


def align_piece(samples, sr, words, lang):
    """One piece, aligned by its own language's live listener."""
    return align(emissions(samples, sr, lang), words, lang)


def hybrid(samples, sr, first, align_piece=align_piece):
    """Moves 2 and 3: cut at the one-pass borders, realign each piece by its language, shift back, combine."""
    out = []
    for piece in plan_pieces(first, len(samples) / sr):
        own = [first[i] for i in piece.words]
        expected = [{"word": w["word"], "pron": w.get("pron", ""), "phonemes": [p["ipa"] for p in w["phonemes"]]}
                    for w in own]
        try:
            local = align_piece(samples[int(piece.a * sr): int(piece.b * sr)], sr, expected, piece.lang)
        except ValueError:
            out += own   # this model couldn't place them: keep the one-pass times
            continue
        out += place(local, piece)
    return out


def align_mixed(samples, sr, words):
    """Move 1 (one multilingual pass over everything), then the hybrid."""
    first = align(emissions(samples, sr, model=MODEL), words, "mix")
    return hybrid(samples, sr, first)
