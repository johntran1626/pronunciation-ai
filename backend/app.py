"""FastAPI app: the web entry point of the backend .

Run the server:  uvicorn backend.app:app --reload     then open http://127.0.0.1:8000/docs
"""
import io
import json
import os
from pathlib import Path
from typing import Literal

import soundfile as sf
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from backend.align import align, emissions
from backend.compare import attach_heard
from backend.custom import custom_text
from backend import native, translate, tts
from backend.g2p import expected_phonemes
from backend.limits import TTSLimiter
from backend.match import active_checks, finalize, load_match_thresholds, mark_unchecked, sentence_check
from backend.packs import get_pack, list_packs
from backend.recognize import recognize
from backend.scoring import load_thresholds, score_words
from backend.text_map import attach_display

MAX_SECONDS = 15.0             # hard limit per recording (cost + abuse)
MAX_BYTES = 10 * 1024 * 1024   # 10 MB: stops huge uploads before we try to decode them

app = FastAPI(title="Pronunciation coach")

# CORS: which websites' pages may READ our replies in a browser. An explicit list, not "*",
# so a random site can't use our backend from its own page.
LOCAL_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def allowed_origins(setting: str | None) -> list[str]:
    """The local dev origins plus the comma-separated FRONTEND_ORIGINS setting (the deployed frontend's URL).

    Set on the host, so a new frontend URL is a settings change, not a code change. "*" is refused.
    """
    extra = [o.strip().rstrip("/") for o in (setting or "").split(",") if o.strip()]
    if "*" in extra:
        raise ValueError("FRONTEND_ORIGINS must list exact sites; '*' would let any website read our replies")
    return LOCAL_ORIGINS + [o for o in extra if o not in LOCAL_ORIGINS]


ALLOWED_ORIGINS = allowed_origins(os.environ.get("FRONTEND_ORIGINS"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],   # all the app uses: GET (/health, /packs, /tts...) and POST /analyze
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Tiny 'are you alive?' check. Hosting services call this to know the server is up."""
    return {"ok": True}


@app.get("/packs")
def packs(lang: Literal["ko", "en"] | None = None):
    """Pack summaries for the picker (no sentences). ?lang=ko shows only packs for learning Korean."""
    return list_packs(lang)


@app.get("/packs/{pack_id}")
def pack(pack_id: str):
    """One pack with its sentences."""
    found = get_pack(pack_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"No pack called '{pack_id}'")
    return found


ARTICULATION = Path(__file__).resolve().parent.parent / "content" / "articulation.json"


@app.get("/articulation")
def articulation():
    """How each sound is made (content/articulation.json), for the mouth diagrams."""
    return json.loads(ARTICULATION.read_text(encoding="utf-8"))


TIPS = Path(__file__).resolve().parent.parent / "content" / "tips.json"


@app.get("/tips")
def tips():
    """Hand-written fix-it tips per confusion pair (content/tips.json), for the detail card."""
    return json.loads(TIPS.read_text(encoding="utf-8"))


# ---------- /tts: native reference audio ----------
# The browser asks US for the clip; only this server knows the Azure key. Cached clips are served straight from
# disk; a new clip costs Azure characters, so only new clips go through the rate limits (backend/limits.py).
tts_limiter = TTSLimiter()


async def _get_clip(request, text, lang, voice, rate):
    """The cached clip's path (making it on a miss). Returns (path, was_cached). Shared by /tts and /tts/timings."""
    try:
        path = tts.clip_path(text, lang, voice, rate)      # checks the text; no network
    except ValueError as e:
        raise HTTPException(400, str(e))
    if path.exists():
        return path, True
    # TODO (deploy): behind a host's proxy, request.client is the proxy; we'll read X-Forwarded-For there instead.
    client = request.client.host if request.client else "unknown"
    n_chars = len(tts.normalize_text(text))
    ok, wait = tts_limiter.allow(client, n_chars)
    if not ok:
        raise HTTPException(429, _limit_message(wait, n_chars), headers={"Retry-After": str(wait)})
    try:
        return await run_in_threadpool(tts.synthesize, text, lang, voice, rate), False  # ~0.7 s network wait
    except tts.TTSError as e:                              # message never holds the key (see tts.py)
        raise HTTPException(503, str(e))


@app.get("/custom")
def custom(text: str = Query(..., max_length=1000), lang: Literal["ko", "en"] = Query(...)):
    """A typed Custom-mode sentence -> the words a native would SAY (커피 2잔 -> 커피 두 잔, Dr. -> Doctor).
    The frontend shows `text` and uses it for /tts and /analyze, so all three agree. 400 = the reason, for the user."""
    try:
        said = custom_text(text, lang)
        expected_phonemes(said, lang)           # must give at least one word we can score
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"text": said, "typed": text, "changed": said != tts.normalize_text(text)}


# ---------- /translate: what a Custom sentence means ----------
# Same pattern as /tts: cached answers are free; only NEW translations count against the limits.
translate_limiter = TTSLimiter(per_client=10, window_s=60, daily_chars=8_000)


@app.get("/translate")
async def translate_sentence(request: Request, text: str = Query(..., max_length=1000),
                             lang: Literal["ko", "en"] = Query(...)):
    """`lang` = the language of `text`. English -> Korean, Korean -> English. 400 bad text, 429 limit, 503 API trouble."""
    try:
        hit = translate.cached(text, lang)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if hit is not None:
        return {**hit, "cached": True}
    client = request.client.host if request.client else "unknown"
    ok, wait = translate_limiter.allow(client, len(tts.normalize_text(text)))
    if not ok:
        raise HTTPException(429, "Too many new translations right now. Try again a little later.",
                            headers={"Retry-After": str(wait)})
    try:
        return await run_in_threadpool(translate.translate, text, lang)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except translate.TranslateError as e:
        raise HTTPException(503, str(e))


@app.get("/tts")
async def tts_clip(request: Request,
                   text: str = Query(..., max_length=1000),
                   lang: Literal["ko", "en"] = Query(...),
                   voice: Literal["female", "male"] = "female",
                   rate: int = Query(0, ge=tts.MIN_RATE, le=tts.MAX_RATE)):
    """A WAV of `text` said by a native voice. rate=-30 = 30% slower. 429 when a limit is hit, 503 if Azure fails."""
    path, hit = await _get_clip(request, text, lang, voice, rate)
    return FileResponse(path, media_type="audio/wav",
                        headers={"X-TTS-Cache": "hit" if hit else "miss",
                                 "Cache-Control": "public, max-age=86400"})   # the browser keeps it a day


@app.get("/tts/timings")
async def tts_timings(request: Request,
                      text: str = Query(..., max_length=1000),
                      lang: Literal["ko", "en"] = Query(...),
                      voice: Literal["female", "male"] = "female",
                      rate: int = Query(0, ge=tts.MIN_RATE, le=tts.MAX_RATE)):
    """Start/end of every word and sound in the SAME clip /tts serves (same query = same WAV), so the
    detail card can play the native version of one word or sound. Aligned once, then read from the saved JSON."""
    try:
        expected_phonemes(tts.normalize_text(text), lang)   # no pronounceable words -> 400 BEFORE paying for a clip
    except ValueError as e:
        raise HTTPException(400, str(e))
    path, _ = await _get_clip(request, text, lang, voice, rate)
    try:
        return await run_in_threadpool(native.native_timings, path, text, lang)   # ~1 s the first time, then ~1 ms
    except ValueError as e:
        raise HTTPException(400, str(e))


def _limit_message(wait, n_chars):
    if tts_limiter.used_today() + n_chars > tts_limiter.daily_chars:
        return "The daily limit for new audio is used up. Sentences already played still work; try again tomorrow."
    return f"Too many new audio clips at once. Try again in {wait} s."


@app.post("/analyze")
async def analyze(audio: UploadFile = File(...),
                  text: str = Form(...),
                  lang: Literal["ko", "en"] = Form(...)):
    """Recording + target sentence in, results out.
    Steps 9-22: input checks, expected phonemes + times, what was heard, the red/green verdict, and
    `display` per word (the pieces of the written word to paint green/red)."""
    text = text.strip()
    if not text:
        raise HTTPException(400, "text is empty")
    data = await audio.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(400, f"file is larger than {MAX_BYTES // (1024 * 1024)} MB")
    try:
        samples, sr = sf.read(io.BytesIO(data), dtype="float32")
    except Exception:  # soundfile raises different errors for different broken files
        raise HTTPException(400, "could not read the audio (send WAV or FLAC)")
    duration = len(samples) / sr
    if duration > MAX_SECONDS:
        raise HTTPException(400, f"recording is {duration:.1f} s; the limit is {MAX_SECONDS:.0f} s")
    try:
        # The model takes ~0.1-3 s. Running it in a worker thread keeps the server answering other requests.
        words, heard, extra_at_start, matched, reason, checks = await run_in_threadpool(
            _run_pipeline, samples, sr, text, lang)
    except ValueError as e:  # no words in the text, or the recording is too short for the sentence
        raise HTTPException(400, str(e))
    return {"text": text, "lang": lang, "duration_s": round(duration, 3),
            "matched": matched, "reason": reason, "checks": checks,
            "words": words, "heard": heard, "extra_at_start": extra_at_start}


def _run_pipeline(samples, sr, text, lang):
    expected = expected_phonemes(text, lang)  # 1. what should be said
    em = emissions(samples, sr, lang)         #    the model runs ONCE (this language's listener)...
    words = align(em, expected, lang)         # 2. ...where each expected sound is
    heard = recognize(em)                     # 3. ...and what was actually heard
    words, extra_at_start = attach_heard(words, heard, lang)  # 4. line them up: what was heard in each place
    sound_t, match_t = load_thresholds(em.model), load_match_thresholds(em.model)  # tuned for THAT listener
    rules = match_t.get(lang, {}).get("sentence", {"enabled": False})
    matched, reason = sentence_check(words, len(heard), rules)  # 5. did they say THIS sentence?
    if matched:
        words = score_words(em, words, lang, thresholds=sound_t, audio=samples, sr=sr)  # 6. sound checks
        words = finalize(words, lang, sound_t, match_t)  # 7. word heard? + honest green / unchecked
    else:
        words = mark_unchecked(words)         #    no verdict on a recording that isn't this sentence
    words = attach_display(words, lang)       # 8. which letters / syllable blocks to paint
    return words, heard, extra_at_start, matched, reason, active_checks(lang, sound_t, match_t)
