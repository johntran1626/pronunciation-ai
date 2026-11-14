"""The WHOLE Speech Accent Archive (all native languages) from its OSF release, for more labelled errors.

Source: OSF project yh23d (Weinberger & Kelley, Speech Accent Archive, CC BY-NC-SA 4.0). Folders: transcription_texts
(one IPA transcription of the "Please call Stella" paragraph per speaker; 1,266 of 3,016 speakers have one),
mp3_files, and speaker_information.xlsx. We download only speakers WITH a transcription (no label = no use).

Run:  python -m eval.saa_osf      -> data/saa_all/{texts,audio}/ + speakers.csv (+ speaker_information.xlsx)
Cached: re-running skips files already on disk. Polite: at most WORKERS requests at once, a short pause after each.
"""
import csv
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "saa_all"
API = "https://api.osf.io/v2/nodes/yh23d/files/osfstorage/"
FOLDERS = {"texts": "6a7dfe089137a29d1100226a", "audio": "698a8f0a9a43a780c6c72b76"}  # transcription_texts, mp3_files
INFO_URL = "https://osf.io/download/9tupa/"  # speaker_information.xlsx
HEADERS = {"User-Agent": "pronunciation-coach-eval/0.1 (research; one-time download)"}
PAUSE = 0.3
WORKERS = 2  # files at the same time. 4 hit OSF's rate limit (HTTP 429, 2026-11-13); 1 took ~2.5 h


def _get(url):
    """Fetch with retries. OSF answers 429 (Too Many Requests) when we go too fast: then wait as long as it asks
    (Retry-After), else 60 s, 120 s, ... Raises after the last try; fetch() then skips the file (a re-run gets it)."""
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as r:
                return r.read()
        except Exception as e:
            if attempt == 7:
                raise
            wait = 5 * (attempt + 1)
            if getattr(e, "code", None) == 429:
                wait = int(e.headers.get("Retry-After") or 60 * (attempt + 1))
            print(f"retry in {wait} s ({e})", flush=True)
            time.sleep(wait)


def listing(folder_id):
    """-> {file name: download url} for every file in an OSF folder (follows the pages)."""
    out, url = {}, f"{API}{folder_id}/?page%5Bsize%5D=100"
    while url:
        d = json.loads(_get(url))
        for f in d["data"]:
            out[f["attributes"]["name"]] = f["links"]["download"]
        url = d["links"].get("next")
        time.sleep(PAUSE)
    return out


def fetch(url, dest):
    """-> True if the file is on disk afterwards. A file that keeps failing is skipped, not fatal."""
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.write_bytes(_get(url))
    except Exception as e:
        print(f"SKIPPED {dest.name}: {e}", flush=True)
        return False
    time.sleep(PAUSE)
    return True


def main():
    texts, audio = listing(FOLDERS["texts"]), listing(FOLDERS["audio"])
    print(f"{len(texts)} transcriptions, {len(audio)} mp3 files listed", flush=True)
    fetch(INFO_URL, ROOT / "speaker_information.xlsx")
    jobs = [(url, ROOT / "texts" / name) for name, url in texts.items()]
    jobs += [(audio[f"{n.rsplit('.', 1)[0]}.mp3"], ROOT / "audio" / f"{n.rsplit('.', 1)[0]}.mp3")
             for n in texts if f"{n.rsplit('.', 1)[0]}.mp3" in audio]
    from concurrent.futures import ThreadPoolExecutor
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for _ in pool.map(lambda job: fetch(*job), jobs):
            done += 1
            if done % 25 == 0:
                print(f"{done}/{len(jobs)} files ({time.strftime('%H:%M')})", flush=True)
    rows, missing = [], 0
    for name in sorted(texts):
        sid = name.rsplit(".", 1)[0]
        if f"{sid}.mp3" not in audio or not (ROOT / "audio" / f"{sid}.mp3").exists() \
                or not (ROOT / "texts" / name).exists():
            missing += 1
            continue
        text = (ROOT / "texts" / name).read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\[([^\[\]]{20,})\]", text)
        rows.append({"speaker": sid, "language": re.sub(r"\d+$", "", sid),
                     "transcription": " ".join((m.group(1) if m else text).split())})
    with (ROOT / "speakers.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["speaker", "language", "transcription"])
        w.writeheader()
        w.writerows(rows)
    print(f"done: {len(rows)} speakers with transcription + audio ({missing} transcriptions without an mp3) -> {ROOT}")


if __name__ == "__main__":
    main()
