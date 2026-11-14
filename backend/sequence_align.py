"""Line up the EXPECTED phonemes against the phonemes the model HEARD.

    align_sequences(["b","ɔː","l","z"], ["b","oː","z"])
    -> [("match","b","b"), ("sub","ɔː","oː"), ("del","l",None), ("match","z","z")]

Plain-words version: find the cheapest "story" of edits that turns what should have been said into
what was heard. Edits: keep a sound (free), swap it (sub), drop it (del), or add an extra one (ins).
This is edit distance (Levenshtein), the same calculation behind word error rate in speech recognition.

How it finds the cheapest story without trying millions of them (dynamic programming):
  cost[i][j] = cheapest way to turn the first i expected sounds into the first j heard sounds.
  Every cell only needs three neighbours that are already filled in:
      up-left  cost[i-1][j-1] + swap/keep expected[i-1] for heard[j-1]
      up       cost[i-1][j]   + drop expected[i-1]
      left     cost[i][j-1]   + add heard[j-1]
  Fill the grid top-left to bottom-right; the bottom-right cell is the cheapest total.
  Then walk back from that corner, each time stepping to the neighbour that produced the cell's value;
  the steps you take, reversed, are the line-up.

Costs (hand-set; learned costs would be better): keep 0, drop 1, add 1, swap 1 within the same kind
(vowel for vowel, consonant for consonant), swap 1.5 across kinds. The 1.5 makes "b ɔː l z" vs "b oː z"
come out as "ɔː became oː and the L was dropped", not "ɔː was dropped and the L became oː".
Costs are multiples of 0.5, which floats store exactly, so the == checks in the walk back are safe.

Compare symbols from the same set: align.model_symbol(expected) vs recognize() output.
"""
VOWEL_CHARS = set("aeiouæɑɒɔəɚɛɜɪʊʌɯɤøœyʏɐɘɵɨʉ")  # a symbol is a vowel if it STARTS with one (oʊ, iː, ɑːɹ)
DROP = 1.0
ADD = 1.0
SWAP_SAME_KIND = 1.0
SWAP_OTHER_KIND = 1.5


def is_vowel(sym):
    return sym[0] in VOWEL_CHARS


def swap_cost(expected_sym, heard_sym):
    if expected_sym == heard_sym:
        return 0.0
    return SWAP_SAME_KIND if is_vowel(expected_sym) == is_vowel(heard_sym) else SWAP_OTHER_KIND


def align_sequences(expected, heard):
    """-> list of (op, expected_sym, heard_sym), op in match/sub/del/ins, in sentence order."""
    n, m = len(expected), len(heard)

    # 1. Fill the grid. Row 0 / column 0: turning something into nothing (all drops) or nothing into
    #    something (all adds).
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i * DROP
    for j in range(1, m + 1):
        cost[0][j] = j * ADD
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i][j] = min(cost[i - 1][j - 1] + swap_cost(expected[i - 1], heard[j - 1]),
                             cost[i - 1][j] + DROP,
                             cost[i][j - 1] + ADD)

    # 2. Walk back from the bottom-right corner to the top-left, recording each step.
    steps, i, j = [], n, m
    while i > 0 or j > 0:
        e = expected[i - 1] if i > 0 else None
        h = heard[j - 1] if j > 0 else None
        if i > 0 and j > 0 and cost[i][j] == cost[i - 1][j - 1] + swap_cost(e, h):
            steps.append(("match" if e == h else "sub", e, h))
            i, j = i - 1, j - 1
        elif i > 0 and cost[i][j] == cost[i - 1][j] + DROP:
            steps.append(("del", e, None))
            i -= 1
        else:
            steps.append(("ins", None, h))
            j -= 1
    return steps[::-1]  # we walked backwards, so reverse into sentence order
