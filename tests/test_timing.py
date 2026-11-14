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


# ---------- the same timing against the live server (python -m eval.timing --live URL) ----------
import io

import httpx
import numpy as np
import soundfile as sf

from eval.readme_results import live_timing_line
from eval.timing import Pacer, post_timed, wav16k_bytes

LIVE = dict(TIMING, machine="Hugging Face Space, cpu-basic hardware",
            timed="round trip of POST /analyze from a laptop: upload, queue, analysis and answer",
            seconds_per_sentence={"n": 600, "median": 1.234, "p95": 2.345, "max": 3.456},
            health_round_trip={"n": 20, "median": 0.312, "p95": 0.401, "max": 0.5})


def test_wav16k_bytes_is_what_the_browser_uploads():
    # the frontend resamples to 16 kHz mono 16-bit WAV before /analyze; time the same upload size
    sr = 44100
    audio = (0.3 * np.sin(2 * np.pi * 220 * np.arange(2 * sr) / sr)).astype("float32")
    info = sf.info(io.BytesIO(wav16k_bytes(audio, sr)))
    assert (info.samplerate, info.channels, info.subtype) == (16000, 1, "PCM_16")
    assert info.duration == pytest.approx(2.0, abs=0.01)


def test_pacer_keeps_request_starts_far_enough_apart_for_the_rate_limit():
    now, slept = [0.0], []

    def sleep(s):
        slept.append(s)
        now[0] += s

    p = Pacer(gap_s=3.2, clock=lambda: now[0], sleep=sleep)
    p.wait()                 # first request: no wait
    now[0] += 1.0            # it took 1 s
    p.wait()                 # so wait the other 2.2 s
    now[0] += 5.0            # a slow one: already past the gap
    p.wait()
    assert slept == [pytest.approx(2.2)]


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://space.test")


def test_post_timed_sends_what_the_browser_sends():
    seen = {}

    def handler(req):
        seen["path"], seen["body"] = req.url.path, req.read()
        return httpx.Response(200, json={"words": []})

    assert post_timed(_client(handler), b"RIFFwav", "Thank you.", "en", sleep=lambda s: None) >= 0
    assert seen["path"] == "/analyze"
    for part in (b'name="text"', b"Thank you.", b'name="lang"', b"en", b'name="audio"', b".wav", b"RIFFwav"):
        assert part in seen["body"]


def test_post_timed_waits_out_a_429_and_times_only_the_answered_try():
    tries, slept = [], []

    def handler(req):
        tries.append(1)
        if len(tries) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={"detail": "slow down"})
        return httpx.Response(200, json={"words": []})

    assert post_timed(_client(handler), b"wav", "hi", "en", sleep=slept.append) >= 0
    assert len(tries) == 2 and slept == [7]


def test_post_timed_returns_none_when_the_app_refuses_the_reading():
    # 400 = the app's own "can't analyse this" answer (the local run skips the same readings)
    h = lambda req: httpx.Response(400, json={"detail": "recording is too short"})
    assert post_timed(_client(h), b"wav", "hi", "en", sleep=lambda s: None) is None


def test_post_timed_stops_on_a_server_error():
    h = lambda req: httpx.Response(503, text="Space is restarting")
    with pytest.raises(RuntimeError, match="503"):
        post_timed(_client(h), b"wav", "hi", "en", sleep=lambda s: None)


def test_live_timing_line_says_it_is_a_round_trip_on_the_server():
    line = live_timing_line(LIVE)
    assert "median 1.23 s" in line and "slowest 5% took 2.35 s or more" in line
    assert "cpu-basic" in line and "600 readings" in line
    assert "network" in line and "0.31 s" in line   # how much of it is just the trip, so it can be read


def test_render_with_live_timing_adds_the_server_line_next_to_the_laptop_one():
    md = render(LISTENERS, MATCH, TIMING, LIVE)
    assert "median 0.21 s" in md and "median 1.23 s" in md


def test_render_refuses_live_timing_from_another_listener():
    with pytest.raises(ValueError):
        render(LISTENERS, MATCH, TIMING, dict(LIVE, listener="old"))
