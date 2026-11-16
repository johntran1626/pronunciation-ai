"""Korean "did you say it?": the sentence check and the word check, measured with BOTH listeners.

    python -m eval.korean_match --run        # ~1 h on CPU, resumable (same command continues)
    python -m eval.korean_match --run --limit 3   # quick check: 3 recordings per source
    python -m eval.korean_match              # report only -> results/korean_match.json
    python -m eval.korean_match --run --learners-only --ratings 2 1   # also the 중 / 하 learners (~25 min)

Why: for Korean the app only rejects a recording with no speech in it. A native who reads the wrong sentence, skips
a word or says a different word gets no red. This measures whether the two checks English already has can work for
Korean, and which listener should do it:
  orig  the main multilingual model the app aligns Korean with today (backend/align.py)
  ko    the Korean-trained listener (backend/korean_listener.py), already loaded for the Korean sound checks

The evidence (both listeners, same shape as backend/match.py): per word and per sentence, the share of expected
sounds the free transcription heard in their place ("heard") and the aligner's average confidence ("conf").

Recordings, every one real speech; the mistakes are made by editing it, so the right answer is known:
  natives   Zeroth native readers. tune = 16 speakers of a train shard (20 readings each); test = the 10 test-split
            speakers (all 457 readings). Conditions as in eval/match_eval.py:
              orig   the reading + its own text         -> must pass, no word may be flagged
              swap   one word of the TEXT replaced by a word from another sentence -> that word wasn't said
              cut    one word's AUDIO cut out (times from the main aligner)         -> that word wasn't said
              other  a different sentence's text        -> the sentence doesn't match
  noise     silence / white noise / a beep / a hum + a real text -> no speech
  learners  AI Hub 505, English-L1 learners rated top (상) for the sentence, 6 readings each (reading = script word
            for word). orig only. Their false flags are an UPPER bound (a real skipped sound counts against us).

Thresholds are picked on the tune natives (eval/match_tune.py pickers and caps: 1% of correct readings rejected,
0.2% of spoken words flagged), then judged on the test natives and the learners by BARS (fixed before the run):
  sentence check: test natives rejected <= 1%, every noise clip rejected, >= 50% of wrong-sentence texts caught
  word check:     test natives' words flagged <= 0.5%, >= 25% of cut or swapped words caught
  then each check GRADES (red) if the learners also pass (sentence rejected <= 2%, words flagged <= 1%),
  else it may only show a soft "check this" HINT. A check that fails a natives bar is OFF.
Nothing in the app changes here: the report proposes, John decides, a later step wires it in.
"""
import argparse
import csv
import io
import json
import random
import time
import zipfile
from pathlib import Path

import numpy as np

from eval.match_tune import SENTENCE_CAP, WORD_CAP, gate_rejects, pick_gate, pick_word_rule, rate, word_flags, word_report

CACHE = Path("data/cache")
PATHS = {"sentences": CACHE / "korean_match_sentences.csv", "words": CACHE / "korean_match_words.csv",
         "done": CACHE / "korean_match_done.csv"}
RESULTS = Path("results/korean_match.json")
LOG = CACHE / "korean_match_run.log"
ZEROTH = Path("data/zeroth/data")
NATIVES = [("tune", ZEROTH / "train-00000-of-00006.parquet", 20), ("test", ZEROTH / "test-00000-of-00001.parquet", 0)]
LEARNERS_PER_SPEAKER = 6
TOP_RATING = 3            # 상
LISTENERS = ("orig", "ko")
BARS = {"natives_rejected": 0.01, "other_caught": 0.5, "learners_rejected": 0.02,
        "natives_false_word": 0.005, "caught_word": 0.25, "learners_false_word": 0.01}
S_FIELDS = ["listener", "source", "group", "speaker", "utt", "rating", "cond", "n", "heard", "conf", "n_heard"]
W_FIELDS = ["listener", "source", "group", "speaker", "utt", "cond", "word_index", "is_target", "dist", "n", "heard",
            "missing", "conf", "human"]


# ---------- 1. the made-up mistakes for one reading ----------
def plan_edits(rng, text, pool):
    """Which word to swap (and with what) and which word to cut out. Same rng -> same edits."""
    words = text.split()
    k = rng.randrange(len(words))
    word = rng.choice([w for w in pool if w != words[k]])
    return {"swap_index": k, "swap_word": word, "swapped": " ".join(words[:k] + [word] + words[k + 1:]),
            "cut_index": rng.randrange(len(words))}


# ---------- 2. the evidence from each listener ----------
class Listener:
    """listen() runs the model once on some audio; measure() reads any text against that output."""

    def __init__(self, name):
        self.name = name

    def listen(self, audio, sr):
        if self.name == "orig":
            from backend.align import emissions
            from backend.recognize import recognize
            em = emissions(audio, sr, "ko")
            return em, recognize(em)
        from backend.korean_listener import emissions, greedy
        lp = emissions(audio, sr)
        return lp, greedy(lp)

    def measure(self, out, text):
        """-> (per-word features, sentence features, n_heard, aligned words or None). ValueError: can't align."""
        from backend.g2p import expected_phonemes
        expected = expected_phonemes(text, "ko")
        if self.name == "orig":
            from backend.align import align
            from backend.compare import attach_heard
            from backend.match import sentence_features, word_features
            em, heard = out
            words, _ = attach_heard(align(em, expected, "ko"), heard, "ko")
            return [word_features(w) for w in words], sentence_features(words), len(heard), words
        from backend.korean_listener import sentence_evidence, word_evidence
        lp, heard = out
        per, n_heard = word_evidence(lp, expected, heard)
        return per, sentence_evidence(per), n_heard, None


def _round(f):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()}


def recording_rows(base, audio, sr, text, edits, other_text, listeners, conds):
    """All conditions for one reading, every listener. -> (sentence rows, word rows)."""
    srows, wrows = [], []
    outs = {L.name: L.listen(audio, sr) for L in listeners}

    def add(L, cond, out, t, target=None):
        per, sent, n_heard, words = L.measure(out, t)
        srows.append(dict(base, listener=L.name, cond=cond, n_heard=n_heard, **_round(sent)))
        if cond in ("orig", "swap", "cut"):
            for i, f in enumerate(per):
                g = _round(f)
                wrows.append(dict(base, listener=L.name, cond=cond, word_index=i, is_target=int(i == target),
                                  dist="" if target is None else abs(i - target), human="",
                                  n=g["n"], heard=g["heard"], missing=g["missing"], conf=g["conf"]))
        return words

    times = None
    for L in listeners:
        words = add(L, "orig", outs[L.name], text)
        if words is not None:
            times = [(w["start"], w["end"]) for w in words]     # the main aligner's word times, for the cut
    if "edits" not in conds:
        return srows, wrows
    for L in listeners:
        try:
            add(L, "swap", outs[L.name], edits["swapped"], edits["swap_index"])
        except (ValueError, AssertionError):
            pass
        try:
            add(L, "other", outs[L.name], other_text)
        except (ValueError, AssertionError):
            srows.append(dict(base, listener=L.name, cond="other", n=0, heard=0, conf=0, n_heard=0))
    if times and len(times) == len(text.split()):
        k = edits["cut_index"]
        a, b = int(times[k][0] * sr), int(times[k][1] * sr)
        cut = np.concatenate([audio[:a], audio[b:]])
        for L in listeners:
            try:
                add(L, "cut", L.listen(cut, sr), text, k)
            except (ValueError, AssertionError):
                pass
    return srows, wrows


# ---------- 3. the recordings ----------
def natives(limit):
    import pyarrow.parquet as pq
    import soundfile as sf
    pool = None
    for group, path, per_speaker in NATIVES:
        rows = pq.read_table(path, columns=["id", "speaker_id", "audio", "text"]).to_pylist()
        pool = sorted({w for r in rows for w in r["text"].split() if len(w) >= 2})
        seen = {}
        for r in rows:
            n = seen[r["speaker_id"]] = seen.get(r["speaker_id"], 0) + 1
            if (per_speaker and n > per_speaker) or (limit and n > 1) or (limit and len(seen) > limit):
                continue
            rng = random.Random(r["id"])
            other = rng.choice([x["text"] for x in rows if x["text"] != r["text"]])
            edits = plan_edits(rng, r["text"], pool)

            def load(b=r["audio"]["bytes"]):
                return sf.read(io.BytesIO(b), dtype="float32")
            yield (f"native:{r['id']}", dict(source="natives", group=group, speaker=f"z{r['speaker_id']}", utt=r["id"],
                                              rating=""), load, r["text"], edits, other, {"edits"})


def learner_group(rating):
    """상 learners keep the name the bars use; 중 / 하 get their own group (reported, not part of the bars)."""
    return "learners" if rating == TOP_RATING else f"learners_{rating}"


def learners(limit, ratings=(TOP_RATING,)):
    import soundfile as sf
    from eval.aihub505 import load_items, per_speaker
    items, _ = load_items()
    items = [i for i in items if i["rating"] in ratings]
    items.sort(key=lambda i: (i["speaker"], i["file"]))
    items = per_speaker(items, LEARNERS_PER_SPEAKER)[: limit or None]
    zips = {}
    for it in items:
        def load(it=it):
            z = zips.setdefault(it["audio_zip"], zipfile.ZipFile(it["audio_zip"], metadata_encoding="cp949"))
            return sf.read(io.BytesIO(z.read(it["member"])), dtype="float32")
        yield (f"learner:{it['file']}", dict(source="learners", group=learner_group(it["rating"]), speaker=it["speaker"], utt=it["file"],
                                             rating=it["rating"]), load, it["text"], None, None, set())


def noise_rows(listeners):
    rng = np.random.default_rng(0)
    sr, srows = 16000, []
    texts = ["강아지가 용변을 보도록 유도하는 말을 가르칠 수도 있다", "돌고래는 주로 오징어 물고기 갑각류 등을 먹고 삽니다"]
    for seconds in (2, 4, 8):
        n = sr * seconds
        t = np.arange(n) / sr
        for kind, x in [("silence", np.zeros(n)), ("white_noise", 0.05 * rng.standard_normal(n)),
                        ("beep", 0.3 * np.sin(2 * np.pi * 440 * t)), ("hum", 0.2 * np.sin(2 * np.pi * 60 * t))]:
            for L in listeners:
                out = L.listen(x.astype("float32"), sr)
                for text in texts:
                    try:
                        _, sent, n_heard, _ = L.measure(out, text)
                    except (ValueError, AssertionError):
                        continue      # "too short for this sentence": the API already refuses it
                    srows.append(dict(listener=L.name, source="noise", group="noise", speaker=kind,
                                      utt=f"{seconds}s", rating="", cond="noise", n_heard=n_heard, **_round(sent)))
    return srows


def _done(path):
    return {r["key"] for r in csv.DictReader(open(path, encoding="utf-8"))} if path.exists() else set()


def _writer(path, fields):
    new = not path.exists()
    f = open(path, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    if new:
        w.writeheader()
    return f, w


def run(limit=None, ratings=(TOP_RATING,), learners_only=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    listeners = [Listener(n) for n in LISTENERS]
    done = _done(PATHS["done"])
    fs, ws = _writer(PATHS["sentences"], S_FIELDS)
    fw, ww = _writer(PATHS["words"], W_FIELDS)
    fd, wd = _writer(PATHS["done"], ["key", "error"])
    t0, n = time.time(), 0
    try:
        if "noise" not in done and not learners_only:
            ws.writerows(noise_rows(listeners))
            wd.writerow(dict(key="noise", error=""))
        for source in ([] if learners_only else natives(limit), learners(limit, ratings)):
            for key, base, load, text, edits, other, conds in source:
                if key in done:
                    continue
                err = ""
                try:
                    audio, sr = load()
                    if audio.ndim > 1:
                        audio = audio.mean(axis=1)
                    srows, wrows = recording_rows(base, audio, sr, text, edits, other, listeners, conds)
                    ws.writerows(srows)
                    ww.writerows(wrows)
                except (ValueError, AssertionError) as e:     # too short, no Korean sounds, alignment mismatch
                    err = str(e)[:120] or type(e).__name__
                wd.writerow(dict(key=key, error=err))        # written LAST: marks the recording as done
                for f in (fs, fw, fd):
                    f.flush()
                n += 1
                if n % 50 == 0:
                    print(f"{time.strftime('%H:%M:%S')} {n} recordings, {(time.time() - t0) / n:.2f} s each", flush=True)
    finally:
        for f in (fs, fw, fd):
            f.close()
    print(f"done: {n} recordings in {time.time() - t0:.0f} s", flush=True)


# ---------- 4. the report ----------
def decide(m):
    """Measured numbers -> "grade" / "hint" / "off" per check (BARS, fixed before the run)."""
    s, w = m["sentence"], m["word"]
    s_ok = s["natives_rejected"] <= BARS["natives_rejected"] and s["noise_all_rejected"] \
        and s["other_caught"] >= BARS["other_caught"]
    w_ok = w["natives_false"] <= BARS["natives_false_word"] and w["caught"] >= BARS["caught_word"]
    return {"sentence": "off" if not s_ok else "grade" if s["learners_rejected"] <= BARS["learners_rejected"] else "hint",
            "word": "off" if not w_ok else "grade" if w["learners_false"] <= BARS["learners_false_word"] else "hint"}


def _load(path, numeric):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for r in rows:
        for k in numeric:
            r[k] = float(r[k]) if r.get(k) not in (None, "") else 0.0
    return rows


def listener_report(L, S, W):
    S = [r for r in S if r["listener"] == L]
    W = [w for w in W if w["listener"] == L]
    tune = [r for r in S if r["group"] == "tune"]
    test = [r for r in S if r["group"] == "test"]
    noise = [r for r in S if r["cond"] == "noise"]
    lrn = [r for r in S if r["group"] == "learners"]
    gate = pick_gate([r for r in tune if r["cond"] == "orig"], [r for r in tune if r["cond"] == "other"] + noise,
                     SENTENCE_CAP)
    w_tune = [w for w in W if w["group"] == "tune"]
    rule = pick_word_rule([w for w in w_tune if w["cond"] == "orig"],
                          [w for w in w_tune if w["cond"] in ("cut", "swap") and w["is_target"] == 1], WORD_CAP)
    w_test = word_report([w for w in W if w["group"] == "test"], test, gate, rule)

    def rej(rows, cond):
        rs = [r for r in rows if r["cond"] == cond]
        return rate(sum(gate_rejects(r, gate) for r in rs), len(rs))
    passed = {(r["speaker"], r["utt"]) for r in lrn if not gate_rejects(r, gate)}
    lw = [w for w in W if w["group"] == "learners" and (w["speaker"], w["utt"]) in passed]
    lrn_word = rate(sum(word_flags(w, rule) for w in lw), len(lw))
    nat = {"orig": rej(test, "orig"), "other": rej(test, "other"), "swap": rej(test, "swap"), "cut": rej(test, "cut")}
    noise_r = rate(sum(gate_rejects(r, gate) for r in noise), len(noise))
    catch = max(w_test["caught_cut"]["rate"] or 0, w_test["caught_swap"]["rate"] or 0)
    measured = {"sentence": {"natives_rejected": nat["orig"]["rate"], "noise_all_rejected": noise_r["k"] == noise_r["n"],
                             "other_caught": nat["other"]["rate"], "learners_rejected": rej(lrn, "orig")["rate"]},
                "word": {"natives_false": w_test["false_not_heard_all_words"]["rate"], "caught": catch,
                         "learners_false": lrn_word["rate"]}}
    by_rating = {}
    for g in sorted({r["group"] for r in S if r["group"].startswith("learners")}):
        rs = [r for r in S if r["group"] == g]
        ok = {(r["speaker"], r["utt"]) for r in rs if not gate_rejects(r, gate)}
        ws_ = [w for w in W if w["group"] == g and (w["speaker"], w["utt"]) in ok]
        by_rating[g] = {"sentence_rejected": rej(rs, "orig"), "words_flagged": rate(sum(word_flags(w, rule) for w in ws_), len(ws_))}
    return {"learners_by_rating": by_rating, "sentence": {"thresholds": gate, "test_natives": nat, "noise": noise_r,
                         "tune_natives_rejected": rej(tune, "orig"), "learners_rejected": rej(lrn, "orig")},
            "word": {"thresholds": rule, "test_natives": w_test, "learners_flagged": lrn_word},
            "measured": measured, "verdict": decide(measured)}


def choose(per_listener):
    """Per check: the listener with the best verdict (grade > hint > off), then the most catches."""
    rank = {"grade": 2, "hint": 1, "off": 0}
    out = {}
    for check, key in (("sentence", "other_caught"), ("word", "caught")):
        best = max(per_listener, key=lambda L: (rank[per_listener[L]["verdict"][check]],
                                                per_listener[L]["measured"][check][key] or 0))
        out[check] = {"listener": best, "mode": per_listener[best]["verdict"][check],
                      "thresholds": per_listener[best][check]["thresholds"]}
    return out


def report():
    S = _load(PATHS["sentences"], ("n", "heard", "conf", "n_heard"))
    W = _load(PATHS["words"], ("n", "heard", "conf", "is_target"))
    for w in W:
        w["dist"] = int(w["dist"]) if w["dist"] not in ("", None) else -1
    done = list(csv.DictReader(open(PATHS["done"], encoding="utf-8")))
    per = {L: listener_report(L, S, W) for L in LISTENERS if any(r["listener"] == L for r in S)}
    res = {"source": "eval/korean_match.py", "bars": BARS, "caps": {"sentence": SENTENCE_CAP, "word": WORD_CAP},
           "recordings": {"done": len(done), "failed": sum(bool(d["error"]) for d in done),
                          "natives_tune": len({r["utt"] for r in S if r["group"] == "tune"}),
                          "natives_test": len({r["utt"] for r in S if r["group"] == "test"}),
                          "learners": len({r["utt"] for r in S if r["group"] == "learners"}),
                          "learner_speakers": len({r["speaker"] for r in S if r["group"] == "learners"})},
           "warning": "Learner flags are an upper bound on false alarms (a real skipped sound counts against us); "
                      "cut times come from the main aligner. Aggregate counts only.",
           "listeners": per, "proposal": choose(per)}
    RESULTS.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    return res


def show(res):
    print(f"recordings: {res['recordings']}")
    for L, r in res["listeners"].items():
        m = r["measured"]
        print(f"\n[{L}] sentence {r['sentence']['thresholds']} -> {r['verdict']['sentence']}: natives rejected "
              f"{m['sentence']['natives_rejected']}, other caught {m['sentence']['other_caught']}, noise all "
              f"{m['sentence']['noise_all_rejected']}, learners rejected {m['sentence']['learners_rejected']}")
        for g, v in r["learners_by_rating"].items():
            print(f"[{L}] {g}: sentences rejected {v['sentence_rejected']['k']}/{v['sentence_rejected']['n']}, "
                  f"words flagged {v['words_flagged']['k']}/{v['words_flagged']['n']}")
        print(f"[{L}] word {r['word']['thresholds']} -> {r['verdict']['word']}: natives words flagged "
              f"{m['word']['natives_false']}, caught (best of cut/swap) {m['word']['caught']}, learners words "
              f"flagged {m['word']['learners_false']}")
    print(f"\nproposal: {res['proposal']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ratings", type=int, nargs="+", default=[TOP_RATING], help="AI Hub ratings: 3 = 상, 2 = 중, 1 = 하")
    ap.add_argument("--learners-only", action="store_true")
    args = ap.parse_args()
    if args.run:
        run(args.limit, tuple(args.ratings), args.learners_only)
    show(report())
