"""Pack reference clips made ahead of time, so pack mode plays native audio without new Azure calls."""
import json
import re
from pathlib import Path

import pytest

from backend import bake_refs
from backend.native import timings_path
from backend.packs import _all_packs
from backend.tts import TTSError, clip_path

ROOT = Path(__file__).resolve().parent.parent
WAV = b"RIFF" + b"\0" * 40


def fake_timings(calls):
    def run(wav_path, text, lang):
        calls.append((text, lang))
        timings_path(wav_path).write_text(json.dumps({"text": text}), encoding="utf-8")
    return run


def small_set(monkeypatch):
    clips = [("같이 가요.", "ko", 0), ("같이 가요.", "ko", -30), ("Very light.", "en", 0), ("Very light.", "en", -30)]
    monkeypatch.setattr(bake_refs, "reference_clips", lambda: clips)
    return clips


def test_every_learner_sentence_at_both_speeds_and_no_dev_packs():
    clips = bake_refs.reference_clips()
    learner = [(i["text"], p["lang"]) for p in _all_packs().values() if not p.get("dev_only") for i in p["items"]]
    dev = {i["text"] for p in _all_packs().values() if p.get("dev_only") for i in p["items"]}
    assert len(learner) > 0
    assert sorted(clips) == sorted((t, lang, r) for t, lang in learner for r in (0, bake_refs.SLOW_RATE))
    assert not dev & {t for t, _, _ in clips}


def test_slow_rate_matches_the_frontend_slower_button():
    api = (ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
    assert int(re.search(r"SLOW_RATE\s*=\s*(-?\d+)", api).group(1)) == bake_refs.SLOW_RATE


def test_bake_makes_every_clip_and_timings_for_normal_speed_only(tmp_path, monkeypatch):
    clips = small_set(monkeypatch)
    fetched, timed = [], []
    report = bake_refs.bake(cache_dir=tmp_path, fetch=lambda ssml: fetched.append(ssml) or WAV,
                            timings=fake_timings(timed), sleep=lambda s: None)
    assert len(fetched) == 4
    assert sorted(timed) == [("Very light.", "en"), ("같이 가요.", "ko")]
    for text, lang, rate in clips:
        assert clip_path(text, lang, rate=rate, cache_dir=tmp_path).exists()
    assert report == {"new_clips": 4, "new_chars": 2 * len("같이 가요.") + 2 * len("Very light."), "timed": 2}


def test_second_bake_is_free(tmp_path, monkeypatch):
    small_set(monkeypatch)
    bake_refs.bake(cache_dir=tmp_path, fetch=lambda ssml: WAV, timings=fake_timings([]), sleep=lambda s: None)
    fetched = []
    report = bake_refs.bake(cache_dir=tmp_path, fetch=lambda ssml: fetched.append(ssml) or WAV,
                            timings=fake_timings([]), sleep=lambda s: None)
    assert fetched == []
    assert report["new_clips"] == 0 and report["new_chars"] == 0


def test_waits_and_retries_when_azure_says_too_many_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(bake_refs, "reference_clips", lambda: [("Hi.", "en", -30)])
    replies, waits = [TTSError("Azure TTS failed: HTTP 429 Too Many Requests"), WAV], []

    def fetch(ssml):
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    bake_refs.bake(cache_dir=tmp_path, fetch=fetch, timings=fake_timings([]), sleep=waits.append)
    assert clip_path("Hi.", "en", rate=-30, cache_dir=tmp_path).exists()
    assert bake_refs.RETRY_WAIT_S in waits


def test_other_azure_errors_stop_the_bake(tmp_path, monkeypatch):
    monkeypatch.setattr(bake_refs, "reference_clips", lambda: [("Hi.", "en", -30)])

    def fetch(ssml):
        raise TTSError("Azure TTS failed: HTTP 401 Unauthorized")

    with pytest.raises(TTSError, match="401"):
        bake_refs.bake(cache_dir=tmp_path, fetch=fetch, timings=fake_timings([]), sleep=lambda s: None)


def test_dry_run_counts_without_calling_azure(tmp_path, monkeypatch):
    small_set(monkeypatch)
    plan = bake_refs.plan(cache_dir=tmp_path)
    assert plan == {"clips": 4, "missing_clips": 4, "missing_chars": 2 * len("같이 가요.") + 2 * len("Very light.")}


def test_ship_list_names_every_file_relative_to_the_cache(tmp_path, monkeypatch):
    small_set(monkeypatch)
    bake_refs.bake(cache_dir=tmp_path, fetch=lambda ssml: WAV, timings=fake_timings([]), sleep=lambda s: None)
    files = bake_refs.ship_list(cache_dir=tmp_path)
    assert len(files) == 4 + 2                       # 4 clips + timings for the 2 normal-speed ones
    assert all("/" not in f for f in files)
    assert all((tmp_path / f).exists() for f in files)


def test_ship_list_refuses_when_something_is_missing(tmp_path, monkeypatch):
    small_set(monkeypatch)
    with pytest.raises(bake_refs.MissingRefs, match="4 of 4"):
        bake_refs.ship_list(cache_dir=tmp_path)
