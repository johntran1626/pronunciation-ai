"""The every-sound English check (backend/any_sound.py): native-variant rules, word context, the red rule, and the
whole pipeline on a committed native recording (correct reading = no reds; a changed target = red, naming the sound
that was really said)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import any_sound
from backend.any_sound import MISSING, SWAP, accepted, context, dropped_ok, verdict
from backend.app import app
from backend.g2p import expected_phonemes

FIXTURES = Path(__file__).parents[0] / "fixtures"
SLT = "cmu_slt_arctic_a0020.wav"          # "Clubs and balls and cities grew to be only memories."
client = TestClient(app)


def row(target, other, **kw):
    base = dict(target=target, other=other, weak=False, func=False, next="", alts=set(), between_consonants=False,
                margin=0.99, right=0.5, op="sub", agrees=1, skip=False)
    return {**base, **kw}


# ---------- native variants are never mistakes ----------
def test_vowel_reduction_is_fine_only_in_weak_syllables_and_small_words():
    assert accepted(row("æ", "ə", weak=True))            # "and" said "uhn"
    assert accepted(row("uː", "ə", weak=True))           # "to" said "tuh"
    assert not accepted(row("æ", "ə"))                    # stressed "cat" said "cut": a real mistake
    assert accepted(row("ə", "ɪ"))                        # schwa may come out as any vowel
    assert not accepted(row("ə", "s"))                    # ...but not as a consonant


def test_other_native_variants():
    assert accepted(row("ð", "θ"))                        # "with" with a voiceless TH
    assert accepted(row("ɑː", "ɔː"))                      # cot / caught merger
    assert accepted(row("iː", "ɪ", next="ɹ"))             # "here": tense/lax merge before R
    assert not accepted(row("iː", "ɪ"))                   # sheep said ship: a real mistake
    assert accepted(row("ɔː", "ɹ", next="ɹ"))             # "for": R-coloured vowel
    assert accepted(row("z", "s", next=""))               # word-final z devoiced
    assert not accepted(row("z", "s", next="iː"))
    assert accepted(row("aɪ", "ɪ", alts={"ɪ"}))            # "lived": the dictionary has both


def test_normal_native_drops():
    assert dropped_ok(row("ə", ""))
    assert dropped_ok(row("d", "", func=True))            # "and" -> "an"
    assert dropped_ok(row("t", "", between_consonants=True))   # "acts"
    assert not dropped_ok(row("k", ""))


# ---------- word context ----------
def test_context_marks_weak_vowels_function_words_and_next_sound():
    words = expected_phonemes("Testing the locker", "en")
    ctx = context(words)
    assert ctx[(0, 1)]["weak"] is False and ctx[(0, 1)]["next"] == "s"   # stressed E of "Testing"
    assert ctx[(1, 1)]["func"] is True                                     # the vowel of "the"
    assert ctx[(2, 3)]["next"] == ""                                        # last sound of "locker"
    assert not any(c["skip"] for c in ctx.values())


def test_words_the_dictionary_does_not_know_are_not_graded():
    ctx = context(expected_phonemes("Zorblaxian ships", "en"))
    assert ctx[(0, 0)]["skip"] is True
    assert ctx[(1, 0)]["skip"] is False


def test_lived_accepts_both_dictionary_vowels():
    words = expected_phonemes("lived", "en")
    picked = words[0]["phonemes"][1]                    # g2p picks one of them
    assert context(words)[(0, 1)]["alts"] | {picked} == {"aɪ", "ɪ"}


# ---------- the red rule ----------
T = {"enabled": True, "margin": 0.95, "right": 0.0005, "sub_right": 0.005}


def test_verdict_swap_missing_and_green():
    assert verdict(row("ɛ", "eɪ", margin=0.97), T) == (SWAP, "eɪ")
    assert verdict(row("ɛ", "eɪ", margin=0.80), T) is None                 # not sure enough
    assert verdict(row("ɛ", "ɑː", margin=0.80, right=0.0001), T) == (SWAP, "ɑː")   # heard as another sound, E absent
    assert verdict(row("ɛ", "ɑː", margin=0.80, right=0.0001, op="match"), T) is None
    assert verdict(row("æ", "ə", weak=True), T) is None                    # native variant
    assert verdict(row("k", "t", op="del", right=0.0001, margin=0.2), T) == (MISSING, None)
    assert verdict(row("d", "n", op="del", right=0.0001, margin=0.2, func=True), T) is None
    assert verdict(row("k", "t", skip=True), T) is None
    assert verdict(row("ɛ", "eɪ"), {"enabled": False}) is None


def test_live_thresholds_file_is_the_measured_balanced_choice():
    t = any_sound.load_thresholds()
    assert t["enabled"] is True
    assert t["cap"] == 0.05                               # "Balanced": <= 5% of correct tune sentences get a false red
    assert t["margin"] == pytest.approx(0.98) and t["right"] == pytest.approx(0.0005)
    assert t["sub_right"] == pytest.approx(0.002)
    assert t["listener"] == "listener_v1"                 # a short name, never a path from this machine


# ---------- the whole pipeline on a real native recording ----------
def analyze(text, file=SLT):
    wav = (FIXTURES / file).read_bytes()
    r = client.post("/analyze", files={"audio": (file, wav, "audio/wav")}, data={"text": text, "lang": "en"})
    assert r.status_code == 200
    return r.json()


def reds(body):
    return {(w["word"], p["ipa"], p.get("pair"), p.get("produced"))
            for w in body["words"] for p in w["phonemes"] if p["status"] == "red"}


needs_listener = pytest.mark.skipif(not any_sound.load_thresholds().get("enabled"), reason="no live thresholds")


@needs_listener
def test_correct_native_reading_has_no_reds_and_every_sound_is_checked():
    body = analyze("Clubs and balls and cities grew to be only memories.")
    assert body["matched"] and reds(body) == set()
    assert "any_sound" in body["checks"]
    assert all(p["status"] == "green" for w in body["words"] for p in w["phonemes"])


@needs_listener
def test_a_swapped_vowel_is_red_and_names_what_was_said():
    body = analyze("Clubs and bells and cities grew to be only memories.")   # she said "balls"
    bells = [p for w in body["words"] if w["word"] == "bells" for p in w["phonemes"]]
    vowel = next(p for p in bells if p["ipa"] == "ɛ")
    assert vowel["status"] == "red" and vowel["pair"] == SWAP
    assert vowel["produced"] in {"ɔː", "ɑː"}            # "balls" (many US speakers say it like "father")
    assert {w["word"] for w in body["words"] if w["status"] == "red"} == {"bells"}


# ---------- per-pair cut-offs ----------
def test_a_pair_cut_overrides_the_global_cut_for_that_pair_only():
    t = {**T, "pair_margin": {"ɪ ʌ": 0.25, "ɪ *": 0.6}}
    assert verdict(row("ɪ", "ʌ", margin=0.3, right=0.18), t) == (SWAP, "ʌ")     # "drunking": a pair natives never blur
    assert verdict(row("ɪ", "ʌ", margin=0.2, right=0.18), t) is None
    assert verdict(row("ɪ", "æ", margin=0.7, right=0.18), t) == (SWAP, "æ")     # the target's own fallback
    assert verdict(row("ɪ", "æ", margin=0.5, right=0.18), t) is None
    assert verdict(row("ɛ", "eɪ", margin=0.80), t) is None                       # other targets keep the global cut


# ---------- vowel pairs natives never blur ----------
NB = {**T, "never_blurred": {"cut": 0.8, "pairs": ["ʌ æ", "æ ʌ"]}}


def test_a_never_blurred_vowel_pair_gets_the_gentler_cut_in_a_stressed_syllable():
    # the listener's numbers for a clear "I'm lacky" read against the text "I'm lucky" (ʌ said as æ)
    lacky = row("ʌ", "æ", margin=0.8327, right=0.0055)
    assert verdict(lacky, T) is None                                 # the global cut alone misses it
    assert verdict(lacky, NB) == (SWAP, "æ")
    assert verdict(row("ʌ", "æ", margin=0.75, right=0.0055), NB) is None   # still has to clearly win
    assert verdict({**lacky, "weak": True}, NB) is None              # weak syllables keep the global cut
    assert verdict(row("ɛ", "æ", margin=0.83, right=0.01), NB) is None     # a pair natives DO blur: global cut


def test_live_thresholds_list_only_pairs_natives_never_blur():
    nb = any_sound.load_thresholds()["never_blurred"]
    assert nb["cut"] == pytest.approx(0.8)
    pairs = {tuple(p.split()) for p in nb["pairs"]}
    assert ("ʌ", "æ") in pairs and ("æ", "ʌ") in pairs
    assert ("v", "b") in pairs and ("dʒ", "tʃ") in pairs           # consonant pairs too
    assert ("ɛ", "æ") not in pairs and ("ɪ", "iː") not in pairs     # natives blur these on their own
    V = any_sound.VOWELS
    assert all((t in V) == (o in V) and t != o for t, o in pairs)   # a vowel only competes with vowels
