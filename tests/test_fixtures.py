"""The whole /analyze pipeline on 3 COMMITTED recordings, so the tests run
without the git-ignored corpora. Native speakers reading correctly -> everything should be green.
Files and licenses: tests/fixtures/fixtures.json and tests/fixtures/LICENSES.md."""
import json
from pathlib import Path

import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from backend.app import MAX_SECONDS, app
from backend.g2p import expected_phonemes
from backend.listener import live_listener
from backend.scoring import PAIRS, load_thresholds

FIXTURES = Path(__file__).with_name("fixtures")
MANIFEST = json.loads((FIXTURES / "fixtures.json").read_text(encoding="utf-8")) if (FIXTURES / "fixtures.json").exists() else []
client = TestClient(app)


def analyze(fx):
    wav = (FIXTURES / fx["file"]).read_bytes()
    return client.post("/analyze", files={"audio": (fx["file"], wav, "audio/wav")},
                       data={"text": fx["text"], "lang": fx["lang"]})


def test_three_fixtures_two_languages_with_licenses():
    assert len(MANIFEST) == 3
    assert {fx["lang"] for fx in MANIFEST} == {"en", "ko"}
    assert (FIXTURES / "LICENSES.md").exists()
    for fx in MANIFEST:
        assert sf.info(str(FIXTURES / fx["file"])).duration <= MAX_SECONDS
        assert fx["source"] and fx["license"]


@pytest.mark.parametrize("fx", MANIFEST, ids=[fx["file"] for fx in MANIFEST])
def test_pipeline_end_to_end(fx):
    r = analyze(fx)
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] is True  # a native reading the right sentence must pass the sentence check
    assert [w["word"] for w in body["words"]] == [w["word"] for w in expected_phonemes(fx["text"], fx["lang"])]
    starts = [p["start"] for w in body["words"] for p in w["phonemes"]]
    assert starts == sorted(starts) and 0 <= starts[0] and starts[-1] < body["duration_s"]
    for w in body["words"]:
        assert "".join(d["text"] for d in w["display"]) == w["word"]
        for p in w["phonemes"]:
            assert p["op"] in ("match", "sub", "del") and p["status"] in ("green", "red", "unchecked") and "source" in p


@pytest.mark.parametrize("fx", MANIFEST, ids=[fx["file"] for fx in MANIFEST])
def test_native_speaker_reading_correctly_gets_no_red(fx):
    # a false red here = a false alarm on a native speaker (false alarms first). Sounds
    # with no live check are "unchecked" (Korean: all of them), so the promise is "no red", not "all green".
    body = analyze(fx).json()
    assert body["matched"] is True
    assert all(w["status"] != "red" for w in body["words"])
    if fx["lang"] == "en":
        # green only where a live sound check passed; every other word is plain. Which sounds are checked
        # comes from the thresholds of the listener the app runs, so this follows a listener switch.
        targets = checked_targets(fx["lang"])
        assert targets, "no live English sound check"
        for w in body["words"]:
            checked = any(p["ipa"] in targets for p in w["phonemes"])
            assert w["status"] == ("green" if checked else "unchecked"), w["word"]


def checked_targets(lang):
    """Target sounds of the enabled per-sound checks for the listener the app runs for lang.
    extra_vowel has no target sound (it looks after a word-final consonant), so it never makes a word green."""
    pairs = load_thresholds(live_listener(lang)).get("pairs", {})
    return {PAIRS[name]["target"] for name, t in pairs.items() if t.get("enabled") and name in PAIRS}
