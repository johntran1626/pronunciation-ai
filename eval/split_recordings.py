"""Cut the three private Korean recordings (30 words each, a pause between words) into one clip per word.

Run:  python -m eval.split_recordings
  in:  eval/private/john_ko/way1.m4a, way2.m4a, way3.m4a     (script: eval/recording_script_ko.md)
  out: eval/private/john_ko/clips/way<w>_<nn>.wav  (16 kHz mono) + clips.csv (one row per clip)
Everything stays in eval/private/ (git-ignored). Nothing is uploaded.

How: measure loudness every 10 ms; loud stretches separated by >= 0.4 s of quiet are separate words; anything
shorter than 0.15 s is a click, not a word. Then drop known false starts (DROP) and REFUSE to write anything
unless exactly 30 pieces are left, because one extra or missing piece would shift every label after it.
"""
import csv
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "recording_script_ko.md"
PRIVATE = ROOT / "private" / "john_ko"
SR = 16000
THRESH_DB = -50.0   # the recordings peak near -29 dB and the room is near -79 dB, so -50 sits well between
MIN_GAP = 0.4       # s of quiet that separates two words (the script asks for 2 s; a gap inside 뽀뽀 is ~0.1 s)
MIN_LEN = 0.15      # s; shorter loud bits are clicks (way3 had a 0.09 s one)
PAD = 0.1           # s of quiet kept on each side of a clip so the first and last sounds aren't clipped
# Times (s) inside pieces to throw away. way3: the speaker misread a word and said it again right away (2026-11-13);
# the misreading is the piece at 38.3-39.0 s, just before the correct 다리.
DROP = {"way3": [38.6]}


def script_rows():
    """-> the 30 rows of the word table in recording_script_ko.md, in reading order."""
    rows = []
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[0].isdigit():
            rows.append({"n": int(cells[0]), "word": re.sub(r"\s*\*\(new\)\*", "", cells[1]),
                         "sound": cells[4], "wrong_on_purpose": cells[5]})
    return rows


def script_words():
    return [r["word"] for r in script_rows()]


def load(path):
    """Any audio file -> 16 kHz mono float32 (ffmpeg does the decoding and resampling)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def speech_pieces(x, sr, thresh_db=THRESH_DB, min_gap=MIN_GAP, min_len=MIN_LEN, hop=0.01):
    """-> [(start s, end s), ...] for each loud stretch (a word)."""
    n = int(hop * sr)
    frames = x[: len(x) // n * n].reshape(-1, n)
    loud = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9) > thresh_db
    pieces, start, last = [], None, None
    for i, is_loud in enumerate(loud):
        if not is_loud:
            continue
        if start is not None and (i - last - 1) * hop >= min_gap:   # a real pause just ended: close the word
            pieces.append((start * hop, (last + 1) * hop))
            start = None
        start = i if start is None else start
        last = i
    if start is not None:
        pieces.append((start * hop, (last + 1) * hop))
    return [(round(s, 2), round(e, 2)) for s, e in pieces if e - s >= min_len]


def select(pieces, expected, drop_at=()):
    """Remove the pieces containing each drop time, then insist on exactly `expected` pieces."""
    for t in drop_at:
        hit = [p for p in pieces if p[0] <= t <= p[1]]
        if not hit:
            raise ValueError(f"no piece at {t} s to drop")
        pieces = [p for p in pieces if p not in hit]
    if len(pieces) != expected:
        raise ValueError(f"expected {expected} pieces, found {len(pieces)}")
    return pieces


def _write_wav(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def main():
    rows = script_rows()
    out_dir = PRIVATE / "clips"
    out_dir.mkdir(exist_ok=True)
    table = []
    for way in ("way1", "way2", "way3"):
        x = load(PRIVATE / f"{way}.m4a")
        pieces = select(speech_pieces(x, SR), expected=len(rows), drop_at=DROP.get(way, []))
        for row, (s, e) in zip(rows, pieces):
            name = f"{way}_{row['n']:02d}.wav"
            _write_wav(out_dir / name, x[int(max(0, s - PAD) * SR): int((e + PAD) * SR)])
            table.append({"clip": name, "way": way, "n": row["n"], "word": row["word"], "sound": row["sound"],
                          "start": s, "end": e,
                          # way2 = the mistake was made on purpose; ways 1 and 3 wait for a native speaker's ear
                          "label": "error_by_intent" if way == "way2" else "attempt"})
        print(f"{way}: {len(pieces)} clips")
    with (PRIVATE / "clips.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)
    print(f"-> {out_dir} + clips.csv ({len(table)} rows)")


if __name__ == "__main__":
    main()
