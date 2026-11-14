"""Processing time per sentence: what the app's analysis costs, summarised the same way every time."""
import pytest

from eval.readme_results import render, timing_line
from eval.timing import summarize
from tests.test_readme_results import LISTENERS, MATCH

TIMING = {
    "listener": "listener_v1", "lang": "en", "machine": "Apple M3 Pro, 12 CPU cores", "device": "cpu",
    "data": "L2-ARCTIC, 4 Korean speakers",
    "seconds_per_sentence": {"n": 600, "median": 0.214, "p95": 0.391, "max": 0.802},
    "audio_seconds": {"n": 600, "median": 3.61, "p95": 5.02, "max": 7.4},
}


def test_summarize_median_p95_max():
    s = summarize([0.5, 0.1, 0.3, 0.2, 0.4])
    assert s == {"n": 5, "median": 0.3, "p95": 0.4, "max": 0.5}


def test_summarize_p95_is_the_value_below_which_95_percent_fall():
    # same rule as eval/run.py: sorted[int(0.95 * (n - 1))], so old and new numbers compare
    secs = [i / 100 for i in range(1, 101)]   # 0.01 .. 1.00
    assert summarize(secs)["p95"] == 0.95
    assert summarize(secs)["max"] == 1.0


def test_summarize_refuses_no_data():
    with pytest.raises(ValueError):
        summarize([])


def test_timing_line_gives_median_slowest_5_percent_and_where_it_ran():
    line = timing_line(TIMING)
    assert "median 0.21 s" in line
    assert "slowest 5% took 0.39 s or more" in line
    assert "600 readings" in line
    assert "Apple M3 Pro" in line and "CPU" in line
    assert "3.6 s" in line   # how long the recordings were, so the time means something


def test_render_without_timing_says_not_measured():
    assert "not yet measured" in render(LISTENERS, MATCH)


def test_render_with_timing_puts_the_numbers_in_the_readme():
    md = render(LISTENERS, MATCH, TIMING)
    assert "not yet measured" not in md
    assert "median 0.21 s" in md


def test_render_refuses_timing_from_another_listener():
    # the README table is the fine-tuned listener; a time measured on the old one must not sit under it
    with pytest.raises(ValueError):
        render(LISTENERS, MATCH, dict(TIMING, listener="facebook/wav2vec2-xlsr-53-espeak-cv-ft"))
