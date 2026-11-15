"""Native reference audio: Azure text-to-speech, saved to disk so each clip is made (and paid for) once.

    from backend.tts import synthesize
    path = synthesize("같이 가요.", "ko")             # woman's voice, normal speed -> data/tts_cache/<hash>.wav
    path = synthesize("Very light.", "en", rate=-30) # 30% slower, a separate cached file
    path = synthesize("I want 떡볶이.", "mix")        # English + Korean: one multilingual voice, <lang> per run

Azure is called over plain HTTPS with Python's built-in urllib (no new dependency). The key and region come
from environment variables, read from the git-ignored .env file if they aren't set already. The key is sent
only in a request header and is never printed or put in an error message.
"""
import hashlib
import os
import re
import tempfile
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from backend.mixed_text import LANG_TAGS, edges, split_runs

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "tts_cache"          # git-ignored (data/)
ENV_FILE = ROOT / ".env"

# The woman's voice by default, the man's kept as an option.
# "mix" (English + Korean in one sentence): a multilingual voice that can say both, told which language each part
# is in by an SSML <lang> tag. Only the woman's voice so far (the one picked after listening to sample clips).
VOICES = {
    "ko": {"female": "ko-KR-SunHiNeural", "male": "ko-KR-InJoonNeural"},
    "en": {"female": "en-US-AvaNeural", "male": "en-US-AndrewNeural"},
    "mix": {"female": "en-US-AvaMultilingualNeural"},
}
OUTPUT_FORMAT = "riff-24khz-16bit-mono-pcm"      # a plain WAV; our aligner resamples to 16 kHz itself
MAX_CHARS = 200                                   # Custom mode length limit (keeps clips short and costs tiny)
MIN_RATE, MAX_RATE = -50, 0                       # percent speed change: slower only, at most half speed
TIMEOUT_S = 30


class TTSError(RuntimeError):
    """Azure couldn't make the audio (no key, network error, bad reply). Safe to show: never holds the key."""


def voice_name(lang, voice="female"):
    """'ko' + 'female' -> 'ko-KR-SunHiNeural'. Refuses anything not in VOICES."""
    try:
        return VOICES[lang][voice]
    except KeyError:
        raise ValueError(f"No voice for lang={lang!r}, voice={voice!r}") from None


def normalize_text(text):
    """The same sentence typed slightly differently must hit the same cache file:
    NFC joins Korean jamo into syllable blocks (two Unicode spellings of 가요 become one); spaces are collapsed."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def build_ssml(text, voice, rate, lang=None):
    """SSML = the small markup Azure reads: which voice, which language, how fast.
    escape() turns & < > into &amp; &lt; &gt; so typed text can't break the markup.
    lang="mix": every language run gets its own <lang xml:lang="..."> tag (with the speed inside it), and the
    spaces between runs stay exactly as typed ("Ben이" must not become "Ben 이")."""
    voice_lang = "-".join(voice.split("-")[:2])                 # 'ko-KR-SunHiNeural' -> 'ko-KR'
    if lang == "mix":
        body = ""
        for run_lang, run in split_runs(text):
            lead, core, tail = edges(run)
            body += (f'{lead}<lang xml:lang="{LANG_TAGS[run_lang]}"><prosody rate="{rate}%">{escape(core)}'
                     f'</prosody></lang>{tail}')
    else:
        body = f'<prosody rate="{rate}%">{escape(text)}</prosody>'
    return f'<speak version="1.0" xml:lang="{voice_lang}"><voice name={quoteattr(voice)}>{body}</voice></speak>'


def cache_key(text, voice, rate):
    """Fingerprint of everything that changes the audio. Same inputs -> same file name; any change -> new file."""
    recipe = "|".join([voice, str(rate), OUTPUT_FORMAT, normalize_text(text)])
    return hashlib.sha256(recipe.encode("utf-8")).hexdigest()[:32]


def load_env(path=None):
    """Read KEY=value lines from .env into os.environ, without overriding anything already set.
    (A 10-line reader instead of adding python-dotenv.)"""
    path = Path(path) if path else ENV_FILE
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def azure_fetch(ssml, urlopen=urllib.request.urlopen):
    """Send SSML to Azure, return the WAV bytes. `urlopen` is swappable so tests never touch the network."""
    load_env()
    key = os.environ.get("AZURE_SPEECH_KEY", "")
    region = os.environ.get("AZURE_SPEECH_REGION", "")
    if not key or key == "paste-key-1-here":
        raise TTSError("AZURE_SPEECH_KEY is not set (put it in .env)")
    if not region:
        raise TTSError("AZURE_SPEECH_REGION is not set (put it in .env, e.g. eastus)")
    req = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml.encode("utf-8"),
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
            "User-Agent": "pronunciation-coach-tts",
        },
    )
    try:
        with urlopen(req, timeout=TIMEOUT_S) as reply:
            return reply.read()
    except urllib.error.HTTPError as e:            # Azure answered with an error code (401 bad key, 429 quota...)
        raise TTSError(f"Azure TTS failed: HTTP {e.code} {e.reason}") from None
    except (urllib.error.URLError, TimeoutError) as e:   # no answer at all (offline, DNS, timeout)
        raise TTSError(f"Azure TTS unreachable: {getattr(e, 'reason', e)}") from None


def clip_path(text, lang, voice="female", rate=0, cache_dir=None):
    """Where the clip for these inputs lives (or will live) in the cache. Checks the inputs; never calls Azure.
    The /tts endpoint uses it to tell a free cache hit from a paid new clip before deciding on rate limits."""
    clean = normalize_text(text)
    if not clean:
        raise ValueError("Text is empty")
    if len(clean) > MAX_CHARS:
        raise ValueError(f"Text is {len(clean)} characters; the limit is {MAX_CHARS}")
    if not (MIN_RATE <= rate <= MAX_RATE):
        raise ValueError(f"rate must be between {MIN_RATE} and {MAX_RATE} percent, got {rate}")
    name = voice_name(lang, voice)
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    return cache_dir / f"{cache_key(clean, name, rate)}.wav"


def synthesize(text, lang, voice="female", rate=0, cache_dir=None, fetch=None):
    """Return the path of a WAV of `text` said by a native voice. Made once, then read from the cache.

    Checks everything BEFORE calling Azure (empty/too long text, unknown voice, bad rate), and writes the file
    atomically (temp file, then rename) so a failed or interrupted call never leaves a broken cache file."""
    path = clip_path(text, lang, voice, rate, cache_dir)
    if path.exists():
        return path                                             # cache hit: no Azure call, no cost
    cache_dir = path.parent
    clean, name = normalize_text(text), voice_name(lang, voice)

    audio = (fetch or azure_fetch)(build_ssml(clean, name, rate, lang))
    if not audio.startswith(b"RIFF"):                           # an error page or empty reply is not audio
        raise TTSError("Azure TTS reply was not a WAV file")

    cache_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=cache_dir, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        os.replace(tmp, path)                                   # rename is all-or-nothing on the same disk
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
