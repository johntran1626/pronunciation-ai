"""Run the REAL pipeline on every annotated L2-ARCTIC sentence and attach the human verdicts.

    python -m eval.l2arctic                 # all 24 speakers x 150 annotated sentences (~20-40 min, CPU)
    python -m eval.l2arctic --limit 5       # quick check: 5 sentences per speaker

Output (git-ignored, data/cache/): eval_l2arctic.csv (one row per checkable sound, with our evidence
and the human label) and eval_l2arctic_timing.csv (seconds per sentence). eval/run.py reads these.

Groups: "korean" = HJK HKK YDCK YKWK (the TEST speakers: never used for tuning);
        "others" = the 20 other L1 speakers (Arabic, Mandarin, Hindi, Spanish, Vietnamese): TUNING.

How human labels reach our phonemes: L2-ARCTIC's "phones" tier lists the dictionary phones with error
marks ("L,R,s" = L said as R; "R,sil,d" = R dropped; "sil,AH,a" = extra AH added). We line that list up
with OUR expected phonemes (sequence_align); where both agree on the target phone, our phoneme gets the
human label. Where the two dictionaries disagree (e.g. "the" DH AH vs DH IY), we leave it unlabelled
rather than guess.
"""
import argparse
import csv
import io
import re
import time
import zipfile
from pathlib import Path

import soundfile as sf

from backend.acoustics import f3_dip, rl_f3, vb_features
from backend.features import sound_features
from backend.align import align, emissions
from eval.listener import keep_speaker, tagged
from backend.compare import attach_heard
from backend.g2p import ARPA2IPA, expected_phonemes
from backend.recognize import recognize
from backend.scoring import EXTRA_VOWEL, PAIRS, candidates
from backend.sequence_align import align_sequences
from eval.detectors import x_columns

DATA = Path("data/l2arctic")
FULL_ZIP = Path.home() / "Downloads" / "l2arctic_release_v5.0.zip"
KOREAN = ["HJK", "HKK", "YDCK", "YKWK"]
OUT = tagged(Path("data/cache/eval_l2arctic.csv"))   # own folder per listener
TIMING = tagged(Path("data/cache/eval_l2arctic_timing.csv"))
ARPA_VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"}
FIX = {"AX": "AH", "ɹ": "R", "R": "R"}
RL_PAIRS = {"r_as_l", "l_as_r"}  # pairs that get the F3 tie-breaker feature


# ---------- human labels ----------
def _norm(sym):
    s = sym.strip()
    s = FIX.get(s, s).upper().rstrip("012")
    return FIX.get(s, s)


def parse_label(label):
    """'AH0' -> ('AH','correct',None) · 'L,R,s' -> ('L','sub','R') · 'R,sil,d' -> ('R','del',None)
    · 'sil,AX,a' -> (None,'ins','AH')"""
    parts = [p.strip() for p in label.split(",")]
    if len(parts) == 1:
        return _norm(parts[0]), "correct", None
    target, perceived = parts[0], parts[1]
    kind = parts[2].lower() if len(parts) > 2 else "s"
    if kind == "a":
        return None, "ins", _norm(perceived)
    if kind == "d" or perceived.lower() == "sil":
        return _norm(target), "del", None
    return _norm(target), "sub", _norm(perceived)


def _ipa(arpa):
    return ARPA2IPA.get(arpa, arpa.lower())  # compare in IPA so vowel/consonant swap costs work


def label_phonemes(words, human_labels):
    """-> (labels, ins_after). labels[k] = (kind, perceived) for OUR flat phoneme k, or None (unlabelled).
    ins_after = set of our phoneme indices that a human-marked EXTRA VOWEL follows."""
    ours = [a.rstrip("012") for w in words for a in w["pron"].split()]
    human, vowel_ins_after = [], set()
    for target, kind, perceived in map(parse_label, human_labels):
        if kind == "ins":
            if human and perceived in ARPA_VOWELS:
                vowel_ins_after.add(len(human) - 1)
        else:
            human.append((target, kind, perceived))

    labels, ours_of_human, i, h = [None] * len(ours), {}, 0, 0
    for op, _, _ in align_sequences([_ipa(a) for a in ours], [_ipa(t) for t, _, _ in human]):
        if op == "match":
            labels[i] = human[h][1:]
            ours_of_human[h] = i
        i += op in ("match", "sub", "del")
        h += op in ("match", "sub", "ins")
    return labels, {ours_of_human[h] for h in vowel_ins_after if h in ours_of_human}


def _phones_tier(textgrid):
    part = textgrid.split('name = "phones"')[1].split("item [")[0]
    return [lab.strip() for lab in re.findall(r'text = "([^"]*)"', part) if lab.strip() not in ("", "sil", "sp")]


# ---------- reading the corpus ----------
def korean_utterances(limit):
    for spk in KOREAN:
        for g in sorted((DATA / spk / "annotation").glob("*.TextGrid"))[:limit]:
            text = (DATA / spk / "transcript" / f"{g.stem}.txt").read_text().strip()
            yield "korean", spk, g.stem, g.read_text(encoding="utf-8", errors="replace"), text, DATA / spk / "wav" / f"{g.stem}.wav"


def other_utterances(limit):
    """The 20 non-Korean speakers, read straight from the download zip (nothing extracted)."""
    outer = zipfile.ZipFile(FULL_ZIP)
    for name in sorted(n for n in outer.namelist() if re.fullmatch(r"[A-Z]+\.zip", n)):
        spk = name[:-4]
        if spk in KOREAN:
            continue
        inner = zipfile.ZipFile(io.BytesIO(outer.read(name)))
        grids = sorted(m for m in inner.namelist() if "/annotation/" in m and m.endswith(".TextGrid"))[:limit]
        for g in grids:
            text = inner.read(g.replace("/annotation/", "/transcript/").replace(".TextGrid", ".txt")).decode().strip()
            wav = io.BytesIO(inner.read(g.replace("/annotation/", "/wav/").replace(".TextGrid", ".wav")))
            yield "others", spk, Path(g).stem, inner.read(g).decode("utf-8", "replace"), text, wav


# ---------- one sentence ----------
def human_status(cand, labels, ins_after, flat_index):
    lab = labels[flat_index]
    if cand["pair"] == EXTRA_VOWEL:
        if flat_index in ins_after:
            return "error", "extra vowel"
        return ("correct", "") if lab and lab[0] == "correct" else ("other", str(lab))
    if lab is None:
        return "unlabelled", ""
    kind, perceived = lab
    if kind == "correct":
        return "correct", ""
    if kind == "sub" and perceived in PAIRS[cand["pair"]]["human_wrong"]:
        return "error", perceived
    return "other", f"{kind}:{perceived}"


def run_one(group, spk, utt, textgrid, text, wav):
    return run_labelled(group, spk, utt, _phones_tier(textgrid), text, wav)


def run_labelled(group, spk, utt, human_labels, text, wav):
    """The pipeline on one recording + its human labels in L2-ARCTIC's format ('R', 'R,L,s', 'sil,AH,a', ...).
    wav = a file path / file object, or (audio, sr) already in memory (e.g. suitcase pieces)."""
    audio, sr = wav if isinstance(wav, tuple) else sf.read(wav, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    t0 = time.perf_counter()
    expected = expected_phonemes(text, "en")
    em = emissions(audio, sr)
    words, _ = attach_heard(align(em, expected, "en"), recognize(em), "en")
    cands = candidates(em, words, "en")
    seconds = time.perf_counter() - t0
    f3_of, ref = rl_f3(audio, sr, words)
    vb = vb_features(audio, sr, words)  # frication + closure dip in every [v] window
    # the shared detector features for every checked sound (backend/features.py)
    xf = sound_features(audio, sr, words, slots=sorted({(c["word_index"], c["phoneme_index"]) for c in cands}))

    labels, ins_after = label_phonemes(words, human_labels)
    offsets = [0]
    for w in words:
        offsets.append(offsets[-1] + len(w["phonemes"]))
    rows = []
    for c in cands:
        k = offsets[c["word_index"]] + c["phoneme_index"]
        p = words[c["word_index"]]["phonemes"][c["phoneme_index"]]
        human, detail = human_status(c, labels, ins_after, k)
        baseline = bool(p["extra_after"]) if c["pair"] == EXTRA_VOWEL else p["op"] != "match"
        rows.append(dict(group=group, speaker=spk, utt=utt, word=words[c["word_index"]]["word"], pair=c["pair"],
                         target=p["ipa"], human=human, human_detail=detail, margin=c["margin"],
                         heard_agrees=int(c["heard_agrees"]), op=p["op"], heard=p["heard"] or "",
                         baseline_flag=int(baseline), f3="", f3_dip="", fric="", closure="",
                         word_index=c["word_index"], phoneme_index=c["phoneme_index"],
                         start=round(p["start"], 3), end=round(p["end"], 3),
                         **x_columns(xf.get((c["word_index"], c["phoneme_index"])))))
        if c["pair"] in RL_PAIRS:  # blank = not measured (not an R/L sound, unvoiced window, or < 3 vowels)
            f3 = f3_of.get((c["word_index"], c["phoneme_index"]))
            dip = f3_dip(f3, ref)
            rows[-1]["f3"] = "" if f3 is None else round(f3, 1)
            rows[-1]["f3_dip"] = "" if dip is None else dip
        if c["pair"] == "v_as_b":  # blank = not measured (fewer than 3 vowels in the sentence)
            for k, v in vb.get((c["word_index"], c["phoneme_index"]), {}).items():
                rows[-1][k] = "" if v is None else v
    return rows, seconds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="sentences per speaker (quick check)")
    ap.add_argument("--out", type=Path, default=OUT, help="where to write the rows (default: the eval cache)")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n, start = 0, time.time()
    timing = TIMING if args.out == OUT else args.out.with_name(args.out.stem + "_timing.csv")
    with open(args.out, "w", newline="") as f, open(timing, "w", newline="") as ft:
        out, tout = None, csv.writer(ft)
        tout.writerow(["group", "speaker", "utt", "seconds"])
        for source in (korean_utterances(args.limit), other_utterances(args.limit)):
            for group, spk, utt, grid, text, wav in source:
                if not keep_speaker("l2arctic", spk, group == "korean"):   # PC_SPEAKERS=heldout
                    continue
                try:
                    rows, sec = run_one(group, spk, utt, grid, text, wav)
                except ValueError as e:  # e.g. recording too short for the sentence
                    print(f"skip {spk}/{utt}: {e}")
                    continue
                if out is None:
                    out = csv.DictWriter(f, fieldnames=list(rows[0]))
                    out.writeheader()
                out.writerows(rows)
                tout.writerow([group, spk, utt, round(sec, 3)])
                n += 1
                if n % 100 == 0:
                    print(f"{n} sentences, {time.time() - start:.0f} s", flush=True)
    print(f"done: {n} sentences in {time.time() - start:.0f} s -> {args.out}")


if __name__ == "__main__":
    main()
