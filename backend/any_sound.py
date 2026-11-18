"""The every-sound English check: any expected sound said as ANOTHER English sound, or left out, turns red.

In brief: inside the time window the forced aligner gave each expected sound, compare how sure the listener is of
that sound with how sure it is of the most likely OTHER English sound. If the other sound clearly wins, the sound
was probably replaced ("Testing" said "Tasting": the E window says [eɪ]). It was also probably replaced when the
free recognizer wrote a different sound there AND the expected one barely shows up (this catches a vowel whose
evidence is split between two similar vowels). If the recognizer skipped the sound AND it barely shows up in its
window, it was probably left out. Three cut-offs decide "clearly"; eval/any_sound.py
measured them on native voices and Korean speakers the listener never trained on (results/any_sound.json).

What is never a mistake (normal native speech, linguistic rules, not fitted numbers):
  - a weak vowel reduced to "uh" (unstressed syllables, small function words: "to" -> tuh, "and" -> uhn)
  - TH voiced or not ("with"), the cot/caught merger, an R-coloured vowel before R ("for"), tense/lax vowels
    merging before R ("here"), a word-final z said like s
  - any other dictionary pronunciation of the same word ("lived" laɪvd / lɪvd, "read" now / past)
  - dropping a weak vowel, a sound of a small function word ("and" -> an), or t/d between consonants ("acts")
Words the dictionary doesn't know (rare names, made-up words) are not graded: their expected sounds are a guess.

The MVP pairs in scoring.py keep their own tuned checks and hand-written tips; this check covers everything else.
"""
import json
import re
from collections import defaultdict
from functools import cache
from pathlib import Path

import torch

from backend.align import vocab
from backend.g2p import ARPA2IPA, _g2p_en
from backend.listener import listener_id

THRESHOLDS_FILE = Path(__file__).with_name("any_sound_thresholds.json")   # written by eval/any_sound.py
SWAP, MISSING = "sound_swap", "sound_missing"

# Every English sound -> the listener tokens that count as it. Overlaps are native variants: a flap ɾ counts as t
# AND d ("water", "ladder"), ɚ counts as ɚ AND ɹ.
CLASSES = {
    # vowels
    "ɑː": ["ɑː", "ɑ", "ɑ:", "a", "aː", "ä"], "ɔː": ["ɔː", "ɔ", "ɒ"], "æ": ["æ", "æː"], "ʌ": ["ʌ", "ɐ"],
    "ə": ["ə", "ɐ", "ᵻ", "ɨ"], "ɛ": ["ɛ", "ɛː", "e̞"], "ɪ": ["ɪ", "ᵻ", "ɨ", "ɪː"], "iː": ["iː", "i", "i:"],
    "eɪ": ["eɪ", "e", "eː", "e:"], "oʊ": ["oʊ", "o", "oː", "o:", "əʊ", "o̞"], "uː": ["uː", "u", "u:", "ʉ"],
    "ʊ": ["ʊ", "ʊː"], "aɪ": ["aɪ", "ai"], "aʊ": ["aʊ", "au"], "ɔɪ": ["ɔɪ"], "ɚ": ["ɚ", "ɜː", "ɜ"],
    # consonants
    "p": ["p", "pʰ", "ph"], "b": ["b"], "t": ["t", "tʰ", "th", "ɾ", "ʔ"], "d": ["d", "ɾ"], "k": ["k", "kʰ", "kh"],
    "ɡ": ["ɡ"], "f": ["f", "ɸ"], "v": ["v", "β"], "θ": ["θ"], "ð": ["ð"], "s": ["s"], "z": ["z"],
    "ʃ": ["ʃ", "ɕ"], "ʒ": ["ʒ"], "h": ["h"], "tʃ": ["tʃ", "tʃʰ"], "dʒ": ["dʒ"], "m": ["m"], "n": ["n"],
    "ŋ": ["ŋ"], "l": ["l", "ɫ", "l̩", "əl", "lː"], "ɹ": ["ɹ", "ɻ", "ɚ", "ɑːɹ", "ɔːɹ", "oːɹ", "ɛɹ", "ɪɹ", "ʊɹ", "aɪɚ"],
    "w": ["w"], "j": ["j"],
}
VOWELS = {"ɑː", "ɔː", "æ", "ʌ", "ə", "ɛ", "ɪ", "iː", "eɪ", "oʊ", "uː", "ʊ", "aɪ", "aʊ", "ɔɪ", "ɚ"}
NAMES = list(CLASSES)
TOKEN_CLASSES = defaultdict(set)
for _c, _toks in CLASSES.items():
    for _t in _toks:
        TOKEN_CLASSES[_t].add(_c)

# Short, mostly unstressed words whose vowel natives normally reduce ("to" -> tuh, "and" -> n).
FUNCTION_WORDS = set("""a an the of to and or nor for in on at by from with as is was are were be been am but that than
then them his her him he she we you your i it its my me us our they their there this these those have has had do does
did can could will would shall should may might must not no so if up out into onto upon over under about what when
which who whom whose how all some any just very""".split())
REDUCED = {"ə", "ɪ", "ʌ"}
BEFORE_R_SAME = [{"iː", "ɪ"}, {"eɪ", "ɛ", "æ"}, {"oʊ", "ɔː", "ɑː"}, {"uː", "ʊ"}]   # "here", "Mary/merry", "more"


# ---------- the rules ----------
def accepted(r):
    """True when the 'other sound' the listener prefers is a normal NATIVE way of saying the target."""
    t, o = r["target"], r["other"]
    if o in r.get("alts", ()):
        return True
    if {t, o} == {"ð", "θ"} or {t, o} == {"ɔː", "ɑː"}:
        return True
    if r.get("next") == "ɹ" and any({t, o} <= g for g in BEFORE_R_SAME):
        return True
    if t == "z" and o == "s" and r.get("next") == "":
        return True
    if t in VOWELS and o == "ɹ" and (t == "ɚ" or r.get("next") == "ɹ"):
        return True
    if t in VOWELS and o in REDUCED and (t == "ə" or r["weak"]):
        return True
    if t == "ə" and o in VOWELS:                   # schwa may come out as any vowel; a consonant there is still wrong
        return True
    return False


def dropped_ok(r):
    """A sound natives normally drop: a weak vowel, a sound of a small function word ("and" -> an), or t/d squeezed
    between consonants ("acts", "last night")."""
    return r["target"] == "ə" or r["func"] or (r["target"] in ("t", "d") and r.get("between_consonants"))


def margin_cut(r, t):
    """How far another sound must win for this sound to count as swapped. One global cut-off is set by the pairs
    natives blur on their own (weak vowels, cot/caught, ɛ/æ), so it is high (~0.98). A stressed sound that natives
    NEVER said like a given other sound of the same kind (t["never_blurred"]: every such pair, rare ones included,
    picked from the native voices by eval/any_sound.py) gets a gentler cut, so a real learner's less clean swap
    still turns red.
    t["pair_margin"] ("target other", "target *") is the per-pair experiment from eval --pairs, not live."""
    cuts = t.get("pair_margin") or {}
    cut = cuts.get(f"{r['target']} {r['other']}", cuts.get(f"{r['target']} *", t["margin"]))
    nb = t.get("never_blurred") or {}
    if not r.get("weak") and f"{r['target']} {r['other']}" in set(nb.get("pairs", ())):
        cut = min(cut, nb["cut"])     # a stressed sound natives never say like that other one ("lucky" -> "lacky")
    return cut


def verdict(r, t):
    """-> (SWAP, the sound probably said) | (MISSING, None) | None (green). t = the tuned thresholds."""
    if not t.get("enabled") or r.get("skip"):
        return None
    replaced = r["margin"] > margin_cut(r, t) or (r["op"] == "sub" and r["right"] < t.get("sub_right", 0.0))
    if replaced and not accepted(r):
        return SWAP, r["other"]
    if r["op"] == "del" and r["right"] < t["right"] and not dropped_ok(r):
        return MISSING, None
    return None


@cache
def load_thresholds():
    return json.loads(THRESHOLDS_FILE.read_text()) if THRESHOLDS_FILE.exists() else {"enabled": False}


def live_for(model):
    """The thresholds, if they were tuned for THIS listener (cut-offs mean nothing for another one)."""
    t = load_thresholds()
    return t if t.get("enabled") and model and listener_id(str(model)) == t.get("listener") else {"enabled": False}


# ---------- word context ----------
def _ipa(arpa):
    return "ə" if arpa == "AH0" else ARPA2IPA[arpa.rstrip("012")]


def _dict_word(part):
    return re.sub(r"'s$", "", part.lower())


def context(words):
    """(word_index, phoneme_index) -> weak, func, next, between_consonants, skip, alts, for words from
    g2p.expected_phonemes / align (each has 'word', 'pron' (ARPAbet with stress) and 'phonemes')."""
    cmu = _g2p_en().cmu
    out = {}
    for wi, w in enumerate(words):
        word, arpa = w["word"].lower(), w["pron"].split()
        ph = [x if isinstance(x, str) else x["ipa"] for x in w["phonemes"]]
        parts = [p for p in word.split("-") if p]
        skip = not parts or any(_dict_word(p) not in cmu for p in parts)
        prons = [] if "-" in word else cmu.get(_dict_word(word), [])
        for pi, sym in enumerate(ph):
            prev, nxt = (ph[pi - 1] if pi else ""), (ph[pi + 1] if pi + 1 < len(ph) else "")
            stress = arpa[pi][-1] if pi < len(arpa) else "1"
            alts = {_ipa(p[pi]) for p in prons if len(p) == len(ph)} - {sym}
            out[(wi, pi)] = dict(weak=word in FUNCTION_WORDS or stress == "0", func=word in FUNCTION_WORDS,
                                 next=nxt, between_consonants=bool(prev) and prev not in VOWELS and nxt not in VOWELS,
                                 skip=skip, alts=alts)
    return out


# ---------- the evidence ----------
@cache
def _matrix():
    v = vocab()
    m = torch.zeros(len(v), len(NAMES))
    for j, c in enumerate(NAMES):
        for t in CLASSES[c]:
            if t in v:
                m[v[t], j] = 1.0
    return m


def evidence(probs, sec_per_frame, words):
    """One dict per expected sound: right, best other sound, margin, and what the recognizer heard there.
    words = align() output after compare.attach_heard()."""
    M = _matrix()
    out, n = [], probs.shape[0]
    for wi, w in enumerate(words):
        for pi, p in enumerate(w["phonemes"]):
            c = p["ipa"]
            if c not in CLASSES:
                continue
            f0 = min(int(round(p["start"] / sec_per_frame)), n - 1)
            f1 = max(f0 + 1, min(int(round(p["end"] / sec_per_frame)), n))
            win = probs[f0:f1]
            j = NAMES.index(c)
            right = (win @ M[:, j]).max().item()
            mask = M.clone()
            mask[M[:, j] > 0, :] = 0          # a token that counts as the expected sound is never "another sound"
            mask[:, j] = 0
            other = (win @ mask).max(0).values  # peak of every other sound
            k = int(other.argmax())
            heard = p.get("heard")
            out.append(dict(word_index=wi, phoneme_index=pi, target=c, right=round(right, 4), other=NAMES[k],
                            margin=round(other[k].item() - right, 4), op=p.get("op"), heard=heard or "",
                            agrees=int(p.get("op") == "sub" and NAMES[k] in TOKEN_CLASSES.get(heard, ()))))
    return out


def score(em, words, t):
    """-> {(word_index, phoneme_index): (SWAP, said) | (MISSING, None)} for the red sounds. English only."""
    if not t.get("enabled"):
        return {}
    ctx = context(words)
    found = {}
    for r in evidence(em.log_probs.exp(), em.sec_per_frame, words):
        key = (r["word_index"], r["phoneme_index"])
        v = verdict({**r, **ctx[key]}, t)
        if v:
            found[key] = v
    return found


def apply(em, words, t):
    """Mark the red sounds in place (after scoring.score_words). A sound an MVP check already made red keeps that
    verdict. A swap that IS an MVP mistake (R said as L, ...) uses that pair's name, so its hand-written tip shows."""
    from backend.scoring import PAIRS
    for (wi, pi), (kind, said) in score(em, words, t).items():
        p = words[wi]["phonemes"][pi]
        if p.get("status") == "red":
            continue
        mvp = next((n for n, d in PAIRS.items() if kind == SWAP and d["target"] == p["ipa"] and said in d["wrong"]), None)
        p["status"], p["pair"], p["produced"] = "red", mvp or kind, said
        words[wi]["status"] = "red"
    return words


def checked(words, t):
    """(word_index, phoneme_index) of every sound this check grades (all but words the dictionary doesn't know)."""
    if not t.get("enabled"):
        return set()
    return {k for k, c in context(words).items() if not c["skip"] and words[k[0]]["phonemes"][k[1]]["ipa"] in CLASSES}
