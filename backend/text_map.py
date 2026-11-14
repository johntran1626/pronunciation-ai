"""Text mapping: which WRITTEN letters each SPOKEN sound comes from, so the UI can color the text.

Korean:
    korean_sources("같이", "가치") -> one entry per spoken phoneme, in g2p order:
        [{"char_index": 0, "jamo": "ㄱ", "slot": "onset", "spoken_index": 0},
         {"char_index": 0, "jamo": "ㅏ", "slot": "vowel", ...},
         {"char_index": 0, "jamo": "ㅌ", "slot": "coda", ...},      # the ㅊ sound is the written ㅌ
         {"char_index": 1, "jamo": "ㅣ", "slot": "vowel", ...}]
    char_index = position of the written syllable block in the word (what the UI colors), jamo = the
    written letter inside it (what the UI highlights). spoken_index = which spoken syllable it was said in.

How it works, in plain words:
  1. g2pk rewrites the word as it is said, and (almost always) keeps the number of syllables:
     같이 -> 가치, 국물 -> 궁물. So spoken syllable i lines up with written syllable i.
  2. Each spoken syllable gives its sounds in a fixed order (onset, vowel(s), final), exactly as g2p.py
     builds the phoneme list, so we can walk both lists in step.
  3. Vowels and finals come from the same written syllable (국물's ŋ = the written ㄱ; 읽다's k = ㄺ).
  4. Liaison: if the written syllable starts with a silent ㅇ and the one before it has a final consonant,
     the spoken onset came from that final (맛있어요 -> 마시써요: 시's ㅅ is 맛's ㅅ; 같이' ㅊ is 같's ㅌ).
  5. If the syllable counts differ (numbers: 3개 -> 세개), every sound maps to the whole word
     (char_index None): the UI colors the word, never a wrong letter.
Design choice: a sound that moved is colored where it is WRITTEN (같 for 같이's ㅊ), because that is the
letter the learner reads. Known limit: ㄴ-insertion (솜이불 -> 솜니불) maps the inserted ㄴ to the previous
final (ㅁ); ㅎ merges (좋다 -> 조타) map the ㅌ to the written ㄷ only.
"""
import copy

from backend.g2p import CODA, ONSET, VOWEL, _is_hangul

ONSET_JAMO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
VOWEL_JAMO = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
CODA_JAMO = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ",
             "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
SILENT = ONSET_JAMO.index("ㅇ")  # the silent onset ㅇ


def _split(ch):
    o = ord(ch) - 0xAC00
    return o // 588, (o % 588) // 28, o % 28


def _spoken_slots(pron):
    """The phonemes g2p.py makes from the pronounced word, as (spoken syllable index, slot), in order."""
    out = []
    for j, ch in enumerate(c for c in pron if _is_hangul(c)):
        onset, vowel, coda = _split(ch)
        if ONSET[onset]:
            out.append((j, "onset"))
        out += [(j, "vowel")] * len(VOWEL[vowel])
        if CODA[coda]:
            out.append((j, "coda"))
    return out


def korean_sources(word, pron):
    slots = _spoken_slots(pron)
    written = [(ci, _split(ch)) for ci, ch in enumerate(word) if _is_hangul(ch)]
    if len(written) != sum(_is_hangul(c) for c in pron):   # syllable counts differ (e.g. 3개 -> 세개)
        return [dict(char_index=None, jamo=None, slot=slot, spoken_index=j) for j, slot in slots]
    out = []
    for j, slot in slots:
        ci, (onset, vowel, coda) = written[j]
        if slot == "vowel":
            src = (ci, VOWEL_JAMO[vowel])
        elif slot == "coda":
            src = (ci, CODA_JAMO[coda])
        elif onset == SILENT and j > 0 and written[j - 1][1][2]:   # liaison: the previous final moved over
            prev_ci, (_, _, prev_coda) = written[j - 1]
            src, slot = (prev_ci, CODA_JAMO[prev_coda]), "coda"
        else:
            src = (ci, ONSET_JAMO[onset])
        out.append(dict(char_index=src[0], jamo=src[1], slot=slot, spoken_index=j))
    return out


# ---------- English ----------
# Which letter chunks can spell each sound (ARPAbet, stress digits dropped). Built by hand from standard
# English spelling patterns (e.g. "igh" = AY in night, "ph" = F, "tch" = CH); not exhaustive. A pair that
# isn't listed can still be aligned, but only through the expensive fallback (and is marked known=False).
P2G = {
    "AA": "a o ah al au aa", "AE": "a ai au", "AH": "u o a e i ou oo io ia ai y",
    "AO": "o aw au a al augh ough oa ou", "AW": "ow ou ough", "AY": "i y igh ie ye ei ai uy eye eigh",
    "EH": "e ea ai a ie ue ay", "ER": "er ir ur or ear our ar yr re eur olo r",
    "EY": "a ai ay ei ey eigh ea e ae", "IH": "i y e ie ui u a ee o", "IY": "e ee ea ie ei y i ey eo ae oe",
    "OW": "o oa ow oe ough ou ew au eau", "OY": "oi oy", "UH": "oo u ou o", "UW": "oo u ue ew o ou ui oe wo",
    "B": "b bb", "CH": "ch tch t c", "D": "d dd ed t", "DH": "th", "F": "f ff ph gh", "G": "g gg gu gh",
    "HH": "h wh", "JH": "j g dg ge gg d", "K": "k c ck ch q cc kk qu g", "L": "l ll", "M": "m mm mb mn lm",
    "N": "n nn kn gn pn mn", "NG": "ng n", "P": "p pp", "R": "r rr wr rh", "S": "s ss c sc ce se ps",
    "SH": "sh ti ci ch s ss si sci ce", "T": "t tt ed th pt bt", "TH": "th", "V": "v f vv", "W": "w u o wh",
    "Y": "y i j", "Z": "z zz s ss x se ze", "ZH": "s si g ge z j",
}
# One chunk that spells TWO sounds: box = B AA K S ("x" = K S), cute = K Y UW ("u" = Y UW), people's "le".
# Added after measuring coverage on the ARCTIC prompts (2026-11-12): ER "r" (our, hour), D "t" (American flap:
# thirty), K "g" (strength), ZH "j" (Jacques), Y+UH / Y+AH "u" (curious, regular).
P2G_TWO = {("K", "S"): "x", ("G", "Z"): "x", ("Y", "UW"): "u ew eu ue iew", ("K", "W"): "qu", ("Y", "UH"): "u", ("Y", "AH"): "u",
           ("AH", "L"): "le", ("W", "AH"): "o"}
ONE = {(g, p) for p, gs in P2G.items() for g in gs.split()}
TWO = {(g, ps) for ps, gs in P2G_TWO.items() for g in gs.split()}
MAX_CHUNK = 4
# Move costs (hand-set, see english_sources). EN_ prefix: Korean code above has its own SILENT (the ㅇ index).
EN_KNOWN, EN_SILENT_E, EN_SILENT, EN_FALLBACK, EN_NO_LETTERS = 0.1, 0.3, 0.8, 2.0, 3.0


def english_sources(word, pron):
    """'knight', 'N AY1 T' -> [{'start': 0, 'end': 2, 'known': True}, {'start': 2, 'end': 5, ...}, {'start': 5, ...}]
    = one letter span per phoneme (word[start:end] = 'kn', 'igh', 't'). start None = no letters (color the word).

    How it works: the cheapest way to walk through the letters and the sounds together, in order
    (dynamic programming, like the edit distance in sequence_align.py). Each move costs:
        a known chunk for this sound (P2G table)      0.1   'igh' -> AY
        a known chunk for two sounds (P2G_TWO)        0.1   'x' -> K S
        a silent final-ish 'e' / other silent letter  0.3 / 0.8
        any letter for any sound (fallback)           2.0   only when nothing in the table fits
        a sound with no letter at all                 3.0
    So "kn" as one chunk (0.1) beats "silent k + n" (0.9), and the table always wins over the fallback."""
    phones = [p.rstrip("012") for p in pron.split()]
    if not any(ch.isalpha() for ch in word):
        return [dict(start=None, end=None, known=False) for _ in phones]
    low = word.lower()
    n, m = len(low), len(phones)
    INF = float("inf")
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0

    def relax(i, j, i2, j2, c, move):
        if cost[i][j] + c < cost[i2][j2]:
            cost[i2][j2], back[i2][j2] = cost[i][j] + c, (i, j, move)

    for i in range(n + 1):
        for j in range(m + 1):
            if cost[i][j] == INF:
                continue
            if i < n:  # a letter with no sound (apostrophes and hyphens are free)
                relax(i, j, i + 1, j, 0.0 if not low[i].isalpha() else EN_SILENT_E if low[i] == "e" else EN_SILENT, "silent")
            if j < m:
                relax(i, j, i, j + 1, EN_NO_LETTERS, "none")
                for L in range(1, MAX_CHUNK + 1):
                    if i + L > n:
                        break
                    g = low[i:i + L]
                    if (g, phones[j]) in ONE:
                        relax(i, j, i + L, j + 1, EN_KNOWN, "one")
                    if j + 1 < m and (g, (phones[j], phones[j + 1])) in TWO:
                        relax(i, j, i + L, j + 2, EN_KNOWN, "two")
                if i < n:
                    relax(i, j, i + 1, j + 1, EN_FALLBACK, "fallback")

    out, i, j = [None] * m, n, m       # walk back from the end to recover the moves
    while (i, j) != (0, 0):
        pi, pj, move = back[i][j]
        if move in ("one", "fallback"):
            out[pj] = dict(start=pi, end=i, known=move == "one")
        elif move == "two":
            out[pj] = out[pj + 1] = dict(start=pi, end=i, known=True)
        elif move == "none":
            out[pj] = dict(start=None, end=None, known=False)
        i, j = pi, pj
    return [dict(s) for s in out]


# ---------- display segments for the UI ----------
def _merge(segments):
    """Join neighbouring English pieces that share a status: [k g][n g][igh r] -> [kn g][igh r]."""
    out = []
    for s in segments:
        if out and out[-1]["status"] == s["status"]:
            out[-1]["text"] += s["text"]
        else:
            out.append(dict(s))
    return out


RANK = {"red": 2, "green": 1, "unchecked": 0}  # a letter shows the strongest verdict of its sounds


def _strongest(a, b):
    return a if a is not None and (b is None or RANK[a] >= RANK[b]) else b


def _fill_gaps(statuses, fallback):
    """Letters with no sound (silent k in knight) take the previous letter's status (or the next one's)."""
    out = list(statuses)
    for i in range(len(out)):
        if out[i] is None and i > 0:
            out[i] = out[i - 1]
    for i in range(len(out) - 2, -1, -1):
        if out[i] is None:
            out[i] = out[i + 1]
    return [s or fallback for s in out]


def _english_display(w):
    spans = english_sources(w["word"], w["pron"])
    letter = [None] * len(w["word"])
    whole_word = False
    for p, s in zip(w["phonemes"], spans):
        p["source"] = {"start": s["start"], "end": s["end"]}
        if s["start"] is None:
            whole_word = whole_word or p["status"] == "red"
            continue
        for k in range(s["start"], s["end"]):
            letter[k] = _strongest(letter[k], p["status"])
    if whole_word:
        return [{"text": w["word"], "status": "red"}]
    statuses = _fill_gaps(letter, w.get("status", "green"))
    return _merge([{"text": ch, "status": st} for ch, st in zip(w["word"], statuses)])


def _korean_display(w):
    sources = korean_sources(w["word"], w["pron"])
    blocks = [{"text": ch, "status": None, "red_jamo": [], "red_slots": [], "start": None, "end": None}
              for ch in w["word"]]
    whole_word = False
    for p, s in zip(w["phonemes"], sources):
        p["source"] = {"char_index": s["char_index"], "jamo": s["jamo"], "slot": s["slot"]}
        if s["char_index"] is None:
            if p["status"] == "red":
                whole_word = True
            continue
        b = blocks[s["char_index"]]
        b["start"] = p["start"] if b["start"] is None else min(b["start"], p["start"])
        b["end"] = p["end"] if b["end"] is None else max(b["end"], p["end"])
        b["status"] = _strongest(b["status"], p["status"])
        if p["status"] == "red":
            if s["jamo"] not in b["red_jamo"]:
                b["red_jamo"].append(s["jamo"])
            if s["slot"] not in b["red_slots"]:  # WHERE in the block (onset/vowel/coda), for 각-type blocks
                b["red_slots"].append(s["slot"])
    for b in blocks:  # a character with no sounds (e.g. a digit before the fallback) shows the word's status
        b["status"] = "red" if whole_word else b["status"] or w.get("status", "green")
    return blocks


def attach_display(words, lang):
    """Scored words -> a copy where each phoneme gets `source` (its letters) and each word gets `display`:
    pieces that spell the word exactly, each green, red or unchecked (no live check looked at it),
    ready for the UI to paint.
        en: [{"text": "kn", "status": "green"}, {"text": "igh", "status": "red"}, {"text": "t", ...}]
        ko: one piece per character: {"text": "같", "status": "red", "red_jamo": ["ㅌ"], "red_slots": ["coda"],
            "start": s, "end": s}
            (start/end = the span of the sounds mapped to that block, for "tap a syllable to replay it";
             None for a character with no sounds, e.g. a digit before the fallback)
    A red sound with no letters (start/char_index None) turns the whole word red: never a wrong letter."""
    words = copy.deepcopy(words)
    for w in words:
        w["display"] = _korean_display(w) if lang == "ko" else _english_display(w)
    return words
