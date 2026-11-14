"""Speech Accent Archive (GMU), Korean speakers -> one table of transcriptions + speaker details.

Source: https://accent.gmu.edu (Weinberger & Kelley), CC BY-NC-SA 4.0. Every speaker reads the same paragraph
("Please call Stella..."); a phonetician wrote a narrow IPA transcription of it. We use it as independent human
labels for R/L (and later F/P, V/B, TH). Only aggregate numbers are published; audio and pages stay in data/
(git-ignored).

Run:  python -m eval.saa_fetch [--audio-from DIR]
  1. downloads each speaker page once (cached in data/saa/pages/, 1 request per second, polite)
  2. copies the MP3s from DIR (downloaded by hand) into data/saa/audio/ (else fetches them)
  3. parses transcription + biography -> data/saa/speakers.csv
"""
import argparse
import csv
import html
import re
import shutil
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "saa"
PAGES, AUDIO, TABLE = ROOT / "pages", ROOT / "audio", ROOT / "speakers.csv"
SITE = "https://accent.gmu.edu"
N_KOREAN = 99  # the site's Korean list had exactly 99 speakers (2026-11-13)
BIO_FIELDS = ["birth place", "native language", "other language(s)", "age, sex", "age of english onset",
              "english learning method", "english residence", "length of english residence"]
HEADERS = {"User-Agent": "pronunciation-coach-eval/0.1 (research; one-time download)"}


def fetch(url, dest):
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
        dest.write_bytes(r.read())
    return True


def page_text(raw):
    """HTML -> plain lines (tags dropped, entities decoded)."""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", text))
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def parse(raw):
    """-> dict with the transcription (text between [ ]) and the biography fields; missing ones are ''."""
    lines = page_text(raw)
    out = {"transcription": ""}
    m = re.search(r"\[([^\[\]]{20,})\]", "\n".join(lines))  # the IPA transcription is the long [...] block
    if m:
        out["transcription"] = " ".join(m.group(1).split())
    for f in BIO_FIELDS:
        out[f] = lines[lines.index(f) + 1] if f in lines and lines.index(f) + 1 < len(lines) else ""
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-from", type=Path, help="folder with koreanN.mp3 already downloaded")
    args = ap.parse_args()
    rows = []
    for i in range(1, N_KOREAN + 1):
        sid = f"korean{i}"
        if fetch(f"{SITE}/samples/{sid}/", PAGES / f"{sid}.html"):
            time.sleep(1.0)
        mp3 = AUDIO / f"{sid}.mp3"
        if not mp3.exists():
            src = args.audio_from / f"{sid}.mp3" if args.audio_from else None
            if src and src.exists():
                mp3.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, mp3)
            elif fetch(f"{SITE}/audio/{sid}.mp3", mp3):
                time.sleep(1.0)
        rows.append({"speaker": sid, **parse((PAGES / f"{sid}.html").read_text(encoding="utf-8"))})
    with TABLE.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["speaker", "transcription", *BIO_FIELDS])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} speakers -> {TABLE}")


if __name__ == "__main__":
    main()
