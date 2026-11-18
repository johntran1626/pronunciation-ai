"""The README results block is generated from the results files, never typed by hand."""
import pytest

from eval.readme_results import END, START, fmt, gap_points, korean_rows, pair_rows, render, update_readme


def _k(k, n, lo, hi):
    return {"k": k, "n": n, "rate": k / n if n else None, "ci95": [lo, hi]}


def _pair(enabled, caught, fa, base_caught, base_fa, precision):
    return {"new": {"margin rule": {
        "enabled": enabled,
        "test (korean)": {"caught": caught, "false_alarms": fa, "precision": precision},
        "baseline (korean)": {"caught": base_caught, "false_alarms": base_fa},
    }, "passes bar": enabled}}


LISTENERS = {"pairs": {
    "l_as_r": _pair(False, _k(13, 37, 0.21, 0.51), _k(13, 1002, 0.0076, 0.022),
                    _k(21, 37, 0.41, 0.71), _k(40, 1002, 0.029, 0.054), 0.5),
    "r_as_l": _pair(True, _k(9, 18, 0.2903, 0.7097), _k(1, 1070, 0.0002, 0.0053),
                    _k(12, 18, 0.4375, 0.8372), _k(127, 1070, 0.1007, 0.1394), 0.9),
}}

MATCH = {"caps": {"sentence": 0.01, "word": 0.002}, "en": {
    "sentence": {"enabled": True, "test": {
        "orig": _k(0, 600, 0.0, 0.0064), "other": _k(598, 600, 0.9879, 0.9991),
        "noise": _k(24, 24, 0.862, 1.0), "swap": _k(2, 600, 0.0009, 0.0121), "cut": _k(6, 600, 0.0046, 0.0216)}},
    "word": {"enabled": True, "test": {
        "false_not_heard_human_correct": _k(2, 3919, 0.0001, 0.0019),
        "false_not_heard_all_words": _k(8, 5620, 0.0007, 0.0028),
        "caught_cut": _k(295, 600, 0.4518, 0.5316), "caught_swap": _k(360, 600, 0.5603, 0.6384)}},
}}


def test_fmt_shows_count_rate_and_interval():
    assert fmt(_k(9, 18, 0.2903, 0.7097)) == "9/18 (50%; 29–71%)"
    # rates under 1% keep two decimals, so 1 in 1,070 doesn't print as "0%"
    assert fmt(_k(1, 1070, 0.0002, 0.0053)) == "1/1,070 (0.09%; 0.02–0.53%)"


def test_fmt_decimals_per_number_so_nothing_looks_better_or_vaguer():
    # 1.3% must not print as "1%" next to a 0.5% cap, and a 0.76% lower bound must not print as "1"
    assert fmt(_k(13, 1002, 0.0076, 0.022)) == "13/1,002 (1.3%; 0.76–2.2%)"
    # 598/600 must not print as "100%"
    assert fmt(_k(598, 600, 0.9879, 0.9991)) == "598/600 (99.7%; 98.8–99.9%)"
    assert fmt(_k(24, 24, 0.862, 1.0)) == "24/24 (100%; 86–100%)"


def test_render_names_the_speakers_of_the_sentence_and_word_checks():
    md = render(LISTENERS, MATCH)
    assert "600 readings by L2-ARCTIC's 4 Korean speakers" in md


def test_fmt_handles_missing():
    assert fmt(None) == "—"
    assert fmt({"k": 0, "n": 0, "rate": None, "ci95": None}) == "—"


def test_pair_rows_live_pairs_first_and_uses_the_app_rule():
    rows = pair_rows(LISTENERS)
    assert [r["pair"] for r in rows] == ["r_as_l", "l_as_r"]   # in the app first
    r = rows[0]
    assert r["in_app"] == "yes"
    assert r["caught"] == "9/18 (50%; 29–71%)"
    assert r["false_alarms"] == "1/1,070 (0.09%; 0.02–0.53%)"
    assert r["reds_right"] == "90%"
    assert r["baseline_false_alarms"].startswith("127/1,070")
    assert rows[1]["in_app"] == "off (failed the bar)"


def test_pair_rows_unknown_pair_fails_loudly():
    bad = {"pairs": {"made_up": LISTENERS["pairs"]["r_as_l"]}}
    with pytest.raises(KeyError):
        pair_rows(bad)


def test_render_has_markers_and_real_counts():
    md = render(LISTENERS, MATCH)
    assert md.startswith(START) and md.rstrip().endswith(END)
    assert "English R said as L" in md
    assert "127/1,070" in md                       # baseline shown next to ours
    assert "0/600" in md and "598/600" in md       # sentence check
    assert "2/3,919" in md                         # word check on correct words
    assert "estimated from audio" in md.lower()
    assert "TODO" not in md


def test_update_readme_replaces_only_the_block():
    old = f"# Title\n\nIntro.\n\n{START}\nold numbers\n{END}\n\n## Method\nkept\n"
    new = update_readme(old, f"{START}\nnew numbers\n{END}\n")
    assert "old numbers" not in new and "new numbers" in new
    assert new.startswith("# Title\n\nIntro.") and new.endswith("## Method\nkept\n")


def test_update_readme_without_markers_inserts_after_title():
    new = update_readme("# Title\n\nWork in progress.\n", f"{START}\nx\n{END}\n")
    assert new.startswith(f"# Title\n\n{START}\nx\n{END}\n")
    assert "Work in progress." in new


def test_update_readme_is_idempotent():
    block = render(LISTENERS, MATCH)
    once = update_readme("# Title\n", block)
    assert update_readme(once, block) == once


# ---------- Korean (English speakers learning Korean) ----------

def _bar(k, n, lo, hi, cap=None, ok=True):
    return {**_k(k, n, lo, hi), "cap": cap, "pass": ok}


def _check(live, b1, b2, gap, b4):
    """b1, b2, b4 = (k, n, lo, hi, pass); gap = (top rate, lower rate, lo, hi, pass)."""
    top, low, glo, ghi, gok = gap
    return {"cut": 0.9, "tune_correct": 1000, "live": live,
            "bar1": _bar(*b1[:4], cap=0.005, ok=b1[4]), "bar2": _bar(*b2[:4], cap=0.01, ok=b2[4]),
            "bar3": {"top": {"rate": top}, "lower_rated": {"rate": low}, "gap": low - top,
                     "gap_ci95_by_speaker": [glo, ghi], "pass": gok},
            "bar4": {**_k(*b4[:4]), "speakers": 10, "bar": 0.25, "pass": b4[4]}}


KOREAN = {
    "model": "slplab/wav2vec2-xls-r-300m_phone-mfa_korean",
    "recordings": {"natives": 1368, "learners": 4453, "learner_speakers": 151},
    "settings": {"bar1": 0.005, "bar2": 0.01, "bar4": 0.25},
    "checks": {
        "ㅓ_as_ㅗ": _check(False, (7, 1830, 0.0019, 0.0079, True), (292, 10061, 0.0259, 0.0325, False),
                          (0.029, 0.0504, 0.0098, 0.0356, True), (350, 445, 0.7461, 0.8221, True)),
        "ㅜ_as_ㅡ": _check(True, (2, 1319, 0.0004, 0.0055, True), (23, 4168, 0.0037, 0.0083, True),
                          (0.0055, 0.0153, 0.0049, 0.015, True), (358, 456, 0.7451, 0.8203, True)),
        "asp_as_tense": _check(False, (9, 900, 0.005, 0.02, False), (50, 2000, 0.02, 0.03, False),
                               (0.025, 0.028, -0.0101, 0.016, False), (188, 237, 0.74, 0.84, True)),
    },
}


def test_gap_points_shows_the_interval_with_signs():
    assert gap_points(0.0049, 0.015) == "+0.49 to +1.5 points"
    assert gap_points(-0.0101, 0.016) == "−1.0 to +1.6 points"


def test_korean_rows_live_first_and_name_the_failed_bars():
    rows = korean_rows(KOREAN)
    assert [r["check"] for r in rows] == ["ㅜ_as_ㅡ", "ㅓ_as_ㅗ", "asp_as_tense"]
    assert rows[0]["in_app"] == "yes"
    assert rows[1]["in_app"] == "off (failed bar 2)"
    assert rows[2]["in_app"] == "off (failed bars 1, 2, 3)"


def test_korean_rows_numbers_come_from_the_file():
    r = korean_rows(KOREAN)[0]
    assert r["label"] == "ㅜ said like ㅡ"
    assert r["natives"] == "2/1,319 (0.15%; 0.04–0.55%)"
    assert r["top_learners"] == "23/4,168 (0.55%; 0.37–0.83%)"
    assert r["gap"] == "0.55% → 1.5% (+0.49 to +1.5 points)"
    assert r["simulated"] == "358/456 (79%; 75–82%)"


def test_korean_rows_unknown_check_fails_loudly():
    bad = {**KOREAN, "checks": {"made_up": KOREAN["checks"]["ㅜ_as_ㅡ"]}}
    with pytest.raises(KeyError):
        korean_rows(bad)


def test_render_with_korean_has_the_table_and_its_caveats():
    md = render(LISTENERS, MATCH, korean=KOREAN)
    assert "## Results: English speakers learning Korean" in md
    assert "| ㅜ said like ㅡ | yes |" in md
    assert "4,453 readings by 151" in md
    assert "upper bound" in md.lower() and "simulated" in md.lower()
    assert "no real detection rate" in md.lower()
    assert "the sound checks are off" not in md          # the old sentence is gone once the table exists
    assert md.rstrip().endswith(END)


def test_render_without_korean_says_so():
    md = render(LISTENERS, MATCH)
    assert "English speakers learning Korean" in md and "not run yet" in md


# ---------- the every-sound checks and the Korean "did you say it?" checks ----------
from eval.readme_results import count_of, any_sound_block, korean_any_sound_block, korean_match_block  # noqa: E402

ANY_EN = {"live_cap": 0.05, "sentences": {"tune": 5097, "test": 3984, "korean": 600}, "caps": {"0.05": {
    "false_red_sentences": {"tune": 0.0494, "test": 0.0419, "korean": 0.0567},
    "swaps_stressed": {"caught": 9438, "n": 9891}, "swaps_stressed_vowels": {"caught": 2283, "n": 2576},
    "swaps_stressed_consonants": {"caught": 7155, "n": 7315}, "said_sound_named_right": {"caught": 9195, "n": 9438},
    "left_out": {"caught": 4173, "n": 7918}}}}

KO_ANY = {"live_cap": 0.05, "bars": {"test_false_red_max": 0.075, "swaps_caught_min": 0.5, "left_out_min": 0.25,
                                      "top_false_red_grade": 0.2}, "caps": {"0.05": {
    "left_out_rule_on": False, "verdict": "grade",
    "readings": {"tune": 320, "test": 457, "learners": 635, "learners_2": 806, "learners_1": 195},
    "false_red_readings": {"tune": 0.0469, "test": 0.035, "learners": 0.1039, "learners_2": 0.1377, "learners_1": 0.2051},
    "swaps": {"caught": 1106, "n": 1805, "said_named_right": 1044}, "swaps_vowel": {"caught": 470, "n": 787},
    "swaps_consonant": {"caught": 630, "n": 972}, "swaps_final": {"caught": 6, "n": 46},
    "left_out": {"caught": 38, "n": 914}, "lower_rated_gap_ci": [0.0091, 0.0857],
    "swaps_green": {"green": 11, "n": 1805}, "test_sounds_green": {"green": 40121, "n": 43161}}}}

KO_MATCH = {"recordings": {"natives_test": 457}, "bars": {"natives_rejected": 0.01, "learners_rejected": 0.02,
                                                          "natives_false_word": 0.005, "learners_false_word": 0.01},
            "listeners": {"ko": {
    "sentence": {"test_natives": {"orig": _k(1, 457, 0.0004, 0.0123), "other": _k(456, 457, 0.9877, 0.9996)},
                 "noise": _k(24, 24, 0.862, 1.0)},
    "word": {"test_natives": {"false_not_heard_all_words": _k(15, 6623, 0.0014, 0.0037),
                              "caught_cut": _k(282, 457, 0.5717, 0.6605), "caught_swap": _k(230, 457, 0.4576, 0.5489)}},
    "learners_by_rating": {
        "learners": {"sentence_rejected": _k(0, 635, 0.0, 0.006), "words_flagged": _k(6, 9850, 0.0003, 0.0013)},
        "learners_2": {"sentence_rejected": _k(0, 772, 0.0, 0.005), "words_flagged": _k(14, 12107, 0.0007, 0.0019)},
        "learners_1": {"sentence_rejected": _k(3, 44, 0.0235, 0.1823), "words_flagged": _k(1, 672, 0.0003, 0.0084)}}}}}


def test_count_of_recovers_the_exact_count_from_a_rounded_rate():
    assert count_of(0.0419, 3984) == 167 and count_of(0.0567, 600) == 34 and count_of(0.2051, 195) == 40
    with pytest.raises(ValueError):
        count_of(0.0419, 10)          # no whole count gives that rate: the file and the n don't belong together


def test_english_every_sound_block_counts_and_caveats():
    md = "\n".join(any_sound_block(ANY_EN))
    assert "167/3,984 (4.2%" in md                 # native test sentences with a wrong red
    assert "34/600 (5.7%" in md                    # Korean speakers' sentences, only annotator-correct sounds
    assert "9,438/9,891 (95.4%" in md and "4,173/7,918 (53%" in md
    assert "5%" in md and "text" in md.lower()     # the cap, and how the mistakes are made


def test_korean_every_sound_block_counts_bars_and_greens():
    md = "\n".join(korean_any_sound_block(KO_ANY))
    assert "16/457 (3.5%" in md
    assert "66/635 (10%" in md and "111/806 (14%" in md and "40/195 (21%" in md
    assert "+0.91 to +8.6 points" in md
    assert "1,106/1,805 (61%" in md and "6/46 (13%" in md
    assert "11/1,805" in md                        # missed swaps that would show green
    assert "38/914" in md and "off" in md          # the left-out rule failed its bar
    assert "upper bound" in md.lower()
    assert "passed every bar, so it marks sounds red" in md and "grade" not in md


def test_korean_match_block_reads_the_korean_listener():
    md = "\n".join(korean_match_block(KO_MATCH))
    assert "1/457 (0.22%" in md and "456/457 (99.8%" in md and "24/24" in md
    assert "0/635" in md and "3/44 (6.8%" in md
    assert "15/6,623 (0.23%" in md and "282/457 (62%" in md and "230/457 (50%" in md


def test_render_puts_each_new_block_in_its_language_section():
    md = render(LISTENERS, MATCH, korean=KOREAN, any_en=ANY_EN, ko_match=KO_MATCH, ko_any=KO_ANY)
    en, ko = md.split("## Results: English speakers learning Korean")
    assert "167/3,984" in en and "16/457 (3.5%" in ko and "456/457" in ko
    assert md.rstrip().endswith(END)


NB = {"adopt": True, "settings": {"cut": 0.8}, "n_pairs": 672, "with_never_blurred": {
    "false_red_sentences": {"tune": 0.0494, "test": 0.0452, "korean": 0.0817},
    "swaps_stressed": {"caught": 9568, "n": 9891}, "swaps_stressed_vowels": {"caught": 2378, "n": 2576},
    "swaps_stressed_consonants": {"caught": 7190, "n": 7315}, "said_sound_named_right": {"caught": 9300, "n": 9568},
    "left_out": {"caught": 4173, "n": 7918}, "real_learner_substitutions": {"caught": 100, "n": 1518}}}


def test_english_every_sound_block_uses_the_live_never_blurred_numbers_and_real_mistakes():
    md = "\n".join(any_sound_block(ANY_EN, NB))
    assert "180/3,984 (4.5%" in md and "49/600 (8.2%" in md     # the live cut, not the older one
    assert "167/3,984" not in md and "34/600" not in md
    assert "9,568/9,891" in md and "2,378/2,576" in md
    assert "100/1,518 (6.6%" in md                               # real annotated mistakes, not made-up swaps
    assert "0.8" in md and "672" in md


def test_english_every_sound_block_ignores_a_never_blurred_run_that_was_not_adopted():
    md = "\n".join(any_sound_block(ANY_EN, dict(NB, adopt=False)))
    assert "167/3,984 (4.2%" in md and "1,518" not in md
