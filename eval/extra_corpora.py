"""Two more labelled English corpora, run through the SAME pipeline and labeller as eval/l2arctic.py.

1. speechocean762 (openslr.org/101, CC BY 4.0): 5,000 English sentences by 250 Mandarin speakers (128 adults,
   122 children). Five experts marked every sound: plain = fine, {X} = right but heavy accent, (X) = wrong or missing,
   [X] = an extra sound. They do NOT say what was said instead, so a wrong R can't be called "R said as L".
   What it's good for: (a) thousands of CORRECT sounds from new speakers (the false-alarm side, which is what the
   thresholds are set on), (b) extra vowels: [AH0] after a final consonant is exactly "bus-eu".
   Majority rule: a sound counts as correct / wrong only if at least 3 of the 5 experts agree; otherwise "accented".

2. L2-ARCTIC suitcase corpus (same license as L2-ARCTIC): 22 speakers (incl. the 4 Korean) retell a picture story,
   unscripted, 27-235 s each, labelled exactly like the L2-ARCTIC sentences. Too long for the model in one go (and the
   app caps recordings at 15 s), so each story is cut at pauses into pieces of about 6-14 s, using the phoneticians'
   own word times.

Run:  python -m eval.extra_corpora suitcase      -> data/cache/eval_suitcase.csv
      python -m eval.extra_corpora speechocean   -> data/cache/eval_speechocean.csv
      (--limit N = first N recordings, a quick check)
"""
import argparse
import csv
import re
import time
from collections import Counter
from pathlib import Path

from eval.listener import keep_speaker, tagged

ROOT = Path(__file__).resolve().parents[1] / "data"
SO = ROOT / "speechocean762" / "speechocean762"
SUITCASE = ROOT / "l2arctic_suitcase" / "suitcase_corpus"
OUT = {"speechocean": tagged(ROOT / "cache" / "eval_speechocean.csv"),   # own folder per listener
       "suitcase": tagged(ROOT / "cache" / "eval_suitcase.csv")}
KOREAN = {"hjk", "hkk", "ydck", "ykwk"}  # L2-ARCTIC's Korean speakers (lowercase in the suitcase file names)
VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"}
MAJORITY = 3  # of 5 experts


# ---------- 1. speechocean762 ----------
def so_word_labels(word):
    """One word's 5 expert annotations -> L2-ARCTIC-style labels per sound, or None if an annotation doesn't fit."""
    ref = word["ref-phones"].split()
    votes = [Counter() for _ in ref]
    inserted = Counter()  # (after which sound, vowel) -> how many experts heard an extra vowel there
    for ann in word["phones"]:
        j = -1
        heard_here = set()
        for tok in ann.split():
            if tok.startswith("["):
                sym = tok.strip("[]")
                if re.sub(r"\d", "", sym) in VOWELS:
                    heard_here.add((j, sym))
                continue
            j += 1
            if j >= len(ref):
                return None
            votes[j]["wrong" if tok.startswith("(") else "accent" if tok.startswith("{") else "ok"] += 1
        if j != len(ref) - 1:
            return None
        inserted.update(heard_here)
    out = []
    for j, (phone, v) in enumerate(zip(ref, votes)):
        out.append(phone if v["ok"] >= MAJORITY else f"{phone},err,s" if v["wrong"] >= MAJORITY else f"{phone},acc,s")
        extra = [sym for (after, sym), n in inserted.items() if after == j and n >= MAJORITY]
        if extra:
            out.append(f"sil,{extra[0]},a")
    return out


def so_human(human, detail):
    """Rename L2-ARCTIC's catch-all 'other' for speechocean's two special labels."""
    if human == "other" and detail == "sub:ERR":
        return "wrong_any"  # the experts said wrong, but not WHAT was said: not a pair-specific error
    if human == "other" and detail == "sub:ACC":
        return "accented"   # no 3-of-5 majority, or a heavy accent: left out of both rates
    return human


def speechocean_items(limit=None):
    import json
    detail = json.loads((SO / "resource" / "scores-detail.json").read_text())
    ages = {}
    for split in ("train", "test"):
        for line in (SO / split / "spk2age").read_text().split("\n"):
            if line.strip():
                spk, age = line.split()
                ages[spk] = int(age)
    texts, spk_of = {}, {}
    for split in ("train", "test"):
        for line in (SO / split / "text").read_text().split("\n"):
            if line.strip():
                uid, text = line.split(maxsplit=1)
                texts[uid] = text
        for line in (SO / split / "utt2spk").read_text().split("\n"):  # the corpus's own utterance -> speaker map
            if line.strip():
                uid, spk = line.split()
                spk_of[uid] = spk
    n = 0
    for uid in sorted(detail):
        spk = spk_of.get(uid, "")
        labels = []
        for w in detail[uid]["words"]:
            wl = so_word_labels(w)
            if wl is None:
                labels = None
                break
            labels += wl
        wav = SO / "WAVE" / f"SPEAKER{spk.zfill(4)}" / f"{uid}.WAV"
        if labels is None or uid not in texts or not wav.exists():
            continue
        group = "so_adult" if ages.get(spk, 0) >= 18 else "so_child"
        yield group, spk, uid, labels, texts[uid], wav
        n += 1
        if limit and n >= limit:
            return


# ---------- 2. suitcase ----------
INTERVAL = re.compile(r'xmin = ([\d.]+)\s*\n\s*xmax = ([\d.]+)\s*\n\s*text = "([^"]*)"')


def textgrid_tiers(tg):
    """-> {"words": [(start, end, text)], "phones": [...]} from a long-format Praat TextGrid."""
    out = {}
    for name in ("words", "phones"):
        part = tg.split(f'name = "{name}"')[1].split("item [")[0]
        out[name] = [(float(a), float(b), t.strip()) for a, b, t in INTERVAL.findall(part)]
    return out


def suitcase_segments(tg, min_len=6.0, max_len=14.0, min_gap=0.1):
    """Cut a story into pieces: close a piece at a pause once it is at least min_len long, or before it would pass
    max_len. -> [{"start", "end", "text", "labels"}] (labels = the phones tier inside the piece, no silences)."""
    tiers = textgrid_tiers(tg)
    words = [w for w in tiers["words"] if w[2]]
    segs, cur = [], []
    for k, w in enumerate(words):
        if cur and w[1] - cur[0][0] > max_len:
            segs.append(cur)
            cur = []
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        pause = nxt is None or nxt[0] - w[1] >= min_gap
        if pause and w[1] - cur[0][0] >= min_len:
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    out = []
    for seg in segs:
        start, end = seg[0][0], seg[-1][1]
        labels = [t for a, b, t in tiers["phones"] if start <= (a + b) / 2 < end and t not in ("", "sil", "sp")]
        out.append({"start": start, "end": end, "text": " ".join(t for _, _, t in seg), "labels": labels})
    return out


def suitcase_items(limit=None):
    import soundfile as sf
    n = 0
    for tg_path in sorted((SUITCASE / "annotation").glob("*.TextGrid")):
        spk = tg_path.stem.lower()
        audio, sr = sf.read(SUITCASE / "wav" / f"{spk}.wav", dtype="float32")
        group = "suitcase_korean" if spk in KOREAN else "suitcase_others"
        for i, seg in enumerate(suitcase_segments(tg_path.read_text(encoding="utf-8", errors="replace"))):
            if len(seg["text"].split()) < 3:
                continue  # too short to align reliably
            a, b = max(0, int((seg["start"] - 0.1) * sr)), int((seg["end"] + 0.1) * sr)
            yield group, spk.upper(), f"seg{i:02d}", seg["labels"], seg["text"], (audio[a:b], sr)
            n += 1
            if limit and n >= limit:
                return


# ---------- run ----------
def main():
    from eval.l2arctic import run_labelled
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", choices=sorted(OUT))
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    items = speechocean_items(args.limit) if args.corpus == "speechocean" else suitcase_items(args.limit)
    out_path = OUT[args.corpus]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n, start, writer = 0, time.time(), None
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        for group, spk, utt, labels, text, wav in items:
            if not keep_speaker(args.corpus, spk, group == "suitcase_korean"):   # PC_SPEAKERS=heldout
                continue
            try:
                rows, sec = run_labelled(group, spk, utt, labels, text, wav)
            except ValueError as e:  # e.g. a piece too short for its text
                print(f"skip {spk}/{utt}: {e}")
                continue
            for r in rows:
                r["human"] = so_human(r["human"], r["human_detail"])
                r["seconds"] = round(sec, 3)
            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
            writer.writerows(rows)
            n += 1
            if n % 250 == 0:
                print(f"{n} recordings, {time.time() - start:.0f} s", flush=True)
    print(f"done: {n} recordings in {time.time() - start:.0f} s -> {out_path}")


if __name__ == "__main__":
    main()
