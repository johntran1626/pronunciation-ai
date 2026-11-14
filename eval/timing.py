"""Processing time per sentence: the app's whole analysis, timed on real learner recordings.

    python -m eval.timing            # about 5 minutes on a laptop CPU; writes results/timing.json
    python -m eval.timing --live https://johntran1626-pronunciation-ai.hf.space   # ~32 min; results/timing_live.json

What is timed: backend.app._run_pipeline, the exact function /analyze calls once the upload is read
(expected sounds, the listener, alignment, recognition, the sentence and word checks, the sound checks,
the text mapping). Not timed: the network, reading the upload, and loading the model, which happens once
when the server starts (one warm-up sentence absorbs it and is not counted).
Data: every reading by L2-ARCTIC's 4 Korean speakers, English, on the listener the app runs for English.

--live times the same readings on the deployed server instead: the whole round trip of POST /analyze (upload,
any queue, the analysis, the answer), which is what a visitor waits for after pressing Stop. Each reading is sent
as 16 kHz mono 16-bit WAV, the file the browser uploads. Requests are spaced to stay under the server's
per-visitor limit; a 429 is waited out and that try is not timed. /health round trips are timed too, so the
share that is only the network can be read off.
"""
import argparse
import io
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path

import httpx
import soundfile as sf
import torch
import torchaudio

from backend.app import ANALYZE_PER_MINUTE, _run_pipeline
from backend.listener import listener_id, live_listener
from eval.l2arctic import KOREAN, korean_utterances

OUT = Path("results/timing.json")
LIVE_OUT = Path("results/timing_live.json")
LANG = "en"
UPLOAD_RATE = 16000                       # frontend/lib/recorder.ts TARGET_RATE
GAP_S = 60 / ANALYZE_PER_MINUTE + 0.2     # 3.2 s between request starts: under 20 a minute with room to spare
HEALTH_CHECKS = 20


def summarize(values):
    """n, median, the slowest-5% line (same rule as eval/run.py, so old and new numbers compare) and max."""
    if not values:
        raise ValueError("no timings to summarize")
    v = sorted(values)
    return {"n": len(v), "median": round(statistics.median(v), 3),
            "p95": round(v[int(0.95 * (len(v) - 1))], 3), "max": round(v[-1], 3)}


def machine():
    """'Apple M3 Pro, 12 CPU cores': the time only means something next to the hardware it ran on."""
    try:
        chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        chip = platform.processor() or platform.machine()
    return f"{chip}, {torch.get_num_threads()} CPU threads"


def _load(wav):
    audio, sr = sf.read(wav, dtype="float32")
    return (audio.mean(axis=1) if audio.ndim > 1 else audio), sr


# ---------- --live: the deployed server ----------
def wav16k_bytes(audio, sr):
    """The upload the browser makes: resampled to 16 kHz, mono, 16-bit WAV."""
    x = torch.from_numpy(audio)
    if sr != UPLOAD_RATE:
        x = torchaudio.functional.resample(x, sr, UPLOAD_RATE)
    buf = io.BytesIO()
    sf.write(buf, x.numpy(), UPLOAD_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class Pacer:
    """Keeps request starts at least gap_s apart, so a long run never trips the per-visitor limit."""
    def __init__(self, gap_s=GAP_S, clock=time.monotonic, sleep=time.sleep):
        self.gap_s, self.clock, self.sleep, self.last = gap_s, clock, sleep, None

    def wait(self):
        if self.last is not None:
            left = self.gap_s - (self.clock() - self.last)
            if left > 0:
                self.sleep(left)
        self.last = self.clock()


def post_timed(client, wav, text, lang, sleep=time.sleep):
    """Seconds from sending the reading to having the whole answer; None if the app refuses it (400).
    A 429 is waited out (Retry-After) and retried; only the answered try is timed. Anything else stops the run."""
    while True:
        t0 = time.perf_counter()
        r = client.post("/analyze", files={"audio": ("recording.wav", wav, "audio/wav")},
                        data={"text": text, "lang": lang})
        secs = time.perf_counter() - t0
        if r.status_code == 429:
            sleep(int(r.headers.get("Retry-After", "60")))
            continue
        if r.status_code == 400:
            return None
        if r.status_code != 200:
            raise RuntimeError(f"/analyze answered {r.status_code}: {r.text[:200]}")
        return secs


def space_hardware(url):
    """'cpu-basic' etc. from the Hugging Face API, for a *.hf.space URL; None if it can't be read."""
    host = httpx.URL(url).host
    if not host.endswith(".hf.space"):
        return None
    owner, _, name = host.removesuffix(".hf.space").partition("-")
    try:
        r = httpx.get(f"https://huggingface.co/api/spaces/{owner}/{name}/runtime", timeout=30)
        return r.json()["hardware"]["current"]
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def main_live(url, limit=None):
    readings = list(korean_utterances(None))[:limit]
    hw = space_hardware(url)
    pacer = Pacer()
    with httpx.Client(base_url=url, timeout=120) as client:
        health = []
        for _ in range(HEALTH_CHECKS):            # also wakes the Space if it was asleep
            t0 = time.perf_counter()
            client.get("/health").raise_for_status()
            health.append(time.perf_counter() - t0)
        first = readings[0]
        pacer.wait()
        post_timed(client, wav16k_bytes(*_load(first[5])), first[4], LANG)   # warm-up, not counted

        secs, audio_secs = [], []
        for i, (_, spk, utt, _, text, wav) in enumerate(readings, 1):
            audio, sr = _load(wav)
            pacer.wait()
            t = post_timed(client, wav16k_bytes(audio, sr), text, LANG)
            if t is None:
                print(f"skip {spk}/{utt}: the app refused it (400)")
                continue
            secs.append(t)
            audio_secs.append(len(audio) / sr)
            if i % 25 == 0:
                print(f"{i}/{len(readings)}  median so far {statistics.median(secs):.3f} s", flush=True)

    result = {
        "listener": listener_id(live_listener(LANG)), "lang": LANG, "device": "cpu",
        "machine": f"Hugging Face Space, {hw} hardware" if hw else url, "url": url,
        "data": f"L2-ARCTIC, every reading by its {len(KOREAN)} Korean speakers ({', '.join(KOREAN)})",
        "timed": "round trip of POST /analyze from a laptop: upload, queue, analysis and answer",
        "seconds_per_sentence": summarize(secs),
        "audio_seconds": summarize(audio_secs),
        "health_round_trip": summarize(health),
        "skipped": len(readings) - len(secs),
        "measured": time.strftime("%Y-%m-%d"),
    }
    out = LIVE_OUT if limit is None else LIVE_OUT.with_name("timing_live_trial.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    s = result["seconds_per_sentence"]
    print(f"{result['machine']}: median {s['median']} s, p95 {s['p95']} s, max {s['max']} s (n={s['n']}); "
          f"/health median {result['health_round_trip']['median']} s; wrote {out}")


def main():
    readings = list(korean_utterances(None))
    first = readings[0]
    _run_pipeline(*_load(first[5]), first[4], LANG)   # warm-up: loads the model, not counted

    secs, audio_secs = [], []
    for i, (_, spk, utt, _, text, wav) in enumerate(readings, 1):
        audio, sr = _load(wav)
        t0 = time.perf_counter()
        try:
            _run_pipeline(audio, sr, text, LANG)
        except ValueError as e:   # the app answers 400 for these; nothing to time
            print(f"skip {spk}/{utt}: {e}")
            continue
        secs.append(time.perf_counter() - t0)
        audio_secs.append(len(audio) / sr)
        if i % 100 == 0:
            print(f"{i}/{len(readings)}  median so far {statistics.median(secs):.3f} s")

    result = {
        "listener": listener_id(live_listener(LANG)), "lang": LANG, "device": "cpu", "machine": machine(),
        "data": f"L2-ARCTIC, every reading by its {len(KOREAN)} Korean speakers ({', '.join(KOREAN)})",
        "timed": "backend.app._run_pipeline (the whole /analyze analysis), model already loaded",
        "seconds_per_sentence": summarize(secs),
        "audio_seconds": summarize(audio_secs),
        "skipped": len(readings) - len(secs),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    s = result["seconds_per_sentence"]
    print(f"{result['listener']} on {result['machine']}: median {s['median']} s, p95 {s['p95']} s, "
          f"max {s['max']} s (n={s['n']}); wrote {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", metavar="URL", help="time the deployed server instead of this machine")
    ap.add_argument("--limit", type=int, help="with --live: only the first N readings (a trial run)")
    args = ap.parse_args()
    main_live(args.live.rstrip("/"), args.limit) if args.live else main()
