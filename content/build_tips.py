"""Build content/tips.json: what went wrong + how to fix it, per confusion pair.
(LLM-drafted from content/articulation.json facts; a human reviews each tip before it counts as reviewed.
Every entry says reviewed: false until then, and Korean ones also say needs_native_review: true.)

    python -m content.build_tips

One line per pair: (name, target, produced, labels, what happened, tip, 3 practice words, facts).
- "what happened" has one {word} slot; the card fills in the word or syllable that went red.
- "facts" = the articulation.json facts the tip is written from. tests/test_tips.py checks each one against the
  table, so a tip can't quietly contradict the mouth diagram drawn next to it.
- Practice words are checked by our own G2P (backend.g2p): each really contains the target sound.
- Wording says "probably": the app estimates from audio, it doesn't see the mouth (honesty).
English pairs mirror backend/scoring.PAIRS; Korean pairs follow the MVP list (ㅓ/ㅗ, ㅡ, ㅐ/ㅔ, ㄹ tap, ㅂ/ㅃ/ㅍ).
"""
import json
from pathlib import Path

from backend.g2p import TENSE

OUT = Path(__file__).resolve().parent / "tips.json"


def tip(target, produced, target_label, produced_label, what_happened, text, practice, facts=None,
        target_lang=None, produced_lang=None, position=None, lang="en", sources=None):
    e = {"target": target, "target_lang": target_lang or lang, "target_label": target_label,
         "produced": produced, "produced_lang": produced_lang or lang, "produced_label": produced_label,
         "what_happened": what_happened, "tip": text, "practice": practice, "facts": facts or {},
         "reviewed": False}
    if sources:
        e["sources"] = sources    # the phonetics references the tip was checked against (Korean: no native reviewer)
    if position:
        e["position"] = position  # practice words must START with the target (Korean stops change mid-word)
    if lang == "ko":
        e["needs_native_review"] = True
    return e


# ---------- learning English (Korean speakers) ----------
EN = {
    "r_as_l": tip("ɹ", "l", "English R", "L",
                  "In “{word}”, the R probably sounded like an L.",
                  "Pull your tongue back and don't let the tip touch the roof of your mouth. Round your lips slightly.",
                  ["red", "right", "road"],
                  {"target": {"contact": False, "lips": "rounded"}, "produced": {"contact": True}}),
    "l_as_r": tip("l", "ɹ", "L", "English R",
                  "In “{word}”, the L probably sounded like an R.",
                  "Touch the ridge just behind your upper teeth with your tongue tip and keep it there as the vowel starts. Don't curl the tongue back.",
                  ["light", "long", "lake"],
                  {"target": {"contact": True, "tip": "alveolar"}, "produced": {"contact": False}}),
    "f_as_p": tip("f", "p", "F", "P",
                  "In “{word}”, the F probably sounded like a P.",
                  "Rest your upper teeth lightly on your lower lip and blow a long “fff”. Your lips never close for F.",
                  ["fan", "fine", "coffee"],
                  {"target": {"lips": "lip_to_teeth"}, "produced": {"lips": "closed"}}),
    "v_as_b": tip("v", "b", "V", "B",
                  "In “{word}”, the V probably sounded like a B.",
                  "Upper teeth on your lower lip like F, but turn your voice on so it buzzes: “vvv”. Don't press your lips together.",
                  ["van", "very", "voice"],
                  {"target": {"lips": "lip_to_teeth", "voicing": "voiced"}, "produced": {"lips": "closed"}}),
    "th_as_s": tip("θ", "s", "TH (as in think)", "S",
                   "In “{word}”, the TH probably sounded like an S or T.",
                   "Put your tongue tip lightly between your front teeth and blow. Don't press, and don't pull the tip back behind the teeth like for S.",
                   ["think", "three", "bath"],
                   {"target": {"tip": "dental", "manner": "fricative"}, "produced": {"tip": "alveolar"}}),
    "dh_as_d": tip("ð", "d", "TH (as in this)", "D",
                   "In “{word}”, the TH probably sounded like a D.",
                   "Tongue tip lightly between your front teeth, voice on, and let the air keep flowing so it buzzes. If the tip presses the ridge, it becomes D.",
                   ["this", "they", "mother"],
                   {"target": {"tip": "dental", "voicing": "voiced", "contact": False}, "produced": {"contact": True}}),
    "ih_as_iy": tip("ɪ", "iː", "the short i in “ship”", "the long ee in “sheep”",
                    "In “{word}”, the short i probably sounded like a long ee.",
                    "Relax: let your tongue and jaw drop a little from the “ee” position, and keep the vowel short. Ship is shorter and looser than sheep.",
                    ["ship", "sit", "fill"],
                    {"target": {"height": "near-close"}, "produced": {"height": "close"}}),
    "iy_as_ih": tip("iː", "ɪ", "the long ee in “sheep”", "the short i in “ship”",
                    "In “{word}”, the long ee probably sounded like a short i.",
                    "Spread your lips like a small smile, push your tongue high and forward, and hold the vowel a little longer: “sheeep”.",
                    ["sheep", "seat", "feel"],
                    {"target": {"height": "close", "lips": "spread"}, "produced": {"height": "near-close"}}),
    "extra_vowel": tip(None, "ɯ", "the last consonant", "an extra “eu” vowel (ㅡ)",
                       "“{word}” probably had an extra “eu” vowel after the last sound.",
                       "End the word on the consonant and stop your voice right there. Don't release it into a small “eu”.",
                       ["bus", "desk", "milk"], produced_lang="ko"),
    "word_not_heard": tip(None, None, "this word", None,
                          "We couldn't hear “{word}” in your recording.",
                          "Say every word, including short ones like “a”, “the” and “to”. Try again a little slower.",
                          []),
}

# ---------- learning Korean (English speakers). ALL need native review before users see them. ----------
# References for the Korean tips (also listed in content/articulation.json "sources")
SRC_LEE = "Lee, Hyun Bok (1993), 'Korean', Journal of the International Phonetic Association 23(1) (Illustrations of the IPA)"
SRC_SHIN = "Shin, Kiaer & Cha (2013), The Sounds of Korean, Cambridge University Press"
SRC_CJL = ("Cho, Jun & Ladefoged (2002), 'Acoustic and aerodynamic correlates of Korean stops and fricatives', "
           "Journal of Phonetics 30")
SRC_SILVA = "Silva (2006), 'Acoustic evidence for the emergence of tonal contrast in contemporary Korean', Phonology 23"
STOP_SOURCES = [SRC_CJL, SRC_SILVA, SRC_SHIN]

KO = {
    "eo_as_o": tip("ʌ", "o", "ㅓ", "ㅗ",
                   "In “{word}”, ㅓ probably sounded like ㅗ.",
                   "Keep your lips relaxed and open, not rounded or pushed forward, and drop your jaw a bit more than for ㅗ. The tongue stays back for both.",
                   ["거기", "머리", "버스"],
                   {"target": {"rounded": False}, "produced": {"rounded": True, "lips": "rounded"}}, lang="ko"),
    "eu_as_u": tip("ɯ", "u", "ㅡ", "ㅜ",
                   "In “{word}”, ㅡ probably sounded like ㅜ.",
                   "Keep the tongue high and back as for ㅜ, but spread your lips flat like a slight smile. No rounding at all.",
                   ["그림", "크다", "쓰다"],
                   {"target": {"rounded": False, "lips": "spread", "height": "close"},
                    "produced": {"rounded": True, "height": "close"}}, lang="ko"),
    "ae_as_e": tip("ɛ", "e", "ㅐ", "ㅔ",
                   "In “{word}”, ㅐ may have sounded like ㅔ.",
                   "Open your jaw a little more than for ㅔ. Many Seoul speakers say ㅐ and ㅔ the same (they've merged), so this is a fine detail.",
                   ["개", "새", "배"],
                   {"target": {"height": "open-mid"}, "produced": {"height": "mid"}}, lang="ko"),
    "tap_as_r": tip("ɾ", "ɹ", "ㄹ (a quick tap)", "English R",
                    "In “{word}”, ㄹ probably sounded like an English R.",
                    "Don't curl your tongue back. Flick the tip once, quickly, against the ridge behind your upper teeth, like the tt in American “butter”.",
                    ["나라", "다리", "우리"],
                    {"target": {"manner": "tap", "contact": True}, "produced": {"contact": False}},
                    produced_lang="en", lang="ko"),
    "tap_as_l": tip("ɾ", "l", "ㄹ (a quick tap)", "a long L",
                    "In “{word}”, ㄹ probably sounded like a long English L.",
                    "Between vowels, touch the ridge for only an instant and let go right away. Don't hold the tongue there like an English L.",
                    ["노래", "사랑", "거리"],
                    {"target": {"manner": "tap"}, "produced": {"manner": "lateral"}}, lang="ko"),
    "pp_as_p": tip("p͈", "p", "ㅃ (tense)", "ㅂ (plain)",
                   "In “{word}”, you probably said a plain ㅂ where the word needs a tense ㅃ.",
                   "Tighten your throat, press your lips firmly, and release with no puff of air. Start the vowel high and sharp.",
                   ["빵", "뿌리", "뽀뽀"],
                   {"target": {"laryngeal": "tense"}, "produced": {"laryngeal": "plain"}}, position="initial", lang="ko"),
    "pp_as_ph": tip("p͈", "pʰ", "ㅃ (tense)", "ㅍ (aspirated)",
                    "In “{word}”, you probably said an aspirated ㅍ (too much air) where the word needs a tense ㅃ.",
                    "Hold a hand in front of your mouth: for ㅃ you should feel almost no air. Tighten your throat and release the lips without a puff.",
                    ["빵", "뿌리", "뽀뽀"],
                    {"target": {"laryngeal": "tense"}, "produced": {"laryngeal": "aspirated"}}, position="initial", lang="ko"),
    "ph_as_p": tip("pʰ", "p", "ㅍ (aspirated)", "ㅂ (plain)",
                   "In “{word}”, you probably said a plain ㅂ where the word needs an aspirated ㅍ.",
                   "Release your lips with a big puff of air (you can feel it on your hand) and start the vowel at a high pitch.",
                   ["포도", "파도", "피"],
                   {"target": {"laryngeal": "aspirated"}, "produced": {"laryngeal": "plain"}}, position="initial", lang="ko"),
    "p_as_ph": tip("p", "pʰ", "ㅂ (plain)", "ㅍ (aspirated)",
                   "In “{word}”, you probably said an aspirated ㅍ where the word needs a plain ㅂ.",
                   "Use a lighter puff and start the vowel at a lower, relaxed pitch. In Seoul speech, the vowel's pitch is a big part of what separates ㅂ from ㅍ.",
                   ["바다", "비", "불"],
                   {"target": {"laryngeal": "plain"}, "produced": {"laryngeal": "aspirated"}}, position="initial", lang="ko"),
    # The two live Korean checks (backend/korean_scoring.py): ㅜ said like ㅡ, and a plain stop said tense.
    "u_as_eu": tip("u", "ɯ", "ㅜ", "ㅡ",
                   "In “{word}”, ㅜ probably sounded like ㅡ.",
                   "Round your lips and push them forward a little, like English “oo”. The tongue stays high and back, as for ㅡ; only the lips change.",
                   ["구두", "수박", "두부"],
                   {"target": {"rounded": True, "lips": "rounded", "height": "close"},
                    "produced": {"rounded": False, "lips": "spread", "height": "close"}},
                   lang="ko", sources=[SRC_LEE, SRC_SHIN]),
    "p_as_pp": tip("p", "p" + TENSE, "ㅂ (plain)", "ㅃ (tense)",
                   "In “{word}”, you probably said a tense ㅃ where the word needs a plain ㅂ.",
                   "Relax your throat and close your lips lightly. At the start of a word, let a little air out and start the vowel low; between vowels, ㅂ is soft, close to English b.",
                   ["바다", "비", "불"],
                   {"target": {"laryngeal": "plain"}, "produced": {"laryngeal": "tense"}},
                   position="initial", lang="ko", sources=STOP_SOURCES),
    "t_as_tt": tip("t", "t" + TENSE, "ㄷ (plain)", "ㄸ (tense)",
                   "In “{word}”, you probably said a tense ㄸ where the word needs a plain ㄷ.",
                   "Relax your throat and touch the tongue tip lightly behind your teeth. At a word's start, let a little air out and start the vowel low; between vowels, ㄷ is soft, close to English d.",
                   ["다리", "도시", "두부"],
                   {"target": {"laryngeal": "plain"}, "produced": {"laryngeal": "tense"}},
                   position="initial", lang="ko", sources=STOP_SOURCES),
    "k_as_kk": tip("k", "k" + TENSE, "ㄱ (plain)", "ㄲ (tense)",
                   "In “{word}”, you probably said a tense ㄲ where the word needs a plain ㄱ.",
                   "Relax your throat and touch the back of the tongue lightly. At a word's start, let a little air out and start the vowel low; between vowels, ㄱ is soft, close to English g.",
                   ["가방", "고기", "구름"],
                   {"target": {"laryngeal": "plain"}, "produced": {"laryngeal": "tense"}},
                   position="initial", lang="ko", sources=STOP_SOURCES),
}


# Review status: every English tip, plus the Korean vowel and ㄹ tips (checked by a native speaker).
# The ㅂ/ㅃ/ㅍ tips are worded "you said X where the word needs Y", because Koreans hear ㅂ ㅃ ㅍ as clearly
# different sounds ("ㅃ sounded like ㅂ" would mislead); they stay unreviewed until checked against a reference.
REVIEWED = {"en": set(EN), "ko": {"eo_as_o", "eu_as_u", "ae_as_e", "tap_as_r", "tap_as_l"}}


def build():
    for lang, table in (("en", EN), ("ko", KO)):
        for name, e in table.items():
            e["reviewed"] = name in REVIEWED[lang]
            if lang == "ko":
                e["needs_native_review"] = not e["reviewed"]
    return {
        "note": "Fixed tips per confusion pair (target -> produced), never generated at request time. LLM-drafted (Claude); "
                "reviewed: true once a human reviewer approved it (see REVIEWED). "
                "Facts come from content/articulation.json; the LLM is never used for these.",
        "tips": {"en": EN, "ko": KO},
    }


if __name__ == "__main__":
    table = build()
    OUT.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT.name}: {len(EN)} English + {len(KO)} Korean tips")
