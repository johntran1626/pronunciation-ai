"""The live app's listener per language: English uses the fine-tuned listener, Korean the original model.
Each listener has its own threshold files, and the app always reads the files that belong to the listener it ran.
No real model is loaded."""
import json

import pytest
import torch

import backend.align as align
import backend.listener as L

TAG_DIR = "listener_v1"


@pytest.fixture
def fake_fine_tuned(tmp_path, monkeypatch):
    """A fine-tuned listener folder + a backend folder for threshold files, both in tmp_path."""
    monkeypatch.delenv(L.LISTENER_ENV, raising=False)
    folder = tmp_path / "models" / TAG_DIR / "best"
    folder.mkdir(parents=True)
    (folder / "config.json").write_text("{}")
    backend = tmp_path / "backend"
    backend.mkdir()
    monkeypatch.setattr(L, "FINE_TUNED", folder)
    monkeypatch.setattr(L, "BACKEND", backend)
    return folder, backend


def _write_thresholds(backend, kinds=("sound", "match")):
    names = {"sound": "thresholds_listener_v1.json", "match": "match_thresholds_listener_v1.json"}
    for k in kinds:
        (backend / names[k]).write_text(json.dumps({"pairs": {}, "kind": k}))


# ---------- 1. which listener the live app uses ----------
def test_threshold_files_are_named_after_the_listener(fake_fine_tuned):
    folder, backend = fake_fine_tuned
    assert L.thresholds_file("sound", L.MODEL) == backend / "thresholds.json"
    assert L.thresholds_file("match", L.MODEL) == backend / "match_thresholds.json"
    assert L.thresholds_file("sound", None) == backend / "thresholds.json"      # None = the original model
    assert L.thresholds_file("sound", str(folder)) == backend / "thresholds_listener_v1.json"
    assert L.thresholds_file("match", str(folder)) == backend / "match_thresholds_listener_v1.json"


def test_english_uses_the_fine_tuned_listener_when_it_is_ready(fake_fine_tuned):
    folder, backend = fake_fine_tuned
    _write_thresholds(backend)
    assert L.live_listener("en") == str(folder)
    assert L.live_listener("ko") == L.MODEL                 # Korean always stays on the original model


def test_missing_threshold_file_falls_back_to_the_original_model(fake_fine_tuned):
    folder, backend = fake_fine_tuned
    _write_thresholds(backend, kinds=("sound",))            # the sentence-check thresholds aren't tuned yet
    assert L.live_listener("en") == L.MODEL                 # never a listener with another listener's thresholds


def test_missing_weights_fall_back_to_the_original_model(fake_fine_tuned):
    folder, backend = fake_fine_tuned
    _write_thresholds(backend)
    (folder / "config.json").unlink()                       # e.g. a fresh clone: the weights are not in git
    assert L.live_listener("en") == L.MODEL


def test_env_var_overrides_the_live_choice(fake_fine_tuned, monkeypatch):
    monkeypatch.setenv(L.LISTENER_ENV, "/x/other/best")
    assert L.live_listener("en") == "/x/other/best"
    assert L.live_listener("ko") == "/x/other/best"


def test_listener_id_is_short_and_has_no_machine_path(fake_fine_tuned):
    folder, _ = fake_fine_tuned
    assert L.listener_id(str(folder)) == TAG_DIR
    assert L.listener_id(L.MODEL) == L.MODEL


# ---------- 2. the model runs with the listener it was asked for, and says which one ----------
@pytest.fixture
def fake_models(monkeypatch):
    loaded = []

    class Out:
        def __init__(self, n):
            self.logits = torch.zeros(1, n, 3)

    class FakeModel:
        config = type("C", (), {"vocab_size": 3, "pad_token_id": 0})()

        def __call__(self, x):
            return Out(10)

    def extractor(wav, sampling_rate, return_tensors):
        return type("I", (), {"input_values": torch.zeros(1, len(wav))})()

    def fake_load(name):
        loaded.append(name)
        return extractor, FakeModel()

    monkeypatch.setattr(align, "_load", fake_load)
    return loaded


def test_emissions_for_a_language_use_the_live_listener(fake_models, monkeypatch):
    monkeypatch.setattr(align, "live_listener", lambda lang: {"en": "/m/listener_v1/best", "ko": L.MODEL}[lang])
    em = align.emissions(torch.zeros(16000).numpy(), 16000, lang="en")
    assert em.model == "/m/listener_v1/best" and fake_models[-1] == "/m/listener_v1/best"
    em = align.emissions(torch.zeros(16000).numpy(), 16000, lang="ko")
    assert em.model == L.MODEL and fake_models[-1] == L.MODEL


def test_emissions_without_a_language_keep_the_eval_listener(fake_models, monkeypatch):
    """Eval scripts call emissions(audio, sr): the original model, or PC_LISTENER, exactly as before."""
    monkeypatch.delenv(L.LISTENER_ENV, raising=False)
    assert align.emissions(torch.zeros(16000).numpy(), 16000).model == L.MODEL
    monkeypatch.setenv(L.LISTENER_ENV, "/x/listener_v1/best")
    assert align.emissions(torch.zeros(16000).numpy(), 16000).model == "/x/listener_v1/best"


# ---------- 3. thresholds follow the listener ----------
def test_scoring_and_match_thresholds_load_the_listeners_files(fake_fine_tuned, monkeypatch):
    folder, backend = fake_fine_tuned
    _write_thresholds(backend)
    (backend / "thresholds.json").write_text(json.dumps({"pairs": {}, "kind": "old sound"}))
    (backend / "match_thresholds.json").write_text(json.dumps({"kind": "old match"}))
    from backend.match import load_match_thresholds
    from backend.scoring import load_thresholds
    assert load_thresholds(str(folder))["kind"] == "sound"
    assert load_match_thresholds(str(folder))["kind"] == "match"
    assert load_thresholds(L.MODEL)["kind"] == "old sound"
    assert load_match_thresholds()["kind"] == "old match"


def test_pipeline_reads_the_thresholds_of_the_listener_it_ran(monkeypatch):
    import backend.app as app
    asked = []
    em = align.Emissions(torch.zeros(5, 3), 0.02, 0.1, model="/m/listener_v1/best")
    monkeypatch.setattr(app, "expected_phonemes", lambda text, lang: [])
    monkeypatch.setattr(app, "emissions", lambda s, sr, lang: em)
    monkeypatch.setattr(app, "align", lambda e, x, lang: [])
    monkeypatch.setattr(app, "recognize", lambda e: [])
    monkeypatch.setattr(app, "attach_heard", lambda w, h, lang: (w, []))
    monkeypatch.setattr(app, "load_thresholds", lambda name: asked.append(("sound", name)) or {"pairs": {}})
    monkeypatch.setattr(app, "load_match_thresholds", lambda name: asked.append(("match", name)) or {})
    monkeypatch.setattr(app, "sentence_check", lambda w, n, rules, ev=None: (False, "no_speech"))
    monkeypatch.setattr(app, "mark_unchecked", lambda w: w)
    monkeypatch.setattr(app, "attach_display", lambda w, lang: w)
    monkeypatch.setattr(app, "active_checks", lambda lang, s, m: [])
    app._run_pipeline(None, 16000, "right", "en")
    assert asked == [("sound", "/m/listener_v1/best"), ("match", "/m/listener_v1/best")]


def test_native_timings_are_redone_when_the_listener_changes(tmp_path, monkeypatch):
    import backend.native as native
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"")
    calls = []
    monkeypatch.setattr(native, "align_clip", lambda p, t, lang: calls.append(lang) or ([{
        "word": "hi", "start": 0.0, "end": 0.2, "phonemes": []}], 0.3))
    monkeypatch.setattr(native, "live_listener", lambda lang: L.MODEL)
    native.native_timings(wav, "hi", "en")
    native.native_timings(wav, "hi", "en")
    assert len(calls) == 1                                   # same listener: saved timings reused
    monkeypatch.setattr(native, "live_listener", lambda lang: "/m/listener_v1/best")
    out = native.native_timings(wav, "hi", "en")
    assert len(calls) == 2 and out["model"] == "listener_v1"  # new listener: aligned again; no machine path saved


# ---------- 4. the fine-tuned listener's pair thresholds, from the old-vs-new report ----------
def _report():
    def rule(enabled, margin):
        return {"cap": 0.005, "variant": "B", "margin": margin, "enabled": enabled,
                "test (korean)": {"caught": {"k": 1, "n": 2}}}
    return {"pairs": {
        "r_as_l": {"new": {"margin rule": rule(True, 0.5), "passes bar": True}},
        "v_as_b": {"new": {"margin rule": rule(False, 0.9), "detector": {"enabled": True}, "passes bar": True}},
        "f_as_p": {"new": {"margin rule": rule(False, 0.7), "passes bar": False}},
    }}


def test_live_thresholds_take_the_new_listeners_margin_rules():
    from eval.compare_listeners import live_thresholds
    out = live_thresholds(_report())
    assert out["pairs"]["r_as_l"] == {"cap": 0.005, "variant": "B", "margin": 0.5, "enabled": True}
    assert out["pairs"]["f_as_p"]["enabled"] is False
    # passes only by the detector: its weights aren't in the report, so it stays off rather than guessing
    assert out["pairs"]["v_as_b"]["enabled"] is False
    assert "dev speakers" in out["source"]


# ---------- 5. re-tuning "did you say this sentence?" for the fine-tuned listener ----------
def test_match_eval_keeps_only_held_out_english_for_the_fine_tuned_listener(monkeypatch):
    from eval import match_eval
    monkeypatch.delenv(L.LISTENER_ENV, raising=False)
    assert match_eval.keep("ko", "test", "spk1") and match_eval.keep("en", "others", "ABA")   # old: everything
    monkeypatch.setenv(L.LISTENER_ENV, "/x/listener_v1/best")
    assert not match_eval.keep("ko", "test", "spk1")         # Korean stays on the original model
    assert match_eval.keep("en", "others", "SKA")            # a dev speaker
    assert not match_eval.keep("en", "others", "ABA")        # a training speaker of the fine-tune
    assert match_eval.keep("en", "korean", "HKK")            # Korean L1 test speakers: never trained on


def test_match_files_get_their_own_names_for_the_fine_tuned_listener(monkeypatch):
    from eval import match_tune
    monkeypatch.delenv(L.LISTENER_ENV, raising=False)
    p = match_tune.paths()
    assert str(p["sentences"]) == "data/cache/match_sentences.csv"
    assert str(p["thresholds"]).endswith("backend/match_thresholds.json")
    monkeypatch.setenv(L.LISTENER_ENV, "/x/listener_v1/best")
    p = match_tune.paths()
    assert str(p["sentences"]) == "data/cache/listener_v1/match_sentences.csv"
    assert str(p["results"]) == "results/match_listener_v1.json"
    assert str(p["thresholds"]).endswith("backend/match_thresholds_listener_v1.json")


def test_fine_tuned_listener_goes_live_only_if_its_sentence_check_holds(monkeypatch):
    from eval import match_tune
    monkeypatch.delenv(L.LISTENER_ENV, raising=False)
    assert match_tune.may_go_live({"en": {"sentence": {"enabled": False}}})        # original: always written
    monkeypatch.setenv(L.LISTENER_ENV, "/x/listener_v1/best")
    assert match_tune.may_go_live({"en": {"sentence": {"enabled": True}}})
    assert not match_tune.may_go_live({"en": {"sentence": {"enabled": False}}})   # cap broken: stay on the original
