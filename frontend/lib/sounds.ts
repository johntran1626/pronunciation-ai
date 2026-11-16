// Short names and practice words for every sound, for the cards of the every-sound checks (backend/any_sound.py,
// backend/korean_any_sound.py: any sound swapped for another, or left out). Keys = articulation.json's sounds.
import type { Ui } from "./i18n.ts";

// [English name, Korean name, 3 practice words with the sound]
const SOUNDS: Record<string, [string, string, string[]]> = {
  p: ["P", "P", ["pen", "pay", "top"]],
  b: ["B", "B", ["bed", "boy", "cab"]],
  t: ["T", "T", ["ten", "tea", "cat"]],
  d: ["D", "D", ["day", "dog", "bed"]],
  k: ["K", "K", ["key", "cake", "back"]],
  ɡ: ["G", "G", ["go", "bag", "egg"]],
  f: ["F", "F", ["fan", "phone", "leaf"]],
  v: ["V", "V", ["van", "very", "five"]],
  θ: ["TH (as in “think”)", "TH (“think”의 TH)", ["think", "three", "bath"]],
  ð: ["TH (as in “this”)", "TH (“this”의 TH)", ["this", "mother", "breathe"]],
  s: ["S", "S", ["sun", "bus", "miss"]],
  z: ["Z", "Z", ["zoo", "rose", "buzz"]],
  ʃ: ["SH", "SH", ["she", "shoe", "fish"]],
  ʒ: ["ZH (as in “measure”)", "ZH (“measure”의 소리)", ["measure", "vision", "usual"]],
  h: ["H", "H", ["hat", "hello", "ahead"]],
  tʃ: ["CH", "CH", ["chair", "cheese", "watch"]],
  dʒ: ["J", "J", ["jam", "job", "age"]],
  m: ["M", "M", ["man", "moon", "time"]],
  n: ["N", "N", ["no", "name", "sun"]],
  ŋ: ["NG", "NG", ["sing", "long", "ring"]],
  l: ["L", "L", ["light", "look", "ball"]],
  ɹ: ["R", "R", ["red", "right", "road"]],
  w: ["W", "W", ["we", "way", "window"]],
  j: ["Y", "Y", ["yes", "you", "yellow"]],
  iː: ["“sheep” vowel", "“sheep”의 모음", ["sheep", "seat", "green"]],
  ɪ: ["“ship” vowel", "“ship”의 모음", ["ship", "sit", "fish"]],
  ɛ: ["“bed” vowel", "“bed”의 모음", ["bed", "pen", "test"]],
  æ: ["“cat” vowel", "“cat”의 모음", ["cat", "bag", "hand"]],
  ɑː: ["“father” vowel", "“father”의 모음", ["father", "hot", "lock"]],
  ɔː: ["“thought” vowel", "“thought”의 모음", ["thought", "saw", "talk"]],
  ʊ: ["“book” vowel", "“book”의 모음", ["book", "good", "put"]],
  uː: ["“food” vowel", "“food”의 모음", ["food", "blue", "moon"]],
  ʌ: ["“cut” vowel", "“cut”의 모음", ["cut", "cup", "sun"]],
  ə: ["weak “uh” vowel", "약한 “어” 모음", ["about", "sofa", "banana"]],
  ɚ: ["“bird” vowel", "“bird”의 모음", ["bird", "her", "word"]],
  eɪ: ["“day” vowel", "“day”의 모음", ["day", "late", "make"]],
  oʊ: ["“go” vowel", "“go”의 모음", ["go", "home", "boat"]],
  aɪ: ["“my” vowel", "“my”의 모음", ["my", "time", "five"]],
  aʊ: ["“now” vowel", "“now”의 모음", ["now", "house", "out"]],
  ɔɪ: ["“boy” vowel", "“boy”의 모음", ["boy", "coin", "toy"]],
};

// Korean sounds (backend/korean_any_sound.py), keyed by articulation.json's Korean IPA; a glide + vowel is one jamo
// ("jʌ" = ㅕ). [jamo, 3 practice words with that jamo]. ㄹ is a tap between vowels and an L at the end.
const KO_SOUNDS: Record<string, [string, string[]]> = {
  p: ["ㅂ", ["바다", "비", "보리"]], "p͈": ["ㅃ", ["빵", "아빠", "뽀뽀"]], pʰ: ["ㅍ", ["파도", "포도", "피"]],
  t: ["ㄷ", ["다리", "도토리", "두부"]], "t͈": ["ㄸ", ["딸기", "땅", "또"]], tʰ: ["ㅌ", ["토끼", "타조", "투수"]],
  k: ["ㄱ", ["가방", "고기", "구름"]], "k͈": ["ㄲ", ["꿈", "꼬리", "까치"]], kʰ: ["ㅋ", ["코", "키", "커피"]],
  tɕ: ["ㅈ", ["자리", "주스", "지도"]], "t͈ɕ": ["ㅉ", ["짜다", "찌개", "짝"]], tɕʰ: ["ㅊ", ["차", "치마", "초"]],
  s: ["ㅅ", ["사과", "소리", "수박"]], "s͈": ["ㅆ", ["쌀", "씨", "싸다"]], h: ["ㅎ", ["하나", "호수", "허리"]],
  m: ["ㅁ", ["마음", "머리", "엄마"]], n: ["ㄴ", ["나무", "누나", "노래"]], ŋ: ["ㅇ", ["강", "방", "사랑"]],
  ɾ: ["ㄹ", ["나라", "다리", "노래"]], l: ["ㄹ", ["물", "길", "달"]],
  i: ["ㅣ", ["이", "기차", "시소"]], e: ["ㅔ", ["네", "게", "세수"]], ɛ: ["ㅐ", ["개", "새", "배"]],
  a: ["ㅏ", ["아기", "바다", "사자"]], ʌ: ["ㅓ", ["어머니", "거기", "너"]], o: ["ㅗ", ["오리", "고기", "소"]],
  u: ["ㅜ", ["우유", "구두", "누나"]], ɯ: ["ㅡ", ["그림", "크다", "쓰다"]],
  ja: ["ㅑ", ["야구", "야채", "약"]], jʌ: ["ㅕ", ["여자", "겨울", "별"]], jo: ["ㅛ", ["요리", "교실", "우표"]],
  ju: ["ㅠ", ["유리", "휴지", "우유"]], je: ["ㅖ", ["예", "예술", "예약"]], jɛ: ["ㅒ", ["얘기", "걔", "쟤"]],
  wa: ["ㅘ", ["과자", "사과", "와"]], we: ["ㅚ", ["회사", "외국", "괴물"]], wɛ: ["ㅙ", ["왜", "돼지", "괜찮아"]],
  wʌ: ["ㅝ", ["뭐", "원", "더워"]], wi: ["ㅟ", ["귀", "위", "쥐"]], ɰi: ["ㅢ", ["의사", "의자", "의미"]],
};

/** A short name for a sound in the site language: English "“bed” vowel", "T"; Korean the jamo (ㅓ). The IPA if unknown. */
export function soundLabel(ui: Ui, sym: string, lang: "en" | "ko" = "en"): string {
  if (lang === "ko") return KO_SOUNDS[sym]?.[0] ?? sym;
  const s = SOUNDS[sym];
  return s ? s[ui === "ko" ? 1 : 0] : sym;
}

/** 3 short words with this sound (none if unknown). */
export function practiceFor(sym: string, lang: "en" | "ko" = "en"): string[] {
  return (lang === "ko" ? KO_SOUNDS[sym]?.[1] : SOUNDS[sym]?.[2]) ?? [];
}
