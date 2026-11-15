"""G2P wrappers: target text -> the phonemes a native speaker would say, word by word.

    expected_phonemes("국물", "ko") -> [{"word": "국물", "pron": "궁물", "phonemes": ["k","u","ŋ","m","u","l"]}]
    expected_phonemes("cat", "en")  -> [{"word": "cat",  "pron": "K AE1 T", "phonemes": ["k","æ","t"]}]
    expected_phonemes("I want 떡볶이", "mix") -> the same per word, each also tagged "lang": "en" / "ko"

Korean:  g2pk rewrites the text as it is SAID (sound-change rules), then each jamo -> IPA (tables below).
English: g2p_en gives ARPAbet (CMUdict, plus a neural guess for unknown words), then ARPAbet -> IPA.
Output is textbook IPA. The recognizer's own symbols (align.py's HEARD_AS) are applied in the aligner, not here.

IPA reference: Korean, Shin, Kiaer & Cha (2012), *The Sounds of Korean*; English, standard CMUdict/ARPAbet
-> IPA correspondences (as used in spikes/d_align.py). Korean is phonemic (lenis ㄱㄷㅂ stay k t p even where they
sound voiced), except ㄹ: tap [ɾ] before a vowel, [l] at a syllable end and in ㄹㄹ.
"""
import re
from functools import cache

from backend.mixed_text import split_runs

TENSE = "͈"  # combining double vertical line below: p͈ t͈ k͈ s͈ (IPA for Korean tense consonants)

# ---------- Korean ----------
# A Hangul syllable block = onset (19) x vowel (21) x coda (28), packed in Unicode from U+AC00.
#   ㄱ    ㄲ          ㄴ   ㄷ    ㄸ          ㄹ   ㅁ   ㅂ    ㅃ          ㅅ    ㅆ          ㅇ (silent)
#   ㅈ     ㅉ                ㅊ      ㅋ    ㅌ    ㅍ    ㅎ
ONSET = ["k", "k" + TENSE, "n", "t", "t" + TENSE, "ɾ", "m", "p", "p" + TENSE, "s", "s" + TENSE, None,
         "tɕ", "t" + TENSE + "ɕ", "tɕʰ", "kʰ", "tʰ", "pʰ", "h"]
#        ㅏ     ㅐ     ㅑ          ㅒ          ㅓ     ㅔ     ㅕ          ㅖ          ㅗ     ㅘ          ㅙ
#        ㅚ          ㅛ          ㅜ     ㅝ          ㅞ          ㅟ          ㅠ          ㅡ     ㅢ          ㅣ
VOWEL = [["a"], ["ɛ"], ["j", "a"], ["j", "ɛ"], ["ʌ"], ["e"], ["j", "ʌ"], ["j", "e"], ["o"], ["w", "a"], ["w", "ɛ"],
         ["w", "e"], ["j", "o"], ["u"], ["w", "ʌ"], ["w", "e"], ["w", "i"], ["j", "u"], ["ɯ"], ["ɰ", "i"], ["i"]]
# Only 7 sounds can end a syllable. g2pk usually outputs those already; this table covers anything it leaves.
# (none ㄱ ㄲ ㄳ ㄴ ㄵ ㄶ ㄷ ㄹ ㄺ ㄻ ㄼ ㄽ ㄾ ㄿ ㅀ ㅁ ㅂ ㅄ ㅅ ㅆ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ)
CODA = [None, "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l",
        "m", "p", "p", "t", "t", "ŋ", "t", "t", "k", "t", "p", "t"]
HANGUL_FIRST, HANGUL_COUNT = 0xAC00, 11172


def _is_hangul(ch):
    return 0 <= ord(ch) - HANGUL_FIRST < HANGUL_COUNT


def _korean_word_ipa(pron_word, prev_coda):
    """'궁물' -> ['k','u','ŋ','m','u','l']. prev_coda carries across words, so ㄹ+ㄹ over a space is [l l]."""
    phones = []
    for ch in pron_word:
        if not _is_hangul(ch):
            continue
        o = ord(ch) - HANGUL_FIRST
        onset, vowels, coda = ONSET[o // 588], VOWEL[(o % 588) // 28], CODA[o % 28]
        if onset == "ɾ" and prev_coda == "l":
            onset = "l"  # ㄹㄹ is a long [l], not a tap
        if onset:
            phones.append(onset)
        phones += vowels
        if coda:
            phones.append(coda)
        prev_coda = coda
    return phones, prev_coda


@cache
def _g2pk():
    from g2pk import G2p  # loads a Korean dictionary (mecab): slow the first time, so load once, on first use
    return G2p()


def _korean(text):
    written = text.split()
    said = _g2pk()(text).split()  # the WHOLE sentence at once: some rules cross word gaps (먹을 것 -> 머글 껃)
    if len(said) != len(written):  # g2pk changed the word count (rare); fall back to one word at a time
        said = [_g2pk()(w) for w in written]
    words, prev_coda = [], None
    for w, s in zip(written, said):
        pron = "".join(ch for ch in s if _is_hangul(ch))
        if not pron:
            continue  # a punctuation-only token like "?!"
        phones, prev_coda = _korean_word_ipa(pron, prev_coda)
        words.append({"word": _strip_punct(w), "pron": pron, "phonemes": phones})
    return words


# ---------- English ----------
ARPA2IPA = {
    "AA": "ɑː", "AE": "æ", "AH": "ʌ", "AO": "ɔː", "AW": "aʊ", "AY": "aɪ", "B": "b", "CH": "tʃ",
    "D": "d", "DH": "ð", "EH": "ɛ", "ER": "ɚ", "EY": "eɪ", "F": "f", "G": "ɡ", "HH": "h",
    "IH": "ɪ", "IY": "iː", "JH": "dʒ", "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ",
    "OW": "oʊ", "OY": "ɔɪ", "P": "p", "R": "ɹ", "S": "s", "SH": "ʃ", "T": "t", "TH": "θ",
    "UH": "ʊ", "UW": "uː", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}


def _arpa_to_ipa(arpa):
    """'AH0' -> 'ə' (unstressed AH is a schwa); otherwise drop the stress digit and look it up."""
    return "ə" if arpa == "AH0" else ARPA2IPA[arpa.rstrip("012")]


@cache
def _g2p_en():
    from g2p_en import G2p
    return G2p()


def _arpa_groups(text):
    """g2p_en output ['HH','AH0',..,' ',',',' ','W',..] -> one ARPAbet list per word, punctuation dropped."""
    groups, cur = [], []
    for tok in _g2p_en()(text) + [" "]:
        if tok == " ":
            if cur:
                groups.append(cur)
            cur = []
        elif tok.rstrip("012") in ARPA2IPA:
            cur.append(tok)
    return groups


def _english(text):
    written = [w for w in (_strip_punct(t) for t in text.split()) if w]
    groups = _arpa_groups(text)  # whole sentence: g2p_en uses the sentence to pick between e.g. REcord / reCORD
    if len(groups) != len(written):  # numbers or hyphens changed the word count; go one word at a time
        groups = [sum(_arpa_groups(w), []) for w in written]
    return [{"word": w, "pron": " ".join(g), "phonemes": [_arpa_to_ipa(a) for a in g]}
            for w, g in zip(written, groups) if g]


# ---------- mixed English + Korean ----------
def _mixed(text):
    """Each language run gets its own G2P. Known limit: Korean sound changes across the border with English
    (Ben 어제 -> 베너제) are not applied, because each Korean run is converted on its own."""
    words = []
    for lang, run in split_runs(text):
        try:
            run_words = expected_phonemes(run.strip(), lang)
        except ValueError:
            continue  # a run with nothing to say (lone jamo like ㅋㅋ)
        words += [{**w, "lang": lang} for w in run_words]
    return words


# ---------- shared ----------
def _strip_punct(token):
    """'Hello,' -> 'Hello'; '안녕하세요.' -> '안녕하세요'. Keeps inner marks like I'm and well-known."""
    return re.sub(r"^[^\w]+|[^\w]+$", "", token)


def expected_phonemes(text, lang):
    """Target text -> [{'word', 'pron', 'phonemes'}, ...] in sentence order.
    pron = the pronounced Hangul (ko) or ARPAbet with stress digits (en). Raises ValueError on bad input."""
    if lang == "ko":
        words = _korean(text)
    elif lang == "en":
        words = _english(text)
    elif lang == "mix":
        words = _mixed(text)
    else:
        raise ValueError(f"unsupported language: {lang!r} (use 'ko', 'en' or 'mix')")
    if not words:
        raise ValueError("no pronounceable words in the text")
    return words
