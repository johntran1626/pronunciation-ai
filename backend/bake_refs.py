"""Make every pack sentence's native reference clip ahead of time, so the deployed app ships with them.

    python -m backend.bake_refs --dry-run   # how many clips and Azure characters are still missing (no Azure call)
    python -m backend.bake_refs             # make the missing ones in data/tts_cache/ (each is made once, ever)
    python -m backend.bake_refs --list      # file names to ship; fails if anything is missing (used by upload.sh)

Why: the server's daily Azure budget is shared by all visitors. With the pack clips already in the image, every
pack sentence is a cache hit (free, no limit), so pack mode keeps working even on a day someone uses up the budget.
Only Custom mode needs new audio.

Two speeds per sentence (normal and the "Slower" button), plus the word/sound timings of the normal-speed clip
(the detail card and the mouth animation only ask for those). The clips are the same files /tts would make:
same cache folder, same file names, so the server can't tell a baked clip from one it made itself.
"""
import argparse
import sys
import time

from backend import tts
from backend.native import native_timings, timings_path
from backend.packs import _all_packs

SLOW_RATE = -30          # the frontend's "Slower" button (frontend/lib/api.ts SLOW_RATE); a test keeps them equal
RATES = (0, SLOW_RATE)
PAUSE_S = 0.5            # between new clips, to stay under the free tier's requests-per-minute limit
RETRY_WAIT_S = 60        # Azure said "too many requests": wait this long, then try again
MAX_TRIES = 3


class MissingRefs(RuntimeError):
    """Some pack clips haven't been made yet, so the upload would ship an incomplete set."""


def reference_clips():
    """(text, lang, rate) for every sentence in every learner pack, at both speeds. Dev packs are left out."""
    return [(item["text"], pack["lang"], rate)
            for pack in _all_packs().values() if not pack.get("dev_only")
            for item in pack["items"]
            for rate in RATES]


def _files(text, lang, rate, cache_dir):
    """The clip, plus its timings file for the normal-speed clip."""
    wav = tts.clip_path(text, lang, rate=rate, cache_dir=cache_dir)
    return [wav, timings_path(wav)] if rate == 0 else [wav]


def plan(cache_dir=None):
    """What a bake would cost right now, without calling Azure."""
    clips = reference_clips()
    missing = [(t, lang, r) for t, lang, r in clips if not tts.clip_path(t, lang, rate=r, cache_dir=cache_dir).exists()]
    return {"clips": len(clips), "missing_clips": len(missing),
            "missing_chars": sum(len(tts.normalize_text(t)) for t, _, _ in missing)}


def _synthesize(text, lang, rate, cache_dir, fetch, sleep):
    """tts.synthesize, waiting and retrying when Azure answers 429. Any other error stops the bake."""
    for attempt in range(1, MAX_TRIES + 1):
        try:
            return tts.synthesize(text, lang, rate=rate, cache_dir=cache_dir, fetch=fetch)
        except tts.TTSError as e:
            if "HTTP 429" not in str(e) or attempt == MAX_TRIES:
                raise
            sleep(RETRY_WAIT_S)


def bake(cache_dir=None, fetch=None, timings=native_timings, sleep=time.sleep, log=lambda msg: None):
    """Make every missing clip, then make or refresh the normal-speed timings. Returns what it did."""
    report = {"new_clips": 0, "new_chars": 0, "timed": 0}
    clips = reference_clips()
    for n, (text, lang, rate) in enumerate(clips, 1):
        path = tts.clip_path(text, lang, rate=rate, cache_dir=cache_dir)
        if not path.exists():
            _synthesize(text, lang, rate, cache_dir, fetch, sleep)
            report["new_clips"] += 1
            report["new_chars"] += len(tts.normalize_text(text))
            log(f"[{n}/{len(clips)}] made {lang} rate={rate}: {text}")
            sleep(PAUSE_S)
        if rate == 0:
            timings(path, text, lang)       # saved timings are reused; only missing or outdated ones are redone
            report["timed"] += 1
    return report


def ship_list(cache_dir=None):
    """Every file to put in the image, as names inside the cache folder. Raises MissingRefs if any is missing."""
    clips = reference_clips()
    files, missing = [], 0
    for text, lang, rate in clips:
        paths = _files(text, lang, rate, cache_dir)
        missing += not all(p.exists() for p in paths)
        files += [p.name for p in paths]
    if missing:
        raise MissingRefs(f"{missing} of {len(clips)} pack clips are missing; run: python -m backend.bake_refs")
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="count what's missing; no Azure call")
    group.add_argument("--list", action="store_true", help="print the file names to ship; fail if any is missing")
    args = ap.parse_args(argv)

    if args.list:
        try:
            print("\n".join(ship_list()))
        except MissingRefs as e:
            print(e, file=sys.stderr)
            return 1
        return 0

    p = plan()
    print(f"{p['clips']} pack clips; missing {p['missing_clips']} = {p['missing_chars']} Azure characters")
    if args.dry_run:
        return 0
    report = bake(log=print)
    print(f"Done: {report['new_clips']} new clips, {report['new_chars']} characters; timings checked for {report['timed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
