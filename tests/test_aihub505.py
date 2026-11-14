"""AI Hub 505 (English-L1 learners reading Korean) -> (a) how often each candidate Korean check fires on
real learners, (b) does our sentence score follow the human 상/중/하 rating. Small made-up data, no model, except
the two LIVE tests at the bottom (they check that our measurement = the one that set the native cut-offs)."""
import csv
import io
import json
import zipfile
from pathlib import Path

import pytest

from eval import aihub505 as A


# ---------- 1. which recordings we keep ----------
def tr(reading="잠시만, 내 지갑이 어디 갔지?", label="잠시만 내 지갑이 어디 갔지", rating="중"):
    return {"Reading": reading, "ReadingLabelText": label, "Question": "", "AnswerLabelText": "",
            "SentenceSpeechLV": rating}


def test_norm_drops_punctuation_and_extra_spaces():
    assert A.norm("잠시만,  내 지갑이 어디 갔지?") == "잠시만 내 지갑이 어디 갔지"
    assert A.norm(" 형석아. 어떡하지! ") == "형석아 어떡하지"


def test_keeps_a_reading_whose_transcript_matches_the_script():
    assert A.usable(tr()) is None


def test_drops_answers_slips_false_starts_fillers_and_unknown_ratings():
    assert A.usable(tr(reading="", label="")) == "not a reading"                      # question-answer item
    assert A.usable(tr(label="잠시만 나 지갑이 어디 갔지")) == "said other words"      # word slip
    assert A.usable(tr(label="잠시만 내 지+ 지갑이 어디 갔지")) == "false start or filler"
    assert A.usable(tr(label="잠시만 / 내 지갑이 어디 갔지")) == "false start or filler"
    assert A.usable(tr(rating="")) == "no rating"


def test_speaker_split_is_stable_and_about_half_half():
    ids = [f"EN{i:04d}" for i in range(1, 158)]
    first = [A.split_of(s) for s in ids]
    assert first == [A.split_of(s) for s in ids]                 # same answer every run
    assert set(first) == {"dev", "test"}
    assert 0.35 < first.count("dev") / len(ids) < 0.65


class CP949Info(zipfile.ZipInfo):
    """Writes the member name in CP949 with no UTF-8 flag, like AI Hub's zips (Python would write UTF-8)."""
    def _encodeFilenameFlags(self):
        return self.filename.encode("cp949"), self.flag_bits


def fake_zips(tmp_path):
    """A labels zip + audio zip shaped like AI Hub's (CP949 names, one folder per topic)."""
    labels, audio = tmp_path / "labels_val.zip", tmp_path / "audio_val.zip"
    items = {"EN11RC001_EN0006_20210727": tr(rating="상"),
             "EN11RC001_EN0007_20210727": tr(label="잠시만 나 지갑이 어디 갔지"),
             "EN10QC227_EN0089_20211019": tr(reading="", label="")}
    with zipfile.ZipFile(labels, "w") as zl, zipfile.ZipFile(audio, "w") as za:
        for stem, t in items.items():
            j = {"fileName": stem + ".wav", "file_info": {"speakerID": stem.split("_")[1], "recordTime": "8.4"},
                 "transcription": t}
            name = f"1. 한국일반/{stem}"
            zl.writestr(CP949Info(name + ".json"), json.dumps(j))
            za.writestr(CP949Info(name + ".wav"), b"RIFF")
    return labels, audio


def test_items_come_from_the_label_zip_and_point_at_their_audio(tmp_path):
    labels, audio = fake_zips(tmp_path)
    items, dropped = A.load_items([(labels, audio)])
    assert [i["file"] for i in items] == ["EN11RC001_EN0006_20210727.wav"]
    it = items[0]
    assert it["speaker"] == "EN0006" and it["rating"] == 3 and it["text"] == "잠시만 내 지갑이 어디 갔지"
    assert it["member"] == "1. 한국일반/EN11RC001_EN0006_20210727.wav" and it["audio_zip"] == str(audio)
    assert it["split"] == A.split_of("EN0006")
    assert dropped == {"said other words": 1, "not a reading": 1}
    with zipfile.ZipFile(audio, metadata_encoding="cp949") as z:   # the member name really opens
        assert z.read(it["member"]) == b"RIFF"


# ---------- 2. cut-offs from NATIVE speakers ----------
def test_native_cut_lets_at_most_half_a_percent_of_native_sounds_fire():
    c = A.native_cut(list(range(1, 1001)))
    assert c == {"cut": 995, "fired": 5, "n": 1000, "rate": 0.005}
    assert A.native_cut(list(range(1, 101)))["fired"] == 0           # 0.5% of 100 < 1: nothing may fire
    assert A.native_cut([1, 2, 5, 5, 5])["fired"] == 0                 # ties at the top never sneak over


def test_fires_follows_each_checks_direction():
    assert A.fires({"margin_r": 0.9}, "tap_as_r_margin", {"tap_as_r_margin": 0.5})
    assert not A.fires({"margin_r": 0.5}, "tap_as_r_margin", {"tap_as_r_margin": 0.5})   # must be OVER the cut
    assert A.fires({"f3_dip": -400}, "tap_as_r_f3", {"tap_as_r_f3": 300})                 # lower F3 = R-like
    assert not A.fires({"f3_dip": ""}, "tap_as_r_f3", {"tap_as_r_f3": 300})               # not measured
    assert A.fires({"vot": 40.0}, "tense_puff_vot", {"tense_puff_vot": 30.0})


def test_native_values_read_the_step_18_caches(tmp_path):
    taps, vot = tmp_path / "taps.csv", tmp_path / "vot.csv"
    taps.write_text("lang,kind,margin_r,margin_l,f3_dip\nko,ko_tap,0.1,0.2,-50\nen,en_r,0.9,0,-900\n"
                    "ko,ko_tap,0.3,0.0,\n")
    vot.write_text("lang,cat,vot\nko,tense,12.0\nko,tense,\nko,asp,80\nen,asp,70\n")
    v = A.native_values(taps, vot)
    assert v["tap_as_r_margin"] == [0.1, 0.3] and v["tap_as_l_margin"] == [0.2, 0.0]
    assert v["tap_as_r_f3"] == [50.0]                                  # sign flipped; empty skipped
    assert v["tense_puff_vot"] == [12.0]                               # tense only, Korean only


# ---------- 3. statistics ----------
def test_wilson_interval():
    lo, hi = A.wilson(0, 100)
    assert lo == 0.0 and 0.03 < hi < 0.04
    lo, hi = A.wilson(50, 100)
    assert lo < 0.5 < hi
    assert A.wilson(0, 0) == (None, None)


def test_spearman():
    assert A.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert A.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert A.spearman([1, 1, 2, 2], [1, 2, 3, 4]) == pytest.approx(0.8944, abs=1e-4)   # ties: average ranks
    assert A.spearman([1, 1, 1], [1, 2, 3]) is None                                    # no spread


def test_speaker_bootstrap_is_repeatable_and_resamples_speakers():
    rows = [dict(speaker=f"s{i % 6}", rating=1 + i % 3, heard=(1 + i % 3) / 3 + (i % 5) / 50) for i in range(60)]
    stat = lambda rs: A.spearman([r["heard"] for r in rs], [r["rating"] for r in rs])
    a = A.speaker_bootstrap(rows, stat, n_boot=200, seed=1)
    assert a == A.speaker_bootstrap(rows, stat, n_boot=200, seed=1)
    assert a[0] <= stat(rows) <= a[1]
    one = [dict(r, speaker="only") for r in rows]                       # one speaker: every resample is the same
    lo, hi = A.speaker_bootstrap(one, stat, n_boot=50, seed=1)
    assert lo == pytest.approx(hi)


def test_fire_summary_counts_per_split_and_rating():
    cuts = {"tap_as_r_margin": 0.5}
    rows = [dict(check="tap_as_r_margin", split="dev", rating=3, margin_r=0.9),
            dict(check="tap_as_r_margin", split="dev", rating=1, margin_r=0.1),
            dict(check="tap_as_r_margin", split="dev", rating=1, margin_r=0.8),
            dict(check="tap_as_r_margin", split="test", rating=2, margin_r=0.0)]
    s = A.fire_summary(rows, cuts)["tap_as_r_margin"]
    assert s["dev"]["all"]["n"] == 3 and s["dev"]["all"]["fired"] == 2
    assert s["dev"]["하"]["fired"] == 1 and s["dev"]["하"]["n"] == 2
    assert s["dev"]["상"]["rate"] == 1.0
    assert s["test"]["all"] == dict(n=1, fired=0, rate=0.0, ci=list(A.wilson(0, 1)))


def test_score_summary_has_sentence_and_speaker_level_correlations():
    rows = [dict(speaker=f"s{i % 4}", split="dev", rating=1 + (i % 4) % 3, heard=(i % 4) / 4, conf=0.5,
                 missing=0.1) for i in range(40)]
    s = A.score_summary(rows, n_boot=50)["dev"]
    assert s["n_sentences"] == 40 and s["n_speakers"] == 4
    assert set(s["by_rating"]) == {"상", "중", "하"}
    assert s["heard"]["spearman"] is not None and len(s["heard"]["ci_by_speaker"]) == 2
    assert s["conf"]["spearman"] is None                               # a constant score has no correlation
    assert "speaker_level_spearman" in s["heard"]


def test_script_id_is_the_first_part_of_the_file_name():
    assert A.script_of("EN12RC045_EN0001_20210803.wav") == "EN12RC045"


def test_partial_spearman_removes_a_shared_third_variable():
    """y and x both follow z, and only through z: once z is removed nothing is left."""
    z = list(range(60))
    x = [v + (7 if i % 2 else -7) for i, v in enumerate(z)]
    y = [v + (7 if i % 3 == 0 else -3) for i, v in enumerate(z)]
    assert A.spearman(x, y) > 0.9
    assert abs(A.partial_spearman(x, y, z)) < A.spearman(x, y) / 3
    assert A.partial_spearman(x, [1] * 60, z) is None                    # no spread -> no correlation


def test_within_script_spearman_compares_readers_of_the_same_script():
    """Script B is read better AND scores higher, but within each script a higher rating means a LOWER score."""
    rows = []
    for script, base in (("A", 0.2), ("B", 0.8)):
        for i in range(10):
            rating = 1 + i % 3
            rows.append(dict(file=f"{script}_s{i}_x.wav", rating=rating + (1 if script == "B" else 0),
                             heard=base - 0.05 * rating))
    pooled = A.spearman([r["heard"] for r in rows], [r["rating"] for r in rows])
    assert pooled > 0                                                    # pooled: the script difference wins
    assert A.within_script_spearman(rows, "heard") < -0.9                # same script: backwards


def test_speed_summary_reports_rate_length_and_scores_with_speed_removed():
    rows = []
    for i in range(60):
        rating = 1 + i % 3
        seconds = 20 - 4 * rating + (i % 5) * 0.3                         # better speakers read faster
        n = 100
        speed = n / seconds
        rows.append(dict(file=f"S{i % 6}_spk{i % 12}_x.wav", speaker=f"spk{i % 12}", split="dev" if i % 12 < 6 else "test",
                         rating=rating, n=n, seconds=seconds,
                         heard=round(1 - speed / 20 + (i % 7) * 0.002, 4),
                         conf=round(0.9 - speed / 25 + (i % 4) * 0.002, 4), missing=0.1))
    s = A.speed_summary(rows, n_boot=50)
    assert set(s) == {"dev", "test", "both"}
    b = s["both"]
    assert set(b["by_rating"]) == {"상", "중", "하"}
    assert b["by_rating"]["상"]["speed"] > b["by_rating"]["하"]["speed"]
    assert b["by_rating"]["상"]["sounds"] == 100
    assert b["speed_vs_rating"]["spearman"] > 0.8 and len(b["speed_vs_rating"]["ci_by_speaker"]) == 2
    for k in ("heard", "conf"):
        assert b[k]["vs_speed"] < -0.9
        assert b[k]["vs_rating"] < -0.5
        assert abs(b[k]["vs_rating_speed_removed"]["spearman"]) < abs(b[k]["vs_rating"])
        assert len(b[k]["vs_rating_speed_removed"]["ci_by_speaker"]) == 2
        assert "vs_rating_same_script" in b[k]
    assert "missing" not in b                                            # only the two scores the README discusses


def test_report_saves_the_speed_check(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "native_values", lambda: {"tap_as_r_margin": [0.1] * 400})
    sent = tmp_path / "s.csv"
    fields = ["file", "speaker", "split", "rating", "seconds", "n", "heard", "missing", "conf", "error"]
    with open(sent, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        for i in range(30):
            w.writerow(dict(file=f"S{i % 3}_spk{i % 6}_x.wav", speaker=f"spk{i % 6}", split="dev", rating=1 + i % 3,
                            seconds=10 + i % 4, n=80, heard=0.5 + (i % 7) / 50, missing=0.1, conf=0.4 + (i % 5) / 40,
                            error=""))
    res = A.report(sent, tmp_path / "none.csv", tmp_path / "out.json", {}, n_boot=20)
    saved = json.loads((tmp_path / "out.json").read_text())
    assert "speed" in saved and saved["speed"] == res["speed"]
    assert saved["speed"]["dev"]["heard"]["vs_speed"] is not None


# ---------- 4. safety ----------
def test_refuses_the_fine_tuned_listener(monkeypatch):
    """The native cut-offs were measured with the original listener; Korean must use the same one."""
    monkeypatch.setenv("PC_LISTENER", "data/models/listener_v1/best")
    with pytest.raises(SystemExit, match="original listener"):
        A.check_listener()
    monkeypatch.delenv("PC_LISTENER")
    A.check_listener()


def test_resume_reads_the_files_already_done(tmp_path):
    p = tmp_path / "s.csv"
    assert A.done_files(p) == set()
    p.write_text("file,speaker\na.wav,EN1\nb.wav,EN2\n")
    assert A.done_files(p) == {"a.wav", "b.wav"}


def test_per_speaker_limit_keeps_the_first_n_of_each_speaker():
    items = [dict(file=f"{s}{i}.wav", speaker=s) for s in "ab" for i in range(5)]
    kept = A.per_speaker(items, 2)
    assert [i["file"] for i in kept] == ["a0.wav", "a1.wav", "b0.wav", "b1.wav"]
    assert A.per_speaker(items, None) == items


# ---------- 5. LIVE: same measurement as the native cut-offs (loads the model) ----------
ZEROTH = Path("data/zeroth/data/test-00000-of-00001.parquet")
needs_data = pytest.mark.skipif(not (ZEROTH.exists() and A.NATIVE_TAPS.exists() and A.NATIVE_VOT.exists()),
                                reason="Zeroth + carry-over caches not on this machine")


def _zeroth_with(pred):
    import pyarrow.parquet as pq
    for r in pq.read_table(ZEROTH).to_pylist():
        if pred(r):
            return r


@needs_data
def test_live_tense_vot_matches_the_native_cache():
    import soundfile as sf
    cache = [r for r in csv.DictReader(open(A.NATIVE_VOT)) if r["lang"] == "ko" and r["cat"] == "tense"
             and r["vot"] != ""]
    want = {}
    for r in cache:
        want.setdefault(r["utt"], []).append(float(r["vot"]))
    rec = _zeroth_with(lambda r: r["id"] in want)
    audio, sr = sf.read(io.BytesIO(rec["audio"]["bytes"]), dtype="float32")
    _, sounds = A.measure_recording(audio, sr, " ".join(rec["text"].split()))
    got = [s["vot"] for s in sounds if s["check"] == "tense_puff_vot" and s["vot"] != ""]
    assert got == pytest.approx(want[rec["id"]], abs=2.0)              # ms


@needs_data
def test_live_tap_margins_match_the_native_cache():
    import soundfile as sf
    cache = [r for r in csv.DictReader(open(A.NATIVE_TAPS)) if r["kind"] == "ko_tap"]
    want = {}
    for r in cache:
        want.setdefault(r["utt"], []).append(float(r["margin_r"]))
    rec = _zeroth_with(lambda r: r["id"] in want)
    audio, sr = sf.read(io.BytesIO(rec["audio"]["bytes"]), dtype="float32")
    feats, sounds = A.measure_recording(audio, sr, " ".join(rec["text"].split()))
    got = [s["margin_r"] for s in sounds if s["check"] == "tap_as_r_margin"]
    assert got == pytest.approx(want[rec["id"]], abs=0.01)
    assert 0 < feats["heard"] <= 1 and feats["n"] > 0
