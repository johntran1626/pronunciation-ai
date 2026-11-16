// Short names and practice words for every English sound, for the cards of the every-sound check
// (backend/any_sound.py: any sound swapped for another, or left out). Keys = articulation.json's English sounds.
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

/** A short name for an English sound in the site language ("“bed” vowel", "T"); the IPA if unknown. */
export function soundLabel(ui: Ui, sym: string): string {
  const s = SOUNDS[sym];
  return s ? s[ui === "ko" ? 1 : 0] : sym;
}

/** 3 short words with this English sound (none if unknown). */
export function practiceFor(sym: string): string[] {
  return SOUNDS[sym]?.[2] ?? [];
}
