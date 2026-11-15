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
