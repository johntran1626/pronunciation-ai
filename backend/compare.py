"""Attach what was HEARD to each EXPECTED phoneme, using sequence_align's line-up.

    words, extra_at_start = attach_heard(align(...), recognize(...), lang)
    each expected phoneme gains:
        target_symbol  the model's symbol for it (ㅓ ʌ -> ɔ), which is what we compare against
        op             "match" | "sub" | "del"
        heard          what was heard in its place (None if dropped)
        extra_after    sounds heard right AFTER it that weren't expected, e.g. ["ɯ"] for "bus-eu"
    extra_at_start = extra sounds before the first expected one (often a breath or a click)

Why compare in the model's symbols: the recognizer has no ʌ for Korean ㅓ, it writes ɔ (spikes/a_vowels.py).
Comparing textbook ʌ to heard ɔ would mark every native speaker wrong.
"""
import copy

from backend.align import model_symbol
from backend.sequence_align import align_sequences


def attach_heard(words, heard, lang):
    words = copy.deepcopy(words)                         # don't change the caller's data
    flat = [p for w in words for p in w["phonemes"]]     # every expected phoneme, in sentence order
    for p in flat:
        p["target_symbol"] = model_symbol(p["ipa"], lang)
        p["extra_after"], p["extra_after_conf"] = [], []

    steps = align_sequences([p["target_symbol"] for p in flat], [h["symbol"] for h in heard])

    k = 0                     # index of the next expected phoneme to fill in
    j = 0                     # index of the next heard sound
    extra_at_start = []
    for op, _, h in steps:
        if op == "ins":       # an extra sound: hang it on the expected phoneme just before it
            if k > 0:
                flat[k - 1]["extra_after"].append(h)
                flat[k - 1]["extra_after_conf"].append(heard[j]["conf"])
            else:
                extra_at_start.append(h)
            j += 1
        else:                 # match / sub / del all use up one expected phoneme
            flat[k]["op"], flat[k]["heard"] = op, h
            k += 1
            j += op != "del"  # a deletion uses no heard sound
    return words, extra_at_start
