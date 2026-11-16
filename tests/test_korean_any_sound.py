"""The every-sound Korean check (backend/korean_any_sound.py) and its eval (eval/korean_any_sound.py).

Unit tests use made-up numbers (no model): the native-variant rules, the per-symbol context, the evidence rows, the
red rule, the made-up mistakes and the pass bars. One live test runs the Korean-trained listener on the Zeroth
native recording in tests/fixtures (CC BY 4.0): a changed target turns red and names the sound really said.
"""
import random
from pathlib import Path

import numpy as np
import pytest

from backend.g2p import expected_phonemes
from backend.korean_any_sound import (MISSING, SWAP, accepted, context, dropped_ok, rival, rows_from, score,
                                      verdict)
from backend.korean_listener import to_mfa

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "zeroth_126_003_2058.wav"
NATIVE_TEXT = "강아지가 용변을 보도록 유도하는 말을 가르칠 수도 있다"
ON = {"enabled": True, "margin": 0.9, "right": 0.001, "sub_right": 0.001}


def row(target, others, **kw):
    """One evidence row. others = [(symbol, peak), ...] best first."""
    base = dict(target=target, right=0.5, others=others, op="match", heard=target, prev="A", next="A",
                prev_in_word="A", alt=set(), skip=False)
    return {**base, **kw}


# ---------- native variants are never mistakes ----------
def test_spelled_sound_is_fine_where_a_rule_made_it_tense_or_aspirated():
    assert accepted(row("GG", [], alt={"G"}), "G")          # 학교 said 학교 without the tensing (학꾜)
    assert not accepted(row("GG", []), "G")                  # 까 said 가: a real mistake


def test_standard_pronunciation_variants():
    assert accepted(row("euI", []), "I")                     # 의 said 이
    assert accepted(row("euI", []), "E")                     # the particle 의 said 에
    assert accepted(row("iE", [], prev_in_word="G"), "E")   # 계 said 게 (allowed except 예 / 례)
    assert not accepted(row("iE", [], prev_in_word=""), "E")   # 예 itself keeps its glide
    assert not accepted(row("iE", [], prev_in_word="R"), "E")  # 례 too
    assert accepted(row("k", []), "G")                       # a final ㄱ heard released
    assert not accepted(row("k", []), "t")                   # ...but not at another place
    assert not accepted(row("EO", []), "O")                  # ㅓ said ㅗ: a real mistake


def test_second_l_of_a_double_l_may_be_written_r():
    # 빨리: our G2P writes ㄹㄹ as [l l]; the listener's training labels write the second one as R (a notation
    # difference found on the smoke run: natives got "L said as R" at margin ~0.99 every time)
    assert accepted(row("L", [], prev="L"), "R")
    assert not accepted(row("L", [], prev="A"), "R")         # a single final ㄹ said as a tap is still checked


def test_a_r_linked_over_from_the_previous_word_may_stay_l():
    # 책을 읽었다 -> G2P 채그 릴걷따: the ㄹ of 을 moves into the next word. A native who pauses keeps it a final L.
    # (Found on the TUNE natives: 52 of the 56 worst R->L false alarms; the test speakers stay unseen.)
    assert accepted(row("R", [], prev="EU", prev_in_word=""), "L")
    assert not accepted(row("R", [], prev="EU", prev_in_word="EU"), "L")   # a tap inside a word said L: checked
    assert not accepted(row("R", [], prev="N", prev_in_word=""), "L")


def test_h_may_fade_between_voiced_sounds_only():
    assert dropped_ok(row("H", [], prev="N", next="oA"))     # 전화 said 저놔
    assert not dropped_ok(row("H", [], prev="", next="A"))   # a sentence-initial ㅎ must be there
    assert not dropped_ok(row("S", [], prev="A", next="A"))


def test_context_marks_rule_made_sounds_and_neighbours():
    words = expected_phonemes("학교에 좋다 같이", "ko")
    pairs = to_mfa(words)
    ctx = context(words, pairs)
    by_tok = {p[0] + str(i): c for i, (p, c) in enumerate(zip(pairs, ctx))}
    toks = [t for t, _ in pairs]
    gg = ctx[toks.index("GG")]
    assert gg["alt"] == {"G"} and gg["prev"] == "k" and gg["prev_in_word"] == "k"       # 학꾜: spelled ㄱ
    assert ctx[toks.index("Th")]["alt"] == {"D"}                                          # 조타: spelled ㄷ
    assert ctx[toks.index("CHh")]["alt"] == set()      # 가치: palatalised ㅌ is not "plain", stays checked
    assert ctx[0]["prev"] == "" and ctx[-1]["next"] == ""
    assert len(by_tok) == len(pairs)


# ---------- the evidence ----------
def test_rows_from_reads_the_peaks_inside_each_window():
    symbols = ["A", "O", "EO", "G"]
    probs = np.array([[0.9, 0.05, 0.05, 0.0],      # frame 0
                      [0.1, 0.1, 0.0, 0.8],        # frame 1
                      [0.0, 0.7, 0.2, 0.1]])       # frame 2
    pairs = [("A", [(0, 0)]), ("G", [(0, 1)]), ("EO", [(0, 2)])]
    rows = rows_from(probs, symbols, pairs, [(0, 1), (1, 2), (2, 3)], ["A", None, "O"], top=2)
    assert [r["op"] for r in rows] == ["match", "del", "sub"]
    assert rows[2]["right"] == pytest.approx(0.2) and rows[2]["heard"] == "O"
    assert rows[2]["others"][0] == ("O", pytest.approx(0.7)) and len(rows[2]["others"]) == 2
    assert rows[1]["cover"] == [(0, 1)] and rows[1]["index"] == 1


def test_rival_skips_native_variants():
    r = row("iE", [("E", 0.9), ("A", 0.3)], right=0.1, prev_in_word="G")
    assert rival(r) == ("A", pytest.approx(0.2))             # E is a fine way to say 계, so A is the real rival
    assert rival(row("A", [], right=0.1))[1] == -1.0          # nothing else in the window


# ---------- the red rule ----------
def test_verdict_swap_missing_and_green():
    assert verdict(row("EO", [("O", 0.99)], right=0.02), ON) == (SWAP, "O")
    assert verdict(row("EO", [("O", 0.5)], right=0.4), ON) is None                   # not clear enough
    assert verdict(row("EO", [("A", 0.1)], right=0.0005, op="sub", heard="O"), ON) == (SWAP, "O")
    assert verdict(row("iE", [("A", 0.1)], right=0.0005, op="sub", heard="E", prev_in_word="G"), ON) is None
    assert verdict(row("S", [("A", 0.1)], right=0.0001, op="del", heard=""), ON) == (MISSING, None)
    assert verdict(row("H", [("A", 0.1)], right=0.0001, op="del", heard="", prev="N", next="A"), ON) is None
    assert verdict(row("EO", [("O", 0.99)], right=0.0), {"enabled": False}) is None
    assert verdict(row("EO", [("O", 0.99)], right=0.0, skip=True), ON) is None


# ---------- the eval: made-up mistakes and the bars ----------
def test_variants_change_one_symbol_of_the_same_kind_or_add_one():
    from eval.korean_any_sound import kind, variants
    pairs = to_mfa(expected_phonemes(NATIVE_TEXT, "ko"))
    a = variants(pairs, random.Random(3), n_sub=4, n_del=2)
    assert a == variants(pairs, random.Random(3), n_sub=4, n_del=2)        # repeatable
    subs = [v for v in a if v[1][0] == "sub"]
    dels = [v for v in a if v[1][0] == "del"]
    assert len(subs) == 4 and len(dels) == 2
    for new, (cond, said, target, i) in subs:
        assert said == pairs[i][0] and new[i][0] == target != said and kind(target) == kind(said)
        assert len(new) == len(pairs)
    for new, (cond, said, target, i) in dels:
        assert said is None and new[i][0] == target and len(new) == len(pairs) + 1
        assert kind(target) != "final"                    # an added sound is never an unreleased final stop


def test_bars_decide_grade_hint_or_off():
    from eval.korean_any_sound import BARS, decide
    good = {"test_false_red": 0.04, "swaps_caught": 0.8, "lower_rated_gap_ci": (0.02, 0.1), "top_false_red": 0.1}
    assert decide(good) == "grade"
    assert decide(dict(good, top_false_red=BARS["top_false_red_grade"] + 0.01)) == "hint"
    assert decide(dict(good, test_false_red=BARS["test_false_red_max"] + 0.01)) == "off"
    assert decide(dict(good, swaps_caught=BARS["swaps_caught_min"] - 0.01)) == "off"
    assert decide(dict(good, lower_rated_gap_ci=(-0.01, 0.05))) == "off"
    assert decide(dict(good, lower_rated_gap_ci=None)) == "off"


def test_sentence_false_red_uses_the_live_rule():
    from eval.korean_any_sound import false_red
    s1 = [row("EO", [("O", 0.99)], right=0.0, speaker="a", utt="1"), row("A", [], speaker="a", utt="1")]
    s2 = [row("A", [("O", 0.2)], speaker="a", utt="2")]
    assert false_red(s1 + s2, ON) == pytest.approx(0.5)


# ---------- live: the Korean-trained listener on a native recording ----------
@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture missing")
def test_live_changed_vowel_turns_red_and_names_the_sound_said():
    import soundfile as sf
    from backend.korean_listener import emissions
    audio, sr = sf.read(FIXTURE, dtype="float32")
    lp = emissions(audio, sr)
    right = expected_phonemes(NATIVE_TEXT, "ko")
    assert score(lp, right, ON) == {}                                  # the native reading: nothing red
    wrong = expected_phonemes(NATIVE_TEXT.replace("말을", "멀을"), "ko")   # target ㅓ where the native said ㅏ
    found = score(lp, wrong, ON)
    wi = NATIVE_TEXT.split().index("말을")
    hits = {k: v for k, v in found.items() if k[0] == wi}
    assert hits and list(hits.values())[0] == (SWAP, "A")


# ---------- in /analyze: coloring the words (after the two live Korean checks) ----------
from backend.korean_any_sound import color, ipa_of, load_thresholds  # noqa: E402

LIVE = {"enabled": True, "mode": "grade", "margin": 1.0, "right": 0.0, "sub_right": 0.0001}


def kword(text, ipas, status="unchecked", not_heard=False):
    """A Korean word as match.finalize() leaves it: no sound checked yet."""
    return {"word": text, "pron": text, "status": status, "not_heard": not_heard,
            "phonemes": [{"ipa": p, "status": status, "checked": False} for p in ipas]}


def crow(cover, target, **kw):
    """An evidence row merged with its context, for the symbol covering `cover` = [(wi, pi), ...]."""
    return row(target, kw.pop("others", []), cover=cover, **kw)


def test_the_shipped_cut_is_the_measured_5_percent_grade_cut():
    from backend.korean_listener import MODEL, REVISION
    t = load_thresholds()
    assert (t["enabled"], t["mode"], t["cap"]) == (True, "grade", 0.05)
    assert (t["margin"], t["sub_right"], t["right"]) == (1.0, 0.0001, 0.0)   # left-out rule off (4% < 25% bar)
    assert (t["model"], t["revision"]) == (MODEL, REVISION)


def test_listener_symbols_map_back_to_the_sound_table():
    import json
    sounds = json.loads((ROOT / "content" / "articulation.json").read_text(encoding="utf-8"))["sounds"]["ko"]
    assert [ipa_of(s) for s in ("BB", "EU", "A", "E", "k", "JJ")] == ["p͈", "ɯ", "a", "e", "k", "t͈ɕ"]
    assert ipa_of("iEO") == "jʌ" and ipa_of("euI") == "ɰi"
    from backend.korean_any_sound import SYMBOLS
    for s in SYMBOLS:              # every symbol the listener can name has a mouth to draw (a glide + vowel: both)
        ipa = ipa_of(s)
        assert ipa in sounds or (ipa[0] in "jwɰ" and ipa[1:] in sounds), s


def test_a_swap_turns_the_sound_and_word_red_and_names_what_was_said():
    w = [kword("가", ["k", "a"])]
    out = color(w, [crow([(0, 0)], "G"), crow([(0, 1)], "A", op="sub", heard="EO", right=0.00001)], LIVE)
    p = out[0]["phonemes"][1]
    assert (p["status"], p["pair"], p["produced"], p["checked"]) == ("red", SWAP, "ʌ", True)
    assert out[0]["status"] == "red"


def test_a_swap_with_a_hand_written_tip_uses_that_tip():
    out = color([kword("거", ["k", "ʌ"])], [crow([(0, 1)], "EO", op="sub", heard="O", right=0.0)], LIVE)
    assert (out[0]["phonemes"][1]["pair"], out[0]["phonemes"][1]["produced"]) == ("eo_as_o", "o")
    out = color([kword("바", ["p", "a"])], [crow([(0, 0)], "B", op="sub", heard="BB", right=0.0)], LIVE)
    assert out[0]["phonemes"][0]["pair"] == "p_as_pp"          # the same tip the live tense check shows


def test_a_sound_heard_as_itself_is_green():
    out = color([kword("가", ["k", "a"])], [crow([(0, 0)], "G"), crow([(0, 1)], "A")], LIVE)
    assert [p["status"] for p in out[0]["phonemes"]] == ["green", "green"]
    assert all(p["checked"] for p in out[0]["phonemes"]) and out[0]["status"] == "green"


def test_a_native_variant_heard_is_green_too():
    out = color([kword("학교", ["h", "a", "k", "k͈", "j", "o"])],
                [crow([(0, 3)], "GG", op="sub", heard="G", alt={"G"})], LIVE)   # 학교 without the tensing
    assert out[0]["phonemes"][3]["status"] == "green"


def test_another_sound_heard_but_not_past_the_cut_is_neither_red_nor_green():
    # "no mistake found" is not proof the sound was right (same rule as korean_scoring.py)
    out = color([kword("발", ["p", "a", "l"])], [crow([(0, 0)], "B", op="sub", heard="M", right=0.3)], LIVE)
    p = out[0]["phonemes"][0]
    assert (p["status"], p["checked"]) == ("unchecked", False)


def test_a_sound_heard_as_nothing_stays_plain_while_the_left_out_rule_is_off():
    out = color([kword("가", ["k", "a"])], [crow([(0, 0)], "G", op="del", heard="", right=0.0)], LIVE)
    assert out[0]["phonemes"][0]["status"] == "unchecked"


def test_a_live_check_red_keeps_its_own_tip():
    w = [kword("수", ["s", "u"])]
    w[0]["phonemes"][1].update(status="red", pair="u_as_eu", produced="ɯ", checked=True)
    out = color(w, [crow([(0, 1)], "U", op="sub", heard="O", right=0.0)], LIVE)
    assert (out[0]["phonemes"][1]["pair"], out[0]["phonemes"][1]["produced"]) == ("u_as_eu", "ɯ")


def test_a_glide_and_vowel_symbol_marks_both_sounds_as_one_unit():
    out = color([kword("여", ["j", "ʌ"])], [crow([(0, 0), (0, 1)], "iEO", op="sub", heard="iO", right=0.0)], LIVE)
    ps = out[0]["phonemes"]
    assert [(p["status"], p["pair"], p["produced"], p["unit"]) for p in ps] == [("red", SWAP, "jo", "jʌ")] * 2


def test_words_not_heard_or_not_graded_are_left_alone():
    w = [kword("가", ["k", "a"], status="red", not_heard=True), kword("2", ["t", "u"])]
    for p in w[0]["phonemes"]:
        p["pair"] = "word_not_heard"
    rows = [crow([(0, 1)], "A", op="sub", heard="EO", right=0.0),
            crow([(1, 1)], "U", op="sub", heard="O", right=0.0, skip=True)]
    out = color(w, rows, LIVE)
    assert out[0]["phonemes"][1]["pair"] == "word_not_heard" and out[1]["phonemes"][1]["status"] == "unchecked"


def test_switched_off_changes_nothing_and_input_is_not_changed():
    w = [kword("거", ["k", "ʌ"])]
    rows = [crow([(0, 1)], "EO", op="sub", heard="O", right=0.0)]
    assert color(w, rows, {"enabled": False}) == w
    color(w, rows, LIVE)
    assert w[0]["phonemes"][1]["status"] == "unchecked"


# ---------- live: through /analyze, with the shipped cut ----------
def _analyze(text):
    from fastapi.testclient import TestClient
    from backend.app import app
    return TestClient(app).post("/analyze", files={"audio": ("a.wav", FIXTURE.read_bytes(), "audio/wav")},
                                data={"text": text, "lang": "ko"}).json()


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture missing")
def test_live_native_reading_is_all_green_or_plain_and_names_the_check():
    body = _analyze(NATIVE_TEXT)
    assert body["matched"] is True and "any_sound" in body["checks"]
    phones = [p for w in body["words"] for p in w["phonemes"]]
    assert not [p for p in phones if p["status"] == "red"]
    assert sum(p["status"] == "green" for p in phones) > len(phones) // 2     # most sounds graded now, not ~9


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture missing")
def test_live_text_asking_for_another_vowel_goes_red_there():
    body = _analyze(NATIVE_TEXT.replace("말을", "멀을"))        # the speaker said ㅏ where the text asks ㅓ
    w = next(w for w in body["words"] if w["word"] == "멀을")
    assert w["status"] == "red"
    assert (w["phonemes"][1]["ipa"], w["phonemes"][1]["produced"]) == ("ʌ", "a")
    assert [x["word"] for x in body["words"] if x["status"] == "red"] == ["멀을"]


# ---------- the eval also reports greens: a missed mistake must stay plain, not turn green ----------
def test_eval_counts_made_up_swaps_that_would_show_green():
    from eval.korean_any_sound import greens
    swaps = [row("EO", [], op="match", heard="EO", right=0.9),           # listener wrote the (wrong) target: green
             row("EO", [("O", 0.99)], op="sub", heard="O", right=0.0),   # caught: red
             row("EO", [], op="sub", heard="O", right=0.5)]              # missed, heard another: plain
    assert greens(swaps, ON) == {"green": 1, "n": 3, "rate": 0.3333}
    natives = [row("A", []), row("A", [], op="del", heard="")]
    assert greens(natives, ON)["green"] == 1
