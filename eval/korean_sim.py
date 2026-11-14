"""Simulated Korean learner errors by TEXT SWAP. We have no labeled learner Korean, so we make
labeled errors from native audio. 

    python -m eval.korean_sim              # tune: Zeroth train-00000 (16 speakers x 60); test: Zeroth test (10)
    python -m eval.korean_sim --limit 5    # quick check: 5 recordings per speaker

The trick, in plain words: a native speaker says 불. We tell the app the target was 풀. Relative to that
target, the speaker "said ㅍ as ㅂ", and we know the label exactly because we made it.

  1. variants(text): for each syllable and each pair (ㅓ<->ㅗ, ㅡ<->ㅜ, all 6 directions in ㅂㅃㅍ / ㄷㄸㅌ / ㄱㄲㅋ),
     swap one jamo in the TARGET text. Keep it only if g2pk's expected sounds change in exactly ONE place,
     in the swapped word, from the intended sound to the intended sound (the one-difference rule).
     Example dropped: 학교 is said 학꾜, so its ㄱ is already tense and a swap can't make "ㄱ said as X".
  2. main(): the model runs ONCE per recording. The original text gives the CORRECT rows (every target
     sound of a pair); each sampled swap (at most 1 per pair per sentence) is re-aligned on the same model
     output and gives one ERROR row. Rows keep the aligned start/end, so later acoustic detectors
     (VOT, formants) can measure without the model.
  3. summarize(): per group (tune / test) and pair: errors caught and false alarms, for the BASELINE (flag
     any sound the recognizer heard differently) and the APP (score_words; Korean is always green in v1).

Limits (README): each "error" is a perfect native version of the wrong sound, so detection will look
BETTER than on real learners; the correct sounds come from natives, so false alarms will look LOWER.
Swapped targets can be non-words.

Output: data/cache/korean_sim.csv (git-ignored rows) and results/korean_sim.json (counts only).
"""
import argparse
import csv
import io
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq
import soundfile as sf

from backend.align import align, emissions
from backend.compare import attach_heard
from backend.g2p import ONSET, VOWEL, expected_phonemes
from backend.recognize import recognize
from backend.scoring import score_words
from eval.run import rate

ZEROTH = Path("data/zeroth/data")
SOURCES = [("tune", ZEROTH / "train-00000-of-00006.parquet", 60),   # (group, file, max recordings per speaker)
           ("test", ZEROTH / "test-00000-of-00001.parquet", 0)]     # 0 = all
OUT = Path("data/cache/korean_sim.csv")
RESULTS = Path("results/korean_sim.json")
SEED = 17
MIN_ERRORS, MIN_SPEAKERS = 100, 8   # a pair is "usable" on the test speakers only above both (fixed before the run)

# Unicode packs a Hangul block as (onset * 21 + vowel) * 28 + coda, starting at U+AC00.
ONSET_JAMO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
VOWEL_JAMO = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
FIRST, COUNT = 0xAC00, 11172


def _ipa(kind, jamo):
    return ONSET[ONSET_JAMO.index(jamo)] if kind == "onset" else VOWEL[VOWEL_JAMO.index(jamo)][0]


# pair name "target_as_said" -> (kind, said jamo = what the native actually said, target jamo = what we ask for)
PAIRS = {}
for a, b in [("ㅓ", "ㅗ"), ("ㅡ", "ㅜ")]:
    PAIRS[f"{a}_as_{b}"], PAIRS[f"{b}_as_{a}"] = ("vowel", b, a), ("vowel", a, b)
for series in ("ㅂㅃㅍ", "ㄷㄸㅌ", "ㄱㄲㅋ"):
    for target in series:
        for said in series:
            if target != said:
                PAIRS[f"{target}_as_{said}"] = ("onset", said, target)
STOP_PAIRS = {name for name, (kind, _, _) in PAIRS.items() if kind == "onset"}


# ---------- 1. making the swaps ----------
def swap_syllable(syl, kind, frm, to):
    """'불', 'onset', 'ㅂ', 'ㅍ' -> '풀'. None if syl isn't Hangul or doesn't have `frm` in that slot."""
    o = ord(syl) - FIRST
    if not 0 <= o < COUNT:
        return None
    onset, vowel, coda = o // 588, (o % 588) // 28, o % 28
    if kind == "onset":
        if ONSET_JAMO[onset] != frm:
            return None
        onset = ONSET_JAMO.index(to)
    else:
        if VOWEL_JAMO[vowel] != frm:
            return None
        vowel = VOWEL_JAMO.index(to)
    return chr(FIRST + (onset * 21 + vowel) * 28 + coda)


def _flat(words):
    return [(wi, pi, p) for wi, w in enumerate(words) for pi, p in enumerate(w["phonemes"])]


def _check(orig_words, text, pair):
    """The one-difference rule. -> a variant dict, or None if the swap isn't a clean single change."""
    kind, said, target = PAIRS[pair]
    try:
        new_words = expected_phonemes(text, "ko")
    except ValueError:
        return None
    a, b = _flat(orig_words), _flat(new_words)
    if len(a) != len(b):
        return None
    diffs = [(x, y) for x, y in zip(a, b) if x[2] != y[2]]
    if len(diffs) != 1:
        return None
    (wi, pi, said_ipa), (_, _, target_ipa) = diffs[0]
    if (said_ipa, target_ipa) != (_ipa(kind, said), _ipa(kind, target)):
        return None
    if orig_words[wi]["word"] == new_words[wi]["word"]:
        return None  # the change landed in a word we didn't touch
    return dict(pair=pair, target_text=text, word_index=wi, phoneme_index=pi,
                target_ipa=target_ipa, said_ipa=said_ipa)


def _swaps(text):
    """Every (pair, swapped text) one jamo away from `text`, in a fixed order."""
    written = text.split()
    for wi, word in enumerate(written):
        for ci, ch in enumerate(word):
            for pair, (kind, said, target) in PAIRS.items():
                new = swap_syllable(ch, kind, said, target)
                if new:
                    yield pair, " ".join(written[:wi] + [word[:ci] + new + word[ci + 1:]] + written[wi + 1:])


def variants(text):
    """All clean swaps of a sentence (used by the tests; main() samples lazily, which is faster)."""
    text = " ".join(text.split())
    orig = expected_phonemes(text, "ko")
    return [v for pair, new in _swaps(text) if (v := _check(orig, new, pair))]


def sample_variants(vs, rng):
    """At most one variant per pair, chosen at random (seeded, so the set is reproducible)."""
    by_pair = defaultdict(list)
    for v in vs:
        by_pair[v["pair"]].append(v)
    return [rng.choice(by_pair[p]) for p in sorted(by_pair)]


def _sampled_variants(text, orig, rng):
    """Same result type as sample_variants(variants(text)), but tries swaps in random order and stops at
    the first clean one per pair, so g2pk runs far fewer times."""
    by_pair = defaultdict(list)
    for pair, new in _swaps(text):
        by_pair[pair].append(new)
    out = []
    for pair in sorted(by_pair):
        options = by_pair[pair][:]
        rng.shuffle(options)
        for new in options:
            if v := _check(orig, new, pair):
                out.append(v)
                break
    return out


# ---------- 2. running the pipeline ----------
def _row(group, speaker, utt, pair, human, words, scored, wi, pi, said_ipa):
    flat = [p for w in words for p in w["phonemes"]]
    k = sum(len(w["phonemes"]) for w in words[:wi]) + pi
    p = flat[k]
    return dict(group=group, speaker=speaker, utt=utt, pair=pair, human=human, word=words[wi]["word"],
                word_index=wi, phoneme_index=pi, target_ipa=p["ipa"], said_ipa=said_ipa,
                prev_ipa=flat[k - 1]["ipa"] if k else "", next_ipa=flat[k + 1]["ipa"] if k + 1 < len(flat) else "",
                start=p["start"], end=p["end"], op=p["op"], heard=p["heard"] or "",
                baseline_flag=int(p["op"] != "match"),
                app_flag=int(scored[wi]["phonemes"][pi]["status"] == "red"))


def _analyze(em, heard, words):
    aligned, _ = attach_heard(align(em, words, "ko"), heard, "ko")
    return aligned, score_words(em, aligned, "ko")


def run_one(group, speaker, utt, text, audio, sr, rng):
    text = " ".join(text.split())
    em = emissions(audio, sr)
    heard = recognize(em)
    orig = expected_phonemes(text, "ko")
    words, scored = _analyze(em, heard, orig)
    rows = []
    for wi, w in enumerate(words):                     # CORRECT rows: what the native really said
        for pi, p in enumerate(w["phonemes"]):
            for pair, (kind, said, target) in PAIRS.items():
                if p["ipa"] == _ipa(kind, target):
                    rows.append(_row(group, speaker, utt, pair, "correct", words, scored, wi, pi, p["ipa"]))
    for v in _sampled_variants(text, orig, rng):      # ERROR rows: same audio, swapped target
        vwords, vscored = _analyze(em, heard, expected_phonemes(v["target_text"], "ko"))
        rows.append(_row(group, speaker, utt, v["pair"], "error", vwords, vscored,
                         v["word_index"], v["phoneme_index"], v["said_ipa"]))
        if v["pair"] in STOP_PAIRS:                    # known-answer check (pass bar 3)
            same = words[v["word_index"]]["phonemes"][v["phoneme_index"]]
            rows[-1]["known_answer_ok"] = int(rows[-1]["baseline_flag"] == int(same["op"] != "match")
                                              and rows[-1]["start"] == same["start"])
    return rows


def recordings(limit_override=None):
    for group, path, per_speaker in SOURCES:
        if limit_override:
            per_speaker = limit_override
        seen = Counter()
        for r in pq.read_table(path).to_pylist():
            seen[r["speaker_id"]] += 1
            if per_speaker and seen[r["speaker_id"]] > per_speaker:
                continue
            audio, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
            yield group, f"z{r['speaker_id']}", r["id"], r["text"], audio, sr


# ---------- 3. the report ----------
def summarize(rows):
    """-> {group: {pair: {errors, error_speakers, correct, baseline: {...}, app: {...}}}}."""
    out = defaultdict(dict)
    keyed = defaultdict(list)
    for r in rows:
        keyed[(r["group"], r["pair"])].append(r)
    for (group, pair), rs in sorted(keyed.items()):
        err = [r for r in rs if r["human"] == "error"]
        ok = [r for r in rs if r["human"] == "correct"]
        s = dict(errors=len(err), error_speakers=len({r["speaker"] for r in err}), correct=len(ok))
        for system in ("baseline", "app"):
            caught = sum(int(r[f"{system}_flag"]) for r in err)
            fa = sum(int(r[f"{system}_flag"]) for r in ok)
            s[system] = dict(caught=caught, detection=round(caught / len(err), 4) if err else None,
                             detection_ci95=rate(caught, len(err))["ci95"],
                             false_alarms=fa, false_alarm_rate=round(fa / len(ok), 4) if ok else None,
                             false_alarm_ci95=rate(fa, len(ok))["ci95"])
        out[group][pair] = s
    return dict(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="recordings per speaker (quick check)")
    args = ap.parse_args()
    rng = random.Random(SEED)
    rows, n, t0 = [], 0, time.time()
    for group, spk, utt, text, audio, sr in recordings(args.limit):
        try:
            rows += run_one(group, spk, utt, text, audio, sr, rng)
        except ValueError as e:
            print(f"skip {spk}/{utt}: {e}")
            continue
        n += 1
        if n % 100 == 0:
            print(f"{n} recordings, {time.time() - t0:.0f} s", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) + ["known_answer_ok"]
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(fields)))
        w.writeheader()
        w.writerows(rows)

    summary = summarize(rows)
    ka = [r["known_answer_ok"] for r in rows if "known_answer_ok" in r]
    test = summary.get("test", {})
    report = dict(
        source="eval/korean_sim.py: simulated errors by text swap on native Zeroth-Korean",
        warning="SIMULATED errors on NATIVE speech: detection is optimistic, false alarms are optimistic.",
        recordings=n, limit_per_speaker=args.limit, seed=SEED,
        known_answer_check=dict(stop_swaps=len(ka), identical=sum(ka), passed=bool(ka) and all(ka)),
        usable_pairs=sorted(p for p, s in test.items()
                            if s["errors"] >= MIN_ERRORS and s["error_speakers"] >= MIN_SPEAKERS),
        too_few_pairs=sorted(p for p, s in test.items()
                             if s["errors"] < MIN_ERRORS or s["error_speakers"] < MIN_SPEAKERS),
        pairs=summary,
    )
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"done: {n} recordings, {len(rows)} rows in {time.time() - t0:.0f} s -> {OUT}, {RESULTS}")
    print(f"known-answer check: {sum(ka)}/{len(ka)} identical -> {'PASS' if report['known_answer_check']['passed'] else 'FAIL'}")
    print(f"{'pair':10} {'errors':>6} {'spk':>3} {'correct':>7}  baseline caught / FA        app caught / FA")
    for pair, s in sorted(test.items()):
        b, a = s["baseline"], s["app"]
        print(f"{pair:10} {s['errors']:>6} {s['error_speakers']:>3} {s['correct']:>7}  "
              f"{b['caught']:>4} ({b['detection'] or 0:.0%}) / {b['false_alarms']:>4} ({b['false_alarm_rate'] or 0:.1%})"
              f"   {a['caught']:>3} / {a['false_alarms']:>3}")


if __name__ == "__main__":
    main()
