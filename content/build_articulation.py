"""Build content/articulation.json: how each sound is made, for the detail card.
(LLM-drafted from the sources below; every entry says reviewed: false until a human checks it.)

    python -m content.build_articulation

The FACTS are the short tables below (one line per sound). The drawing numbers ("svg") are DERIVED from the facts
by fixed rules at the bottom, so a diagram can never disagree with its own description.

Standard descriptions from (citation details to double-check before the README):
  - International Phonetic Association, IPA chart (2020 revision).
  - P. Ladefoged & K. Johnson, A Course in Phonetics (Cengage), chapters on English consonants and vowels.
  - Hyun Bok Lee (1993), "Korean", Journal of the International Phonetic Association 23(1), Illustrations of the IPA
    (also in the Handbook of the IPA, 1999).
  - J. Shin, J. Kiaer & J. Cha (2013), The Sounds of Korean, Cambridge University Press.
  - D. Silva (2006), "Acoustic evidence for the emergence of tonal contrast in contemporary Korean", Phonology 23.
  - Our own measurements: spikes/b_vot.py (pitch separates ㅂ/ㅍ better than VOT for these speakers).
English = General American. Korean = standard Seoul.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "articulation.json"

# ---------- consonants ----------
# (symbol, place, manner, voicing, laryngeal (Korean 3-way, else None), plain-words description)
EN_CONSONANTS = [
    ("p", "bilabial", "stop", "voiceless", None, "Both lips close, air builds up, lips pop open. A strong puff of air at the start of a stressed syllable (pin), almost none after s (spin)."),
    ("b", "bilabial", "stop", "voiced", None, "Both lips close and pop open, with the voice on (or starting right away). No puff of air."),
    ("t", "alveolar", "stop", "voiceless", None, "Tongue tip presses the ridge just behind the upper teeth, then releases. A puff of air at the start of a stressed syllable."),
    ("d", "alveolar", "stop", "voiced", None, "Tongue tip presses the ridge behind the upper teeth and releases, with the voice on. No puff."),
    ("k", "velar", "stop", "voiceless", None, "The back of the tongue presses the soft palate, then releases. A puff of air at the start of a stressed syllable."),
    ("ɡ", "velar", "stop", "voiced", None, "The back of the tongue presses the soft palate and releases, with the voice on. No puff."),
    ("f", "labiodental", "fricative", "voiceless", None, "Upper teeth rest lightly on the lower lip; air hisses through the gap. The lips never close."),
    ("v", "labiodental", "fricative", "voiced", None, "Upper teeth on the lower lip, air flowing through, with the voice on (a buzz). The lips never close."),
    ("θ", "dental", "fricative", "voiceless", None, "Tongue tip lightly between or just behind the upper front teeth; air hisses over it (think)."),
    ("ð", "dental", "fricative", "voiced", None, "Tongue tip between or just behind the upper front teeth, voice on (this). The tip doesn't press, so it isn't a d."),
    ("s", "alveolar", "fricative", "voiceless", None, "Tongue tip close to (not touching) the ridge behind the upper teeth; a narrow groove makes a sharp hiss."),
    ("z", "alveolar", "fricative", "voiced", None, "Like s, with the voice on: a buzzing hiss."),
    ("ʃ", "postalveolar", "fricative", "voiceless", None, "Tongue blade just behind the ridge, wider than for s; lips pushed slightly forward (she)."),
    ("ʒ", "postalveolar", "fricative", "voiced", None, "Like sh with the voice on (measure)."),
    ("h", "glottal", "fricative", "voiceless", None, "Breath through an open throat; the mouth is already shaped for the next vowel."),
    ("tʃ", "postalveolar", "affricate", "voiceless", None, "Tongue blade presses just behind the ridge, then releases into a sh (church); lips slightly forward."),
    ("dʒ", "postalveolar", "affricate", "voiced", None, "Like ch with the voice on (judge)."),
    ("m", "bilabial", "nasal", "voiced", None, "Lips closed, voice on, air goes out through the nose."),
    ("n", "alveolar", "nasal", "voiced", None, "Tongue tip on the ridge behind the upper teeth, voice on, air through the nose."),
    ("ŋ", "velar", "nasal", "voiced", None, "Back of the tongue against the soft palate, air through the nose (sing). No g at the end."),
    ("l", "alveolar", "lateral", "voiced", None, "Tongue tip TOUCHES the ridge behind the upper teeth and stays there; air flows around the sides. At the end of a syllable (ball) the back of the tongue also rises (dark L)."),
    ("ɹ", "postalveolar", "approximant", "voiced", None, "Tongue tip curls up and back, or the tongue bunches up, but it NEVER touches the roof of the mouth; lips slightly rounded."),
    ("w", "labial-velar", "approximant", "voiced", None, "Lips rounded and pushed forward, back of the tongue raised, then glide into the vowel."),
    ("j", "palatal", "approximant", "voiced", None, "Front of the tongue raised close to the hard palate (like a quick ee), then glide into the vowel (yes)."),
]

KO_CONSONANTS = [
    ("p", "bilabial", "stop", "voiceless", "plain", "ㅂ: lips close and open with a light puff. Between voiced sounds it becomes voiced [b]. At a syllable end the lips stay closed (unreleased)."),
    ("p͈", "bilabial", "stop", "voiceless", "tense", "ㅃ: lips close, throat tight, release with almost no puff; the next vowel starts high and sharp."),
    ("pʰ", "bilabial", "stop", "voiceless", "aspirated", "ㅍ: lips close and release with a big puff of air; the next vowel starts high."),
    ("t", "alveolar", "stop", "voiceless", "plain", "ㄷ: tongue tip and blade against the back of the upper teeth and the ridge (denti-alveolar), light puff. Voiced [d] between voiced sounds; unreleased at a syllable end."),
    ("t͈", "alveolar", "stop", "voiceless", "tense", "ㄸ: same place as ㄷ, throat tight, almost no puff, high sharp vowel after."),
    ("tʰ", "alveolar", "stop", "voiceless", "aspirated", "ㅌ: same place as ㄷ, big puff of air."),
    ("k", "velar", "stop", "voiceless", "plain", "ㄱ: back of the tongue against the soft palate, light puff. Voiced [ɡ] between voiced sounds; unreleased at a syllable end."),
    ("k͈", "velar", "stop", "voiceless", "tense", "ㄲ: same place as ㄱ, throat tight, almost no puff."),
    ("kʰ", "velar", "stop", "voiceless", "aspirated", "ㅋ: same place as ㄱ, big puff of air."),
    ("tɕ", "alveolo-palatal", "affricate", "voiceless", "plain", "ㅈ: front of the tongue presses behind the ridge toward the hard palate, released into a soft hiss. Voiced between voiced sounds."),
    ("t͈ɕ", "alveolo-palatal", "affricate", "voiceless", "tense", "ㅉ: like ㅈ with a tight throat and no puff."),
    ("tɕʰ", "alveolo-palatal", "affricate", "voiceless", "aspirated", "ㅊ: like ㅈ with a big puff of air."),
    ("s", "alveolar", "fricative", "voiceless", "plain", "ㅅ: a soft, breathy s. Before ㅣ or a y-sound it is pronounced like a soft sh [ɕ]."),
    ("s͈", "alveolar", "fricative", "voiceless", "tense", "ㅆ: a tense, sharp s with a tight throat, no breathiness."),
    ("h", "glottal", "fricative", "voiceless", None, "ㅎ: breath through the throat. Often weak or silent between voiced sounds."),
    ("m", "bilabial", "nasal", "voiced", None, "ㅁ: lips closed, air through the nose."),
    ("n", "alveolar", "nasal", "voiced", None, "ㄴ: tongue tip behind the upper teeth, air through the nose."),
    ("ŋ", "velar", "nasal", "voiced", None, "ㅇ at a syllable end: back of the tongue against the soft palate, air through the nose (like English sing)."),
    ("ɾ", "alveolar", "tap", "voiced", None, "ㄹ between vowels: the tongue tip taps the ridge behind the upper teeth ONCE, very quickly. Not an English r (no curling), not a long l."),
    ("l", "alveolar", "lateral", "voiced", None, "ㄹ at a syllable end (and ㄹㄹ): tongue tip stays on the ridge, air around the sides, like a light English l."),
    ("j", "palatal", "approximant", "voiced", None, "The y-glide in ㅑ ㅕ ㅛ ㅠ ㅒ ㅖ: front of the tongue raised toward the hard palate."),
    ("w", "labial-velar", "approximant", "voiced", None, "The w-glide in ㅘ ㅝ ㅙ ㅞ ㅟ: lips rounded, back of the tongue raised."),
    ("ɰ", "velar", "approximant", "voiced", None, "The glide at the start of ㅢ: back of the tongue raised like ㅡ, lips NOT rounded."),
]

# ---------- vowels ----------
# (symbol, height, frontness, rounded, description[, lips override])
EN_VOWELS = [
    ("iː", "close", "front", False, "sheep: tongue high and forward, lips spread; held a bit longer and tenser than ship."),
    ("ɪ", "near-close", "near-front", False, "ship: tongue a little lower and further back than in sheep, relaxed and short."),
    ("ɛ", "open-mid", "front", False, "bed: tongue front, jaw half open."),
    ("æ", "near-open", "front", False, "cat: jaw quite open, tongue low and forward."),
    ("ɑː", "open", "back", False, "father: jaw open, tongue low and back, lips relaxed."),
    ("ɔː", "open-mid", "back", True, "thought: tongue low-mid and back, lips slightly rounded (many Americans say it like father)."),
    ("ʊ", "near-close", "near-back", True, "book: tongue high-ish and back, lips loosely rounded, short."),
    ("uː", "close", "back", True, "food: tongue high and back, lips rounded (often a bit fronted in American English)."),
    ("ʌ", "open-mid", "back", False, "cut: tongue mid-low and fairly central, lips relaxed (not rounded)."),
    ("ə", "mid", "central", False, "the unstressed 'uh' (about): everything relaxed in the middle."),
    ("ɚ", "mid", "central", False, "bird / butter: the r-colored vowel; tongue bunched or tip curled up as for r, without touching."),
]
EN_DIPHTHONGS = [  # (symbol, start height, start frontness, start rounded, glides to, description)
    ("eɪ", "close-mid", "front", False, "ɪ", "day: starts at e and glides up toward the i of ship."),
    ("oʊ", "close-mid", "back", True, "ʊ", "go: starts at o with rounded lips and glides toward the u of book."),
    ("aɪ", "open", "central", False, "ɪ", "my: starts with an open jaw and glides up toward the i of ship."),
    ("aʊ", "open", "central", False, "ʊ", "now: starts open and glides toward the u of book, rounding the lips at the end."),
    ("ɔɪ", "open-mid", "back", True, "ɪ", "boy: starts rounded and back, glides forward to the i of ship."),
]
KO_VOWELS = [
    ("i", "close", "front", False, "ㅣ: tongue high and forward, lips spread."),
    ("e", "mid", "front", False, "ㅔ: tongue mid and forward. Many Seoul speakers say ㅔ and ㅐ the same."),
    ("ɛ", "open-mid", "front", False, "ㅐ: like ㅔ but a little more open. Many Seoul speakers merge it with ㅔ."),
    ("a", "open", "central", False, "ㅏ: jaw open, tongue low and central."),
    ("ʌ", "open-mid", "back", False, "ㅓ: tongue mid-low and back, jaw fairly open, lips NOT pushed forward. (ㅗ has the same tongue area but rounded lips.)"),
    ("o", "close-mid", "back", True, "ㅗ: tongue back, lips clearly rounded and pushed forward. Younger speakers raise it toward ㅜ."),
    ("u", "close", "back", True, "ㅜ: tongue high and back, lips tightly rounded."),
    ("ɯ", "close", "back", False, "ㅡ: tongue high and back like ㅜ, but the lips are SPREAD, not rounded. Often a little central [ɨ].", "spread"),
]

# ---------- drawing rules (svg numbers are derived, never typed per sound) ----------
# tongue_x: 0 = far back, 1 = far front. tongue_y: 0 = low (jaw open), 1 = high.
PLACE_SHAPE = {  # place -> (tongue_x, tongue_y, tip)
    "bilabial": (0.5, 0.45, "down"), "labiodental": (0.5, 0.45, "down"), "dental": (0.65, 0.5, "dental"),
    "alveolar": (0.6, 0.55, "alveolar"), "postalveolar": (0.55, 0.6, "postalveolar"),
    "alveolo-palatal": (0.75, 0.8, "palatal"), "palatal": (0.8, 0.85, "palatal"),
    "velar": (0.2, 0.85, "down"), "labial-velar": (0.2, 0.8, "down"), "glottal": (0.5, 0.4, "down"),
}
HEIGHT_Y = {"close": 1.0, "near-close": 0.85, "close-mid": 0.7, "mid": 0.55, "open-mid": 0.4, "near-open": 0.2, "open": 0.0}
FRONT_X = {"front": 0.9, "near-front": 0.75, "central": 0.5, "near-back": 0.3, "back": 0.15}
CLOSURE = {"stop", "nasal", "affricate", "tap", "lateral"}  # the tongue (or lips) actually touch
LIP_GAP = {"closed": 0.0, "lip_to_teeth": 0.1, "rounded": 0.3, "spread": 0.5, "neutral": 0.4}
SLIGHTLY_ROUNDED = {("en", "ʃ"), ("en", "ʒ"), ("en", "tʃ"), ("en", "dʒ"), ("en", "ɹ")}


def consonant(lang, ipa, place, manner, voicing, laryngeal, text):
    x, y, tip = PLACE_SHAPE[place]
    if place in ("bilabial",) and manner in ("stop", "nasal"):
        lips = "closed"
    elif place == "labiodental":
        lips = "lip_to_teeth"
    elif place == "labial-velar" or (lang, ipa) in SLIGHTLY_ROUNDED:
        lips = "rounded"
    else:
        lips = "neutral"
    if manner == "approximant" and place == "postalveolar":
        tip = "raised"  # English r: tip up, no contact
    contact = manner in CLOSURE and place not in ("bilabial", "labiodental", "glottal")
    lip_round = 0.9 if place == "labial-velar" else 0.5 if lips == "rounded" else 0.0
    kind = "glide" if manner == "approximant" and place in ("palatal", "labial-velar", "velar") else "consonant"
    return {"kind": kind, "place": place, "manner": manner, "voicing": voicing, "laryngeal": laryngeal, "lips": lips,
            "description": text, "reviewed": False,
            "svg": {"tongue_x": x, "tongue_y": y, "tip": tip, "contact": contact,
                    "velum": "lowered" if manner == "nasal" else "raised",
                    "lip_gap": LIP_GAP[lips], "lip_round": lip_round}}


def vowel(ipa, height, front, rounded, text, lips=None, kind="vowel", to=None):
    lips = lips or ("rounded" if rounded else "spread" if front in ("front", "near-front") else "neutral")
    e = {"kind": kind, "height": height, "frontness": front, "rounded": rounded, "voicing": "voiced",
         "laryngeal": None, "lips": lips, "description": text, "reviewed": False,
         "svg": {"tongue_x": FRONT_X[front], "tongue_y": HEIGHT_Y[height], "tip": "down", "contact": False,
                 "velum": "raised", "lip_gap": LIP_GAP[lips], "lip_round": 0.9 if rounded else 0.0}}
    if to:
        e["to"] = to
    return e


def build():
    en = {c[0]: consonant("en", *c) for c in EN_CONSONANTS}
    en.update({v[0]: vowel(*v) for v in EN_VOWELS})
    en.update({d[0]: vowel(d[0], d[1], d[2], d[3], d[5], kind="diphthong", to=d[4]) for d in EN_DIPHTHONGS})
    ko = {c[0]: consonant("ko", *c) for c in KO_CONSONANTS}
    ko.update({v[0]: vowel(*v) for v in KO_VOWELS})
    return {
        "note": "Textbook TARGET articulations, not measurements of the user's mouth (the app estimates from audio). "
                "LLM-drafted (Claude) from the sources below; reviewed: false until checked by a human reviewer.",
        "sources": [
            "International Phonetic Association, IPA chart (2020 revision)",
            "Ladefoged & Johnson, A Course in Phonetics (Cengage)",
            "Lee, Hyun Bok (1993), 'Korean', Journal of the International Phonetic Association 23(1) (Illustrations of the IPA)",
            "Shin, Kiaer & Cha (2013), The Sounds of Korean, Cambridge University Press",
            "Silva (2006), 'Acoustic evidence for the emergence of tonal contrast in contemporary Korean', Phonology 23",
            "This project's VOT and pitch measurements (spikes/b_vot.py)",
        ],
        "svg_axes": {"tongue_x": "0 = back, 1 = front", "tongue_y": "0 = low/open, 1 = high/close",
                     "lip_gap": "0 = closed, 1 = wide open", "lip_round": "0 = spread/neutral, 1 = fully rounded"},
        "sounds": {"en": en, "ko": ko},
    }


if __name__ == "__main__":
    table = build()
    OUT.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT.name}: {len(table['sounds']['en'])} English + {len(table['sounds']['ko'])} Korean sounds")
