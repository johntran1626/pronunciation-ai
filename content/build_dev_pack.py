"""Build the two DEV sentence packs: content/packs/dev_en.json and dev_ko.json.

Run from the project root:  python -m content.build_dev_pack
Needs the git-ignored corpora in data/ (CMU ARCTIC prompts, Zeroth parquet files). The output JSON is committed.

DEV ONLY. These are NOT the learner packs. The sentences are real, native-written text, picked by hand
for being everyday and neutral (no names, politics or religion), but no one has reviewed them as
learning content, and there are no translations. Both packs say so in the JSON and in the UI.
"""
import json
import re
from pathlib import Path

import pyarrow.parquet as pq

from backend.g2p import expected_phonemes
from backend.scoring import PAIRS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "content" / "packs"
ARCTIC_PROMPTS = ROOT / "data" / "cmu_arctic" / "cmu_us_bdl_arctic" / "etc" / "txt.done.data"
ZEROTH = ROOT / "data" / "zeroth" / "data"

# Hand-picked from ARCTIC prompts with 5-8 words, no digits, no names, at least one R sound.
# a0020 is 9 words but is our test fixture (tests/fixtures/), so there's native audio for it.
ENGLISH_IDS = ["arctic_a0020", "arctic_a0031", "arctic_a0052", "arctic_a0054", "arctic_a0079",
               "arctic_a0181", "arctic_a0183", "arctic_a0195", "arctic_a0205", "arctic_a0230"]

# Hand-picked from Zeroth (shortest sentences are 29 characters). split -> ids.
# 126_003_2058 is our Korean test fixture.
KOREAN_IDS = {"test": ["126_003_2058", "137_003_0934", "149_003_2650"],
              "train-00000-of-00006": ["191_003_0210", "191_003_0634", "191_003_0810", "201_003_1744",
                                       "201_003_1785", "214_003_1965", "192_003_1155"]}

# Korean MVP targets, as the IPA our g2p.py writes for them.
KO_VOWELS = {"a", "ɛ", "ʌ", "e", "o", "u", "ɯ", "i", "j", "w", "ɰ"}
P_STOPS = {"p", "p͈", "pʰ"}  # ㅂ ㅃ ㅍ


def english_tags(phonemes):
    """Which MVP English pairs this sentence practices: a pair's target sound appears in it."""
    return sorted(name for name, pair in PAIRS.items() if pair["target"] in phonemes)


def korean_tags(phonemes):
    tags = set()
    if "ʌ" in phonemes or "o" in phonemes:
        tags.add("eo_vs_o")
    if "ɯ" in phonemes:
        tags.add("eu")
    if "ɛ" in phonemes or "e" in phonemes:
        tags.add("ae_vs_e")
    if "ɾ" in phonemes:
        tags.add("tap_r")  # ㄹ between vowels; ㄹ at a syllable end is [l], not a tap
    # ㅂ/ㅃ/ㅍ only contrast before a vowel; a final ㅂ (밥) is unreleased, so it doesn't count.
    if any(p in P_STOPS and nxt in KO_VOWELS for p, nxt in zip(phonemes, phonemes[1:])):
        tags.add("p_stops")
    return sorted(tags)


def flat_phonemes(text, lang):
    return [p for w in expected_phonemes(text, lang) for p in w["phonemes"]]


def build_english():
    prompts = dict(re.findall(r'\( (arctic_\w+) "(.*)" \)', ARCTIC_PROMPTS.read_text()))
    items = [{"id": i, "text": prompts[i], "translation": None,
              "tags": english_tags(flat_phonemes(prompts[i], "en"))} for i in ENGLISH_IDS]
    return {
        "id": "dev-en", "lang": "en", "name": "Dev pack (English)",
        "dev_only": True, "reviewed": False,
        "note": "Developer test sentences, not reviewed as learning content. Learner packs are separate.",
        "source": "CMU ARCTIC prompts (Carnegie Mellon University, 2003), http://www.festvox.org/cmu_arctic/ ; "
                  "prompt text unmodified, selection by this project",
        "license": "CMU ARCTIC: free for any purpose with the notice kept; full notice in tests/fixtures/LICENSES.md",
        "items": items,
    }


def build_korean():
    texts = {}
    for split, ids in KOREAN_IDS.items():
        name = "test-00000-of-00001" if split == "test" else split
        for r in pq.read_table(ZEROTH / f"{name}.parquet", columns=["id", "text"]).to_pylist():
            if r["id"] in ids:
                texts[r["id"]] = r["text"]
    order = [i for ids in KOREAN_IDS.values() for i in ids]
    missing = [i for i in order if i not in texts]
    assert not missing, f"Zeroth ids not found: {missing}"
    items = [{"id": i, "text": texts[i], "translation": None,
              "tags": korean_tags(flat_phonemes(texts[i], "ko"))} for i in order]
    return {
        "id": "dev-ko", "lang": "ko", "name": "Dev pack (Korean)",
        "dev_only": True, "reviewed": False,
        "note": "Developer test sentences, not reviewed as learning content. Native-written news-style text, "
                "longer than real packs will be. Learner packs are separate.",
        "source": "Zeroth-Korean (Zeroth Project: Lucas Jo, Atlas Guide Inc.; Wonkyum Lee, Gridspace Inc.), "
                  "via Hugging Face kresnik/zeroth_korean; transcript text unmodified, selection by this project",
        "license": "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)",
        "items": items,
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for pack, fname in [(build_english(), "dev_en.json"), (build_korean(), "dev_ko.json")]:
        (OUT / fname).write_text(json.dumps(pack, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{fname}: {len(pack['items'])} sentences")
        for it in pack["items"]:
            print(f"  {it['id']:14} {it['tags']}  {it['text']}")
