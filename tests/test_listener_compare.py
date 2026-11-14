"""Switching the listener (old vs fine-tuned) and the old-vs-new pass-bar comparison, on small made-up data.
No model is loaded: from_pretrained and vocab are faked."""
import importlib
from pathlib import Path

import numpy as np
import pytest

import backend.align as align
from eval import listener as L

NEW = "/x/data/models/listener_v1/best"


# ---------- 1. which listener is loaded ----------
def test_default_listener_is_the_original_model(monkeypatch):
    monkeypatch.delenv(align.LISTENER_ENV, raising=False)
    assert align.listener() == align.MODEL
    assert align.listener_tag() == ""


def test_env_var_picks_the_fine_tuned_listener(monkeypatch):
    monkeypatch.setenv(align.LISTENER_ENV, NEW)
    assert align.listener() == NEW
    assert align.listener_tag() == "listener_v1"           # 'best' is named after its run folder
    assert align.listener_tag("/x/some_model") == "some_model"
    assert align.listener_tag(align.MODEL) == ""


@pytest.fixture
def fresh_model_cache():
    align._model.cache_clear()
    yield
    align._model.cache_clear()


def _fake_loader(monkeypatch, vocab_size):
    import transformers
    seen = []

    class FakeModel:
        def __init__(self, name):
            seen.append(name)
            self.config = type("C", (), {"vocab_size": vocab_size, "pad_token_id": 0})()

        def eval(self):
            return self

    monkeypatch.setattr(transformers.Wav2Vec2ForCTC, "from_pretrained", classmethod(lambda cls, n: FakeModel(n)))
    monkeypatch.setattr(transformers.Wav2Vec2FeatureExtractor, "from_pretrained",
                        classmethod(lambda cls, n: seen.append(("extractor", n)) or "extractor"))
    monkeypatch.setattr(align, "vocab", lambda: {"a": 0, "b": 1, "c": 2})
    return seen


def test_model_loads_from_the_chosen_listener(monkeypatch, fresh_model_cache):
    seen = _fake_loader(monkeypatch, vocab_size=3)
    monkeypatch.setenv(align.LISTENER_ENV, NEW)
    extractor, model = align._model()
    assert NEW in seen and ("extractor", NEW) in seen


def test_model_with_a_different_symbol_set_is_refused(monkeypatch, fresh_model_cache):
    _fake_loader(monkeypatch, vocab_size=5)                # 5 outputs, but the vocab has 3 symbols
    monkeypatch.setenv(align.LISTENER_ENV, NEW)
    with pytest.raises(ValueError, match="symbols"):
        align._model()


# ---------- 2. the new listener never overwrites the old caches ----------
def test_tagged_paths():
    p = Path("data/cache/eval_l2arctic.csv")
    assert L.tagged(p, "") == p
    assert L.tagged(p, "listener_v1") == Path("data/cache/listener_v1/eval_l2arctic.csv")
    assert L.tagged(Path("data/cache/saa_all_align"), "listener_v1") == Path("data/cache/listener_v1/saa_all_align")


def test_cache_builders_write_to_the_tagged_folder(monkeypatch):
    import eval.extra_corpora as ec
    import eval.l2arctic as l2
    import eval.saa as saa
    monkeypatch.setenv(align.LISTENER_ENV, NEW)
    try:
        for m in (l2, ec, saa):
            importlib.reload(m)
        assert "listener_v1" in str(l2.OUT) and "listener_v1" in str(l2.TIMING)
        assert all("listener_v1" in str(p) for p in ec.OUT.values())
        assert "listener_v1" in str(saa.SETS["all"]["cache"]) and "listener_v1" in str(saa.SETS["all"]["align"])
        assert "listener_v1" in str(saa.SAA_FEATURES)
    finally:
        monkeypatch.delenv(align.LISTENER_ENV)
        for m in (l2, ec, saa):
            importlib.reload(m)
    assert "listener_v1" not in str(l2.OUT)                # back to the old listener's paths


# ---------- 3. only held-out speakers (dev + Korean test) are run for the new listener ----------
def test_keep_speaker_heldout(monkeypatch):
    monkeypatch.setenv(align.LISTENER_ENV, NEW)
    monkeypatch.setenv(L.SPEAKERS_ENV, "heldout")
    assert L.keep_speaker("l2arctic", "SKA", False)        # a dev speaker
    assert not L.keep_speaker("l2arctic", "ABA", False)    # a training speaker: the new listener has heard them
    assert L.keep_speaker("l2arctic", "HJK", True)         # Korean test speaker
    monkeypatch.setenv(L.SPEAKERS_ENV, "all")
    assert L.keep_speaker("l2arctic", "ABA", False)


def test_heldout_with_the_old_listener_is_refused(monkeypatch):
    """It would overwrite the old listener's FULL caches with a partial run."""
    monkeypatch.delenv(align.LISTENER_ENV, raising=False)
    monkeypatch.setenv(L.SPEAKERS_ENV, "heldout")
    with pytest.raises(ValueError, match="old listener"):
        L.keep_speaker("l2arctic", "SKA", False)


def test_unknown_speaker_mode_is_refused(monkeypatch):
    monkeypatch.setenv(L.SPEAKERS_ENV, "everyone")
    with pytest.raises(ValueError):
        L.keep_speaker("l2arctic", "SKA", False)


# ---------- 4. the comparison ----------
from eval import compare_listeners as C  # noqa: E402


def row(speaker, human, x, group="others", utt="u", wi=0, pi=0):
    return {"speaker": f"saa:{speaker}", "source": "saa", "group": group, "human": human, "margin": -0.9,
            "heard_agrees": False, "baseline_flag": False, "utt": utt, "word_index": wi, "phoneme_index": pi,
            "pair": "th_as_s", "target": "θ", "op": "match", "f3_dip": None, "fric": None, "closure": None,
            "x_hiss": x}


def split(source, speaker, korean):
    return "test" if korean else ("train" if speaker.startswith("tr") else "dev")


def listener_rows(signal, seed):
    """40 dev speakers + 10 TRAINING speakers (must be ignored) + 4 Korean test speakers; x_hiss carries the signal."""
    rng = np.random.default_rng(seed)
    out = []
    for prefix, n in (("d", 40), ("tr", 10)):
        for s in range(n):
            out += [row(f"{prefix}{s}", "correct", float(rng.normal()), wi=i) for i in range(50)]
            out.append(row(f"{prefix}{s}", "error", float(rng.normal() + signal), wi=50))
    for s in range(4):
        out += [row(f"k{s}", "correct", float(rng.normal()), group="korean", wi=i) for i in range(50)]
        out += [row(f"k{s}", "error", float(rng.normal() + signal), group="korean", wi=50 + i) for i in range(3)]
    return out


def test_dev_only_drops_training_speakers():
    rows = listener_rows(3.0, 0)
    kept = C.dev_only(rows, split=split)
    assert not any(r["speaker"].startswith("saa:tr") for r in kept)
    assert sum(r["group"] == "korean" for r in kept) == sum(r["group"] == "korean" for r in rows)


def test_check_tuning_refuses_a_training_speaker():
    with pytest.raises(ValueError, match="training"):
        C.check_tuning(listener_rows(3.0, 0), split=split)


def test_common_rows_keeps_only_sounds_both_listeners_scored():
    old, new = listener_rows(0.0, 1), listener_rows(3.0, 2)
    new = [r for r in new if not (r["speaker"] == "saa:k0" and r["word_index"] == 0)]   # new lost one sound
    o, n, dropped = C.common_rows(old, new)
    assert dropped == {"old": 1, "new": 0}
    assert len(o) == len(n) == len(new)


def test_compare_old_vs_new():
    """Old listener: no signal -> fails the 0.70 feasibility bar. New listener: strong signal -> passes the bar."""
    out = C.compare(listener_rows(0.0, 1), listener_rows(4.0, 2), pairs=("th_as_s",), split=split)
    p = out["pairs"]["th_as_s"]
    assert p["old"]["detector"]["feasible"] is False
    assert p["new"]["detector"]["enabled"] is True
    assert "model" not in p["new"]["detector"]                     # the report keeps numbers, not weights
    assert p["new"]["detector"]["tuning rows"] == {"correct": 2000, "error": 40}   # dev speakers only
    assert out["passing"] == {"old": [], "new": ["th_as_s"]}
    assert out["rows"]["korean test"]["old"] == out["rows"]["korean test"]["new"]


# ---------- 5. the one-command overnight run ----------
def test_training_done(tmp_path):
    log = tmp_path / "train.log"
    log.write_text("20:02:41 dev PER after epoch 3: 0.1542 (800 recordings)\n")
    assert not C.training_done(log)
    log.write_text(log.read_text() + "23:50:00 done: 12239 steps; dev PER ['0.2948']\n")
    assert C.training_done(log)
    assert not C.training_done(tmp_path / "missing.log")


def test_build_commands_use_the_new_listener_and_heldout_speakers():
    cmds, env = C.build_commands(NEW)
    mods = [" ".join(c[2:]) for c in cmds]
    assert mods == ["eval.l2arctic", "eval.extra_corpora suitcase", "eval.extra_corpora speechocean",
                    "eval.saa --set all --run", "eval.saa --set all --features"]
    assert env[align.LISTENER_ENV] == NEW and env[L.SPEAKERS_ENV] == "heldout"
