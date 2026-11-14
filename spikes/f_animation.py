"""Feasibility check: can our aligner + articulation.json drive a native side-view mouth animation?
Throwaway feasibility script.

    .venv/bin/python spikes/f_animation.py     # ~10 s; writes frontend/public/spike/*.json + *.wav (git-ignored)
    then open http://localhost:3000/dev/animate (frontend dev server)

For 3 NATIVE recordings (2 CMU ARCTIC English, 1 Zeroth Korean): expected sounds (g2p) -> forced alignment (start,
end per sound) -> each sound's articulation.json entry. The browser (frontend/lib/animate.ts) blends between those
poses in time. No TTS yet: this tests the animation, not the voice. Prints any sound missing from the table.
"""
import io
import json
import shutil
import sys
from pathlib import Path

import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.align import align, emissions  # noqa: E402
from backend.g2p import expected_phonemes  # noqa: E402

OUT = ROOT / "frontend/public/spike"
TABLE = json.loads((ROOT / "content/articulation.json").read_text())["sounds"]
ARCTIC = ROOT / "data/cmu_arctic"


def arctic_text(spk, utt):
    for line in (ARCTIC / f"cmu_us_{spk}_arctic/etc/txt.done.data").read_text().splitlines():
        if line.startswith(f"( {utt} "):
            return line.split('"')[1]
    raise KeyError(utt)


def zeroth(uid):
    import pyarrow.parquet as pq
    for r in pq.read_table(ROOT / "data/zeroth/data/test-00000-of-00001.parquet").to_pylist():
        if r["id"] == uid:
            audio, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
            return r["text"], audio, sr
    raise KeyError(uid)


def build(name, lang, text, audio, sr, source):
    words = align(emissions(audio, sr), expected_phonemes(text, lang), lang)
    sounds, missing = [], []
    for w in words:
        for p in w["phonemes"]:
            entry = TABLE[lang].get(p["ipa"])
            if entry is None:
                missing.append(p["ipa"])
            sounds.append({"ipa": p["ipa"], "start": p["start"], "end": p["end"], "entry": entry})
    sf.write(OUT / f"{name}.wav", audio, sr)
    data = {"name": name, "lang": lang, "text": text, "source": source, "audio": f"/spike/{name}.wav",
            "duration": round(len(audio) / sr, 3),
            "words": [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in words], "sounds": sounds}
    (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"{name}: {len(sounds)} sounds, {len(words)} words, {data['duration']} s; missing from table: {missing or 'none'}")
    return name


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    names = []
    for spk, utt in (("slt", "arctic_a0001"), ("bdl", "arctic_a0004")):
        audio, sr = sf.read(ARCTIC / f"cmu_us_{spk}_arctic/wav/{utt}.wav", dtype="float32")
        names.append(build(f"en_{spk}_{utt}", "en", arctic_text(spk, utt), audio, sr,
                           f"CMU ARCTIC {spk} {utt} (free use; see COPYING)"))
    text, audio, sr = zeroth("126_003_2058")
    names.append(build("ko_zeroth_126_003_2058", "ko", text, audio, sr, "Zeroth-Korean 126_003_2058 (CC BY 4.0)"))
    (OUT / "index.json").write_text(json.dumps(names))


if __name__ == "__main__":
    main()
