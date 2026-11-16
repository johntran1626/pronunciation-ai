"""Korean green/red: the Korean-trained listener's checks that passed all four bars.

    words = score_korean(samples, sr, expected, words)     # after match.finalize(), Korean sentences only

In brief: the English checks run on the main listener (scoring.py). For Korean the main listener can't tell
ㅂ from ㅃ, so a second, Korean-trained listener (korean_listener.py) measures each checkable sound. Of its 10
candidate checks, only the ones that passed all four bars in eval/korean_checks.py may color anything; that list
is backend/korean_thresholds.json ("enabled": true). Today that is ㅜ said like ㅡ, and a plain ㅂ ㄷ ㄱ said tense.

What each sound gets:
  - a live check looked at it and fired (margin above the cut AND the model wrote the wrong sound) -> red,
    with pair = the tip to show (u_as_eu, or p_as_pp / t_as_tt / k_as_kk for the stop's own place)
  - a live check looked at it, did not fire, AND the listener heard the right sound there -> green
  - a live check did not fire but the listener heard some other sound there (발을 said 말을) -> stays plain:
    the check only asks "tense or not?", so "not tense" is no proof the ㅂ was right
  - no live check covers it -> stays "unchecked" (plain text): we never claim a sound is right unchecked
A word the "did you say it?" check already marked not heard stays red for that reason.
"""
import copy
import json
from pathlib import Path

from backend.g2p import TENSE

THRESHOLDS_FILE = Path(__file__).with_name("korean_thresholds.json")   # written by eval/korean_checks.py

CHECK_ID = {"ㅜ_as_ㅡ": "u_as_eu", "lenis_as_tense": "lenis_as_tense"}   # the name the API and the UI use
LENIS = {"p", "t", "k"}                                                    # plain ㅂ ㄷ ㄱ


def load_korean_thresholds():
    return json.loads(THRESHOLDS_FILE.read_text(encoding="utf-8")) if THRESHOLDS_FILE.exists() else {"checks": {}}


def live_checks(kt):
    """{check name: cut} for the checks that passed all four bars (and that this module knows how to show)."""
    return {name: c["cut"] for name, c in kt.get("checks", {}).items() if c.get("enabled") and name in CHECK_ID}


def check_names(kt):
    """For the honesty line under a result ("This version checks ...")."""
    return sorted(CHECK_ID[name] for name in live_checks(kt))


def tip_id(check, target):
    """Which tips.json entry explains this mistake on this sound."""
    if check == "ㅜ_as_ㅡ":
        return "u_as_eu"
    if check == "lenis_as_tense":
        if target not in LENIS:
            raise KeyError(target)
        return f"{target}_as_{target}{target}"          # p -> p_as_pp
    raise KeyError(check)


def produced(check, target):
    """The sound we think was said instead (an articulation.json key, for the mouth diagram)."""
    return "ɯ" if check == "ㅜ_as_ㅡ" else target + TENSE


def apply_korean(words, rows, kt):
    """Color the sounds the live checks measured. rows = korean_listener.measure() output. -> a copy."""
    live = live_checks(kt)
    words = copy.deepcopy(words)
    for r in rows:
        if r["check"] not in live or r["wi"] >= len(words):
            continue
        w = words[r["wi"]]
        if w.get("not_heard") or r["pi"] >= len(w["phonemes"]):
            continue
        p = w["phonemes"][r["pi"]]
        target = p["ipa"]
        if target not in (LENIS if r["check"] == "lenis_as_tense" else {"u"}):
            continue          # the row doesn't line up with this sound: ignore it rather than guess
        if float(r["margin"]) > live[r["check"]] and int(r["heard_said"]) == 1:   # = korean_listener.fires()
            p["checked"] = True
            p["status"], p["pair"], p["margin"] = "red", tip_id(r["check"], target), r["margin"]
            p["produced"] = produced(r["check"], target)
        elif int(r.get("heard_target", 0)) == 1 and p["status"] != "red":
            p["checked"] = True
            p["status"] = "green"
        # else: not the mistake this check looks for, but the listener didn't hear the right sound either
        # (발을 said 말을): no verdict, the sound stays plain rather than a false green
    for w in words:
        statuses = [p["status"] for p in w["phonemes"]]
        w["status"] = "red" if "red" in statuses else "green" if "green" in statuses else "unchecked"
    return words


def score_korean(samples, sr, expected, words, kt=None, lp=None):
    """Run the Korean listener (only if a check is live) and color the words.
    expected = g2p.expected_phonemes(text, "ko"); words = the same sentence after match.finalize().
    lp = the Korean listener's output if the "did you say it?" check already ran it (the model then runs once)."""
    kt = load_korean_thresholds() if kt is None else kt
    if not live_checks(kt):
        return words
    from backend.korean_listener import measure, measure_lp   # torch + the 1.3 GB model load only when needed
    try:
        rows = measure(samples, sr, expected) if lp is None else measure_lp(lp, expected)
    except ValueError:      # e.g. too short for this model's alignment: no Korean verdict, everything stays plain
        return words
    return apply_korean(words, rows, kt)
