"""AI Hub 505: English-L1 learners reading Korean.
    python -m eval.aihub505 --limit 5               # smoke: 5 recordings -> data/cache/aihub505_smoke_* (not results/)
    python -m eval.aihub505 --per-speaker 40        # the real run (resumes where it stopped) -> results/aihub505.json
    python -m eval.aihub505 --report                # rebuild the report from the cached rows, no model

AI Hub 505 has NO per-sound error labels: only what words were said and one 상/중/하 rating per sentence.
So it can't give detection rates. It answers two other questions:

  (a) FIRE RATE. eval/korean_carryover.py found 4 Korean checks that tell English-like sounds from native Korean (simulated errors):
      ㄹ said as English R (model margin, F3 dip), ㄹ said as English L (model margin), ㅃㄸㄲ said with an English
      puff (VOT). None is live. Here each gets a CANDIDATE cut-off set on NATIVE Korean speakers (Zeroth, the
      carry-over caches): at most 0.5% of native sounds may fire (the false-alarm cap). Then: how often does it fire on real
      learners? That share = real errors + false alarms, and nobody has checked which is which, so it is only an
      UPPER BOUND on false alarms. A check that fires more on 하 sentences than on 상 ones is at least pointing the
      right way.
  (b) SCORE vs RATING. Do our sentence numbers (share of expected sounds the listener heard, mean alignment
      confidence) go up with the human rating? Spearman rank correlation, with a 95% interval from resampling
      SPEAKERS (sentences of one speaker are not independent).

Only recordings where the learner read the script word for word are kept (no slips, false starts or fillers), so
the score measures HOW the words were said, not WHICH words. Speakers are split in two halves (dev / test) by a
fixed hash: AI Hub's own train/val share 142 speakers. Nothing is tuned on AI Hub here; the split keeps a clean
half for later and shows whether the numbers hold on both halves.

Privacy / terms: the per-recording rows stay in data/cache/ (git-ignored). results/aihub505.json holds counts only.
"""
import argparse
import copy
import csv
import hashlib
import io
import json
import math
import re
import sys
import time
import unicodedata
import zipfile
from collections import Counter, defaultdict
from functools import cache
from pathlib import Path

import numpy as np

DATA = Path("data/aihub505")
PAIRS = [(DATA / "labels_train.zip", DATA / "audio_train.zip"), (DATA / "labels_val.zip", DATA / "audio_val.zip")]
NATIVE_TAPS = Path("data/cache/korean_carryover.csv")   # native Korean ㄹ between vowels (Zeroth test)
NATIVE_VOT = Path("data/cache/spike_b_vot.csv")         # spikes/b_vot.py: native Korean word-initial stops (Zeroth)
SENTENCES = Path("data/cache/aihub505_sentences.csv")
SOUNDS = Path("data/cache/aihub505_sounds.csv")
RESULTS = Path("results/aihub505.json")
SMOKE = {"sentences": Path("data/cache/aihub505_smoke_sentences.csv"),
         "sounds": Path("data/cache/aihub505_smoke_sounds.csv"), "results": Path("data/cache/aihub505_smoke.json")}
CAP = 0.005                                    # false-alarm cap: at most 0.5% of correct (here: native) sounds may fire
RATING = {"상": 3, "중": 2, "하": 1}
RATING_NAME = {v: k for k, v in RATING.items()}
SCORES = ("heard", "conf", "missing")          # backend/match.py sentence_features
# check -> (column, direction, plain name). direction -1 = a LOWER value is more English-like (F3 dips for R).
CHECKS = {"tap_as_r_margin": ("margin_r", 1, "ㄹ said as English R (model margin)"),
          "tap_as_r_f3": ("f3_dip", -1, "ㄹ said as English R (F3 dip)"),
          "tap_as_l_margin": ("margin_l", 1, "ㄹ said as English L (model margin)"),
          "tense_puff_vot": ("vot", 1, "ㅃㄸㄲ said with an English puff (VOT)")}
TAP_CHECKS = ("tap_as_r_margin", "tap_as_r_f3", "tap_as_l_margin")
SENTENCE_FIELDS = ["file", "speaker", "split", "rating", "seconds", "n", "heard", "missing", "conf", "error"]
SOUND_FIELDS = ["file", "speaker", "split", "rating", "check", "word", "start", "margin_r", "margin_l", "f3_dip",
                "vot"]


# ---------- 1. which recordings we keep ----------
def norm(text):
    """Script and transcript in one form: NFC, punctuation gone, single spaces."""
    text = unicodedata.normalize("NFC", text)
    return " ".join(re.sub(r"[^\w\s+/]", " ", text).split())


def usable(t):
    """None = keep; else the reason we drop it. t = the label's 'transcription' block."""
    if not t.get("Reading"):
        return "not a reading"                      # question-answer items: no script to compare with
    label = t.get("ReadingLabelText", "")
    if "+" in label or "/" in label:
        return "false start or filler"              # AI Hub marks: + = false start, / = filler
    if norm(t["Reading"]) != norm(label):
        return "said other words"
    if t.get("SentenceSpeechLV") not in RATING:
        return "no rating"
    return None


def split_of(speaker):
    """Fixed half by speaker: same answer every run, on every machine."""
    return "dev" if hashlib.sha256(speaker.encode()).digest()[0] % 2 == 0 else "test"


def load_items(pairs=PAIRS):
    """[(labels zip, audio zip)] -> (kept recordings, Counter of dropped reasons)."""
    items, dropped = [], Counter()
    for labels, audio in pairs:
        with zipfile.ZipFile(audio, metadata_encoding="cp949") as za:
            wavs = set(za.namelist())
        with zipfile.ZipFile(labels, metadata_encoding="cp949") as zl:
            for m in zl.namelist():
                if not m.endswith(".json"):
                    continue
                j = json.loads(zl.read(m))
                reason = usable(j["transcription"])
                wav = m[:-len(".json")] + ".wav"
                if reason is None and wav not in wavs:
                    reason = "audio missing"
                if reason:
                    dropped[reason] += 1
                    continue
                speaker = j["file_info"]["speakerID"]
                items.append(dict(file=j["fileName"], member=wav, audio_zip=str(audio), speaker=speaker,
                                  split=split_of(speaker), rating=RATING[j["transcription"]["SentenceSpeechLV"]],
                                  text=norm(j["transcription"]["Reading"]),
                                  seconds=float(j["file_info"].get("recordTime") or 0)))
    return items, dict(dropped)


def per_speaker(items, n):
    """The first n recordings of each speaker (in the given order); None = all."""
    if n is None:
        return items
    seen, out = Counter(), []
    for it in items:
        seen[it["speaker"]] += 1
        if seen[it["speaker"]] <= n:
            out.append(it)
    return out


# ---------- 2. cut-offs from NATIVE speakers ----------
def _f(v):
    return None if v in ("", None) else float(v)


def native_values(taps_csv=NATIVE_TAPS, vot_csv=NATIVE_VOT):
    """Each check's scores on native Korean sounds, signed so that HIGHER = more English-like."""
    out = {c: [] for c in CHECKS}
    for r in csv.DictReader(open(taps_csv, encoding="utf-8")):
        if r["lang"] == "ko" and r["kind"] == "ko_tap":
            for c in TAP_CHECKS:
                col, sign, _ = CHECKS[c]
                if _f(r[col]) is not None:
                    out[c].append(sign * _f(r[col]))
    for r in csv.DictReader(open(vot_csv, encoding="utf-8")):
        if r["lang"] == "ko" and r["cat"] == "tense" and _f(r["vot"]) is not None:
            out["tense_puff_vot"].append(_f(r["vot"]))
    return out


def native_cut(values, cap=CAP):
    """The cut-off: a sound fires when its score is OVER it. At most floor(cap * n) native sounds may be over it,
    so with fewer than 1/cap native sounds nothing may fire at all."""
    s = sorted(values, reverse=True)
    k = math.floor(cap * len(s) + 1e-9)
    cut = s[min(k, len(s) - 1)]
    fired = sum(v > cut for v in s)
    return dict(cut=cut, fired=fired, n=len(s), rate=round(fired / len(s), 4))


def fires(row, check, cuts):
    col, sign, _ = CHECKS[check]
    v = _f(row.get(col))
    return v is not None and sign * v > cuts[check]


# ---------- 3. statistics ----------
def wilson(k, n, z=1.96):
    """95% interval for a share k/n (Wilson: sensible even at 0 or n)."""
    if n == 0:
        return (None, None)
    p = k / n
    mid, half = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    d = 1 + z * z / n
    return (round(max(0.0, (mid - half) / d), 4), round(min(1.0, (mid + half) / d), 4))


def _rank(a):
    """Average ranks (ties share the mean rank), with numpy."""
    a = np.asarray(a, dtype=float)
    r = np.empty(len(a))
    r[a.argsort(kind="mergesort")] = np.arange(1, len(a) + 1)
    _, inv, counts = np.unique(a, return_inverse=True, return_counts=True)
    return (np.bincount(inv, weights=r) / counts)[inv]


def spearman(x, y):
    """Rank correlation: +1 = y always goes up with x. None when either side has no spread."""
    if len(x) < 3:
        return None
    rx, ry = _rank(x), _rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return round(float(np.corrcoef(rx, ry)[0, 1]), 4)


def speaker_bootstrap(rows, stat, n_boot=1000, seed=0):
    """95% interval for stat(rows), resampling whole SPEAKERS with replacement."""
    by = defaultdict(list)
    for r in rows:
        by[r["speaker"]].append(r)
    groups = list(by.values())
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        v = stat([r for i in pick for r in groups[i]])
        if v is not None:
            vals.append(v)
    if not vals:
        return (None, None)
    return (round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4))


def _share(k, n):
    return dict(n=n, fired=k, rate=round(k / n, 4) if n else None, ci=list(wilson(k, n)))


def _halves(rows):
    """dev, test (whichever exist) and both together."""
    out = {s: [r for r in rows if r["split"] == s] for s in ("dev", "test")}
    out = {s: rs for s, rs in out.items() if rs}
    out["both"] = list(rows)
    return out


def fire_summary(rows, cuts):
    """check -> half -> 'all' / 상 / 중 / 하 -> {n, fired, rate, ci}."""
    out = {}
    for check in cuts:
        out[check] = {}
        for half, rs in _halves([r for r in rows if r["check"] == check]).items():
            groups = {"all": rs}
            for v in (3, 2, 1):
                g = [r for r in rs if int(r["rating"]) == v]
                if g:
                    groups[RATING_NAME[v]] = g
            out[check][half] = {name: _share(sum(fires(r, check, cuts) for r in g), len(g))
                                for name, g in groups.items()}
    return out


def score_summary(rows, n_boot=1000):
    """half -> counts, mean score per rating, and per score: sentence-level Spearman (+ speaker-resampled 95%
    interval) and speaker-level Spearman (each speaker's mean score vs mean rating)."""
    out = {}
    for half, rs in _halves(rows).items():
        s = dict(n_sentences=len(rs), n_speakers=len({r["speaker"] for r in rs}), by_rating={})
        for v in (3, 2, 1):
            g = [r for r in rs if int(r["rating"]) == v]
            if g:
                s["by_rating"][RATING_NAME[v]] = dict(n=len(g), **{k: round(float(np.mean([float(r[k]) for r in g])), 4)
                                                                   for k in SCORES})
        by = defaultdict(list)
        for r in rs:
            by[r["speaker"]].append(r)
        for k in SCORES:
            stat = lambda sub, k=k: spearman([float(r[k]) for r in sub], [int(r["rating"]) for r in sub])
            s[k] = dict(spearman=stat(rs), ci_by_speaker=list(speaker_bootstrap(rs, stat, n_boot=n_boot)),
                        speaker_level_spearman=spearman([np.mean([float(r[k]) for r in g]) for g in by.values()],
                                                        [np.mean([int(r["rating"]) for r in g]) for g in by.values()]))
        out[half] = s
    return out


# ---------- 4. safety + resume ----------
def check_listener():
    """The native cut-offs were measured with the ORIGINAL listener; measuring learners with another one would
    compare two different rulers."""
    from backend.listener import listener_tag
    if listener_tag() != "":
        raise SystemExit("eval.aihub505 needs the original listener: unset PC_LISTENER "
                         "(the native Korean cut-offs were measured with it)")


def done_files(path):
    if not Path(path).exists():
        return set()
    return {r["file"] for r in csv.DictReader(open(path, encoding="utf-8"))}


# ---------- 5. measuring one recording (loads the model) ----------
@cache
def _ko_g2p():
    from g2pk import G2p
    return G2p()


def stop_starts(em, phones):
    """spikes/b_vot.py's stop times: force its phone list onto OUR emissions -> start (s) of each phone's spike.
    Same model and maths as spikes/b_vot.py Aligner.starts, without loading the model a second time."""
    import torch
    import torchaudio.functional as F
    from backend.align import _model, vocab
    ids = torch.tensor([[vocab()[p] for p in phones]], dtype=torch.int32)
    labels, scores = F.forced_align(em.log_probs.unsqueeze(0), ids, blank=_model()[1].config.pad_token_id)
    return [s.start * em.sec_per_frame for s in F.merge_tokens(labels[0], scores[0].exp())]


def measure_recording(audio, sr, text):
    """-> (sentence numbers {n, heard, missing, conf}, sound rows). Uses the SAME code that measured the native
    speakers: eval/korean_carryover.py's _measure for ㄹ, spikes/b_vot.py's korean_targets + measure_vot for stops
    (so a learner's number and a native number come from one ruler; the live tests check this on Zeroth)."""
    import parselmouth
    import torch
    import torchaudio.functional as F
    from backend.align import align, emissions
    from backend.compare import attach_heard
    from backend.g2p import expected_phonemes
    from backend.match import sentence_features
    from backend.recognize import recognize
    from eval.korean_carryover import _measure, intervocalic
    from spikes.b_vot import EMPTY, korean_targets, measure_vot

    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if sr != 16000:  # measure_vot works at 16 kHz
        audio, sr = F.resample(torch.from_numpy(audio), sr, 16000).numpy(), 16000
    expected = expected_phonemes(text, "ko")
    em = emissions(audio, sr)
    words = align(em, expected, "ko")
    heard_words, _ = attach_heard(copy.deepcopy(words), recognize(em), "ko")
    feats = sentence_features(heard_words)

    sounds = []
    picks = [(wi, pi, "ko_tap") for wi, w in enumerate(expected) for pi, p in enumerate(w["phonemes"])
             if p == "ɾ" and intervocalic(w["phonemes"], pi)]
    if picks:
        for row in _measure(audio, sr, dict(em=em, words=words), picks, "ko", "", ""):
            for c in TAP_CHECKS:
                sounds.append(dict(check=c, word=row["word"], start=row["start"], margin_r=row["margin_r"],
                                   margin_l=row["margin_l"], f3_dip="" if row["f3_dip"] is None else row["f3_dip"],
                                   vot=""))
    phones, targets = korean_targets(text, _ko_g2p())
    tense = [t for t in targets if t[1] == "tense"]
    if tense:
        st = stop_starts(em, phones)
        pitch = parselmouth.Sound(audio, sr).to_pitch(time_step=0.002, pitch_floor=75, pitch_ceiling=500)
        for pi, _, _, word, _ in tense:
            m = measure_vot(audio, pitch, st[pi], st[pi + 1]) or EMPTY
            sounds.append(dict(check="tense_puff_vot", word=word, start=round(st[pi], 3), margin_r="", margin_l="",
                               f3_dip="", vot=m["vot"]))
    return feats, sounds


# ---------- 6. the run ----------
def _writer(path, fields):
    new = not path.exists()
    f = open(path, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=fields)
    if new:
        w.writeheader()
    return f, w


def run(items, sentences, sounds):
    done = done_files(sentences)
    todo = [it for it in items if it["file"] not in done]
    print(f"{len(items)} recordings chosen, {len(items) - len(todo)} already done, {len(todo)} to go", flush=True)
    sentences.parent.mkdir(parents=True, exist_ok=True)
    fs, ws = _writer(sentences, SENTENCE_FIELDS)
    fo, wo = _writer(sounds, SOUND_FIELDS)
    zips, t0 = {}, time.time()
    import soundfile as sf
    try:
        for n, it in enumerate(todo, 1):
            z = zips.setdefault(it["audio_zip"], zipfile.ZipFile(it["audio_zip"], metadata_encoding="cp949"))
            base = {k: it[k] for k in ("file", "speaker", "split", "rating")}
            row = dict(base, seconds=it["seconds"], n="", heard="", missing="", conf="", error="")
            try:
                audio, sr = sf.read(io.BytesIO(z.read(it["member"])), dtype="float32")
                feats, rows = measure_recording(audio, sr, it["text"])
                row.update({k: (round(v, 4) if isinstance(v, float) else v) for k, v in feats.items()})
                for r in rows:
                    wo.writerow(dict(base, **r))
            except ValueError as e:          # too short for the sentence, no Korean words, ...
                row["error"] = str(e)[:120]
            ws.writerow(row)                 # the sentence row is written LAST: it marks the recording as done
            fs.flush()
            fo.flush()
            if n % 50 == 0 or n == len(todo):
                rate = (time.time() - t0) / n
                print(f"{time.strftime('%H:%M:%S')} {n}/{len(todo)} {rate:.2f} s/recording "
                      f"~{rate * (len(todo) - n) / 3600:.1f} h left", flush=True)
    finally:
        fs.close()
        fo.close()
        for z in zips.values():
            z.close()


def _read(path):
    return list(csv.DictReader(open(path, encoding="utf-8"))) if Path(path).exists() else []


def report(sentences, sounds, out, settings, dropped=None, n_boot=1000):
    cuts_full = {c: native_cut(v) for c, v in native_values().items()}
    cuts = {c: v["cut"] for c, v in cuts_full.items()}
    sent = [r for r in _read(sentences) if not r["error"]]
    failed = sum(1 for r in _read(sentences) if r["error"])
    ok_files = {r["file"] for r in sent}
    seen, snd = set(), []
    for r in _read(sounds):            # a crash between the two writes can leave a recording's sounds twice
        key = (r["file"], r["check"], r["start"])
        if r["file"] in ok_files and key not in seen:
            seen.add(key)
            snd.append(r)
    res = dict(
        source="eval/aihub505.py: AI Hub 505, English-L1 learners reading Korean scripts",
        warning=("Fire rate = real errors + false alarms; nobody has checked which (no per-sound labels), so it "
                 "is an UPPER BOUND on false alarms, not a detection rate. Cut-offs come from native Zeroth "
                 "speakers (other microphones than AI Hub's phones), so part of any gap can be the recording "
                 "setup. The 상/중/하 rating is for the whole sentence; the label files don't say what the raters "
                 "judged. Aggregate counts only; no recordings or transcripts."),
        settings=settings, dropped_before_run=dropped, failed_in_run=failed,
        recordings=len(sent), speakers=len({r["speaker"] for r in sent}),
        native_cuts={c: dict(name=CHECKS[c][2], **v) for c, v in cuts_full.items()},
        fire=fire_summary(snd, cuts), scores=score_summary(sent, n_boot=n_boot))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"\n{len(sent)} recordings ({failed} failed) -> {out}")
    print("| check | native fired | learners fired (both halves) | 상 | 중 | 하 |")
    print("|---|---|---|---|---|---|")
    for c, by in res["fire"].items():
        b = by.get("both", {})
        cell = lambda g: f"{b[g]['fired']}/{b[g]['n']} ({b[g]['rate']:.1%})" if g in b and b[g]["n"] else "-"
        nc = cuts_full[c]
        print(f"| {CHECKS[c][2]} | {nc['fired']}/{nc['n']} | {cell('all')} | {cell('상')} | {cell('중')} | {cell('하')} |")
    for half, s in res["scores"].items():
        line = ", ".join(f"{k} rho={s[k]['spearman']} {s[k]['ci_by_speaker']} spk={s[k]['speaker_level_spearman']}"
                         for k in SCORES)
        print(f"scores {half} ({s['n_sentences']} sentences, {s['n_speakers']} speakers): {line}")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="smoke run: this many recordings, output to data/cache/aihub505_smoke_*")
    ap.add_argument("--per-speaker", type=int, help="at most this many recordings per speaker")
    ap.add_argument("--split", choices=["dev", "test", "both"], default="both")
    ap.add_argument("--report", action="store_true", help="only rebuild the report from the cached rows")
    args = ap.parse_args(argv)
    paths = (SMOKE["sentences"], SMOKE["sounds"], SMOKE["results"]) if args.limit else (SENTENCES, SOUNDS, RESULTS)
    settings = dict(per_speaker=args.per_speaker, split=args.split, limit=args.limit, cap=CAP)
    if args.report:
        report(*paths, settings)
        return
    check_listener()
    items, dropped = load_items()
    print(f"usable readings: {len(items)} from {len({i['speaker'] for i in items})} speakers; dropped {dropped}",
          flush=True)
    items.sort(key=lambda i: (i["speaker"], i["file"]))
    if args.split != "both":
        items = [i for i in items if i["split"] == args.split]
    items = per_speaker(items, args.per_speaker)
    if args.limit:
        items = items[:args.limit]
    run(items, paths[0], paths[1])
    report(*paths, settings, dropped=dropped)


if __name__ == "__main__":
    sys.exit(main())
