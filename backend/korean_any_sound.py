"""The every-sound Korean check: any expected Korean sound said as ANOTHER Korean sound, or left out, turns red.

The same idea as the English one (backend/any_sound.py), with the Korean-trained listener (korean_listener.py),
whose 40 symbols are the units here (ㅕ = iEO is one symbol; ㅐ and ㅔ are both E):
  1. Forced alignment with that listener gives each expected symbol a time window.
  2. right  = the listener's best frame for the RIGHT symbol in that window (0..1)
     rival  = its best frame for any OTHER symbol that is not a normal native variant
     margin = rival - right (-1..1). Past the cut-off -> the sound was probably replaced by the rival.
  3. It was also probably replaced when the free transcription wrote another symbol there AND the right one barely
     shows up. If the free transcription has nothing there AND the right one barely shows up, it was left out.
Three cut-offs decide "clearly" and "barely": eval/korean_any_sound.py measures them on native Korean readers and
on English-speaking learners the listener never trained on (results/korean_any_sound.json).

What is never a mistake (linguistic rules fixed before any run, not fitted numbers):
  - the spelled sound where a sound rule made a tense or aspirated one: 학교 [학꾜] with a plain ㄱ, 좋다 [조타]
    with a plain ㄷ (the earlier Korean checks skipped these sounds for the same reason: natives vary)
  - ㅢ said as ㅣ, ㅔ or ㅡ; ㅖ said as ㅔ after a consonant other than ㄹ (Standard Pronunciation, Article 5)
  - a final unreleased ㄱ ㄷ ㅂ heard released at the same place
  - the second ㄹ of ㄹㄹ (빨리) heard as R: our G2P writes [l l], the listener's training labels write L R (a
    notation difference, found on the smoke run before the full one)
  - a ㄹ our G2P links over from the previous word (책을 읽었다 -> 채그 릴걷따) said as a final L: a native who
    pauses between the words doesn't link it (found on the TUNE natives, before the test speakers were read)
  - ㅎ fading out between voiced sounds (전화 said 저놔), a common native weakening (described in Korean phonetics
    texts; exact citation not yet checked)
Words whose spelling and pronunciation don't line up syllable by syllable (digits read out) are not graded.
"""
import copy
import json
from functools import cache
from pathlib import Path

import numpy as np

from backend.korean_listener import CONS, DIPH, MFA_VOCAB, VOW, _model, _spelled, force_pairs, greedy, heard_per_token, \
    to_mfa, windows

THRESHOLDS_FILE = Path(__file__).with_name("korean_any_sound_thresholds.json")   # written by eval/korean_any_sound.py
SWAP, MISSING = "sound_swap", "sound_missing"
SYMBOLS = sorted(MFA_VOCAB)
TOP = 5                                   # how many best other symbols each row keeps
VOWEL_TOKS = frozenset(VOW.values()) | frozenset(DIPH.values())
RELEASED = {"k": {"G", "GG", "Kh"}, "t": {"D", "DD", "Th"}, "p": {"B", "BB", "Ph"}}   # unreleased final -> same place
VOICED = VOWEL_TOKS | {"N", "M", "NG", "L", "R"}
PLAIN_OF = {"GG": "G", "Kh": "G", "DD": "D", "Th": "D", "BB": "B", "Ph": "B", "SS": "S", "JJ": "J", "CHh": "J"}
PLAIN_JAMO = {"G": "ㄱ", "D": "ㄷ", "B": "ㅂ", "S": "ㅅ", "J": "ㅈ"}


# ---------- the rules ----------
def accepted(r, other):
    """True when saying `other` for r["target"] is a normal NATIVE way of saying it."""
    t = r["target"]
    if other in r.get("alt", ()):
        return True
    if t == "euI" and other in ("I", "E", "EU"):
        return True
    if t == "L" and other == "R" and r.get("prev") == "L":
        return True
    p = r.get("prev_in_word", "")
    if t == "R" and other == "L" and p == "" and r.get("prev") in VOWEL_TOKS:
        return True               # word-initial R after a vowel: in G2P output, almost always linked over
    if t == "iE" and other == "E" and p not in ("", "R", "L") and p not in VOWEL_TOKS:
        return True
    return t in RELEASED and other in RELEASED[t]


def dropped_ok(r):
    """A sound natives normally let fade: ㅎ between voiced sounds."""
    return r["target"] == "H" and r.get("prev") in VOICED and r.get("next") in VOICED


def rival(r):
    """-> (the best other symbol that is NOT a native variant, its margin over the right one); ("", -1.0) if none."""
    for sym, peak in r["others"]:
        if not accepted(r, sym):
            return sym, round(peak - r["right"], 4)
    return "", -1.0


def verdict(r, t):
    """-> (SWAP, the symbol probably said) | (MISSING, None) | None (no mistake found). t = the tuned thresholds."""
    if not t.get("enabled") or r.get("skip"):
        return None
    other, margin = rival(r)
    if margin > t["margin"]:
        return SWAP, other
    if r["op"] == "sub" and r["right"] < t["sub_right"] and not accepted(r, r["heard"]):
        return SWAP, r["heard"]
    if r["op"] == "del" and r["right"] < t["right"] and not dropped_ok(r):
        return MISSING, None
    return None


@cache
def load_thresholds():
    return json.loads(THRESHOLDS_FILE.read_text()) if THRESHOLDS_FILE.exists() else {"enabled": False}


# ---------- the context of each symbol ----------
def pair_context(pairs, alt=None):
    """Neighbours of each symbol: prev / next in the sentence, prev_in_word ("" at a word start). alt = {index: set}."""
    toks = [t for t, _ in pairs]
    out = []
    for i, (tok, cover) in enumerate(pairs):
        same_word = i and pairs[i - 1][1][0][0] == cover[0][0]
        out.append(dict(prev=toks[i - 1] if i else "", next=toks[i + 1] if i + 1 < len(toks) else "",
                        prev_in_word=toks[i - 1] if same_word else "", alt=set((alt or {}).get(i, ())), skip=False))
    return out


def context(words, pairs):
    """pair_context + what the spelling says. pairs = to_mfa(words)."""
    spelled = _spelled(words)
    alt = {}
    for i, (tok, cover) in enumerate(pairs):
        plain = PLAIN_OF.get(tok)
        if plain and spelled.get(cover[0]) == PLAIN_JAMO[plain]:
            alt[i] = {plain}             # a sound rule made it tense / aspirated; the spelling shows the plain one
    out = pair_context(pairs, alt)
    for c, (_, cover) in zip(out, pairs):
        wi = cover[0][0]
        c["skip"] = any(spelled.get((wi, pi)) is None for pi in range(len(words[wi]["phonemes"])))
    return out


# ---------- the evidence ----------
def rows_from(probs, symbols, pairs, wins, in_place, top=TOP):
    """One row per expected symbol. probs = [frames, len(symbols)] (0..1); wins = (f0, f1) per symbol;
    in_place = what the free transcription has at each symbol (None = nothing)."""
    probs = np.asarray(probs)
    col = {s: j for j, s in enumerate(symbols)}
    rows = []
    for i, ((tok, cover), (f0, f1), h) in enumerate(zip(pairs, wins, in_place)):
        peaks = probs[f0:f1].max(0)
        j = col[tok]
        order = [k for k in np.argsort(-peaks, kind="stable") if k != j][:top]
        rows.append(dict(index=i, cover=cover, target=tok, right=round(float(peaks[j]), 4),
                         others=[(symbols[k], round(float(peaks[k]), 4)) for k in order],
                         op="match" if h == tok else "del" if h is None else "sub", heard=h or ""))
    return rows


def evidence(lp, pairs, heard=None):
    """Rows for a symbol list, from the Korean listener's output lp. heard = greedy(lp), if already known.
    ValueError: this recording can't be aligned to these symbols."""
    spans = force_pairs(lp, pairs)
    vocab = _model()[2]
    probs = lp.exp()[:, [vocab[s] for s in SYMBOLS]].numpy()
    in_place = heard_per_token([t for t, _ in pairs], greedy(lp) if heard is None else heard)
    return rows_from(probs, SYMBOLS, pairs, windows(spans, lp.shape[0]), in_place)


def score_rows(lp, words, heard=None):
    """Evidence + context, one row per expected symbol. words = g2p.expected_phonemes(text, "ko")."""
    pairs = to_mfa(words)
    return [{**r, **c} for r, c in zip(evidence(lp, pairs, heard), context(words, pairs))]


def score(lp, words, t, heard=None):
    """-> {(word_index, phoneme_index): (SWAP, symbol said) | (MISSING, None)} for the red sounds.
    words = g2p.expected_phonemes(text, "ko"). A glide + vowel symbol marks both of its phonemes."""
    if not t.get("enabled"):
        return {}
    found = {}
    for r in score_rows(lp, words, heard):
        v = verdict(r, t)
        if v:
            for key in r["cover"]:
                found[key] = v
    return found


# ---------- in /analyze: coloring the words ----------
# The listener's symbols back to our IPA (= content/articulation.json's Korean keys; a glide + vowel = both, "jʌ").
# E is ㅐ and ㅔ at once (the listener merges them, like most Seoul speakers); it is written e (ㅔ).
IPA_OF = {**{sym: ipa for ipa, sym in CONS.items()}, **{sym: ipa for ipa, sym in VOW.items()},
          **{sym: g + v for (g, v), sym in DIPH.items()}, "E": "e", "iE": "je", "oE": "we", "k": "k", "t": "t", "p": "p"}
TIPS_FILE = Path(__file__).resolve().parent.parent / "content" / "tips.json"


def ipa_of(sym):
    return IPA_OF[sym]


@cache
def tip_pairs():
    """(target IPA, said IPA) -> the hand-written Korean tip for that mistake (content/tips.json)."""
    tips = json.loads(TIPS_FILE.read_text(encoding="utf-8"))["tips"]["ko"]
    return {(t["target"], t["produced"]): name for name, t in tips.items() if t.get("target") and t.get("produced")}


def heard_ok(r):
    """The free transcription has the right symbol, or a native variant of it, in this sound's place."""
    return r["op"] == "match" or (r["op"] == "sub" and accepted(r, r["heard"]))


def color(words, rows, t):
    """Color the words with the every-sound check (after korean_scoring.score_korean). rows = score_rows(). -> a copy.

    Per symbol (a glide + vowel symbol covers both of its sounds):
      - a mistake found -> red; pair = the hand-written tip for that exact mistake if there is one (ㅓ said ㅗ ->
        eo_as_o, plain ㅂ said ㅃ -> p_as_pp), else sound_swap / sound_missing; produced = what was probably said
      - no mistake AND the listener heard the right sound (or a native variant) there -> green
      - no mistake, but it heard something else or nothing -> left as it was: no proof either way (as in korean_scoring.py)
    A sound the live checks already made red keeps their verdict; a word marked not heard is left alone."""
    words = copy.deepcopy(words)
    if not t.get("enabled"):
        return words
    for r in rows:
        if r.get("skip") or any(wi >= len(words) or pi >= len(words[wi]["phonemes"]) for wi, pi in r["cover"]):
            continue
        if any(words[wi].get("not_heard") for wi, _ in r["cover"]):
            continue
        ps = [words[wi]["phonemes"][pi] for wi, pi in r["cover"]]
        unit = "".join(p["ipa"] for p in ps)
        v = verdict(r, t)
        if v:
            if any(p["status"] == "red" for p in ps):
                continue
            said = ipa_of(v[1]) if v[0] == SWAP else None
            pair = tip_pairs().get((unit, said), v[0])
            for p in ps:
                p.update(status="red", pair=pair, produced=said, checked=True)
                if len(ps) > 1:
                    p["unit"] = unit
        elif heard_ok(r):
            for p in ps:
                p["checked"] = True
                if p["status"] != "red":
                    p["status"] = "green"
    for w in words:
        statuses = [p["status"] for p in w["phonemes"]]
        w["status"] = "red" if "red" in statuses else "green" if "green" in statuses else "unchecked"
    return words


def apply_live(samples, sr, expected, words, t=None, lp=None):
    """/analyze's step for Korean: run the listener if lp isn't given, then color(). A recording this listener
    can't align (too short) gets no verdict from this check: the words come back as they were."""
    t = load_thresholds() if t is None else t
    if not t.get("enabled"):
        return words
    from backend.korean_listener import emissions
    try:
        rows = score_rows(emissions(samples, sr) if lp is None else lp, expected)
    except ValueError:
        return words
    return color(words, rows, t)
