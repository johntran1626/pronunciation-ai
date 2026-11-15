"""Split a mixed English + Korean sentence into language runs. No other backend imports (tts.py uses this).

    split_runs("I really want to eat 떡볶이 tonight.")
    -> [("en", "I really want to eat "), ("ko", "떡볶이 "), ("en", "tonight.")]

The language comes from the letters: Hangul = Korean, Latin = English. Everything else (spaces, digits,
punctuation) has no language of its own and goes with a neighbour:
  - normally the run before it ("I want 2 떡볶이": the 2 is English, "two");
  - but what is glued to the next word, with no space, goes with that word ("I want 2개": 2 belongs to 개, "두 개").
The pieces keep every original character, so "".join(the run texts) is the sentence again (the spaces too:
"Ben이" has no space, and the voice must not get one).
"""
import re

HANGUL = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")
LATIN = re.compile(r"[A-Za-z]")
LANG_TAGS = {"en": "en-US", "ko": "ko-KR"}


def char_lang(ch):
    """'떡' -> 'ko', 'a' -> 'en', anything else -> None."""
    if HANGUL.match(ch):
        return "ko"
    if LATIN.match(ch):
        return "en"
    return None


def split_runs(text):
    """Text -> [(lang, run text), ...]. A text with no letters at all gives []."""
    runs, buffer = [], ""            # buffer = characters with no language, waiting to see who they belong to
    for ch in text:
        lang = char_lang(ch)
        if lang is None:
            buffer += ch
        elif runs and runs[-1][0] == lang:
            runs[-1][1] += buffer + ch
            buffer = ""
        else:
            gap = re.search(r"\s", buffer[::-1])            # the last space in the buffer
            cut = len(buffer) - gap.start() if gap else 0   # after it: glued to this new word
            if runs:
                runs[-1][1] += buffer[:cut]
                buffer = buffer[cut:]
            runs.append([lang, buffer + ch])
            buffer = ""
    if runs:
        runs[-1][1] += buffer
    return [(lang, run) for lang, run in runs]


def edges(run):
    """'떡볶이 ' -> ('', '떡볶이', ' '): the spaces around a run, kept apart so they can be put back as typed."""
    core = run.strip()
    if not core:
        return run, "", ""
    lead = run[: len(run) - len(run.lstrip())]
    return lead, core, run[len(lead) + len(core):]


def is_mixed(text):
    """True when the text has both Korean and English letters."""
    return len({lang for lang, _ in split_runs(text)}) > 1
