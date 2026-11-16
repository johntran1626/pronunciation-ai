// Names and practice words for every English sound (the cards of the every-sound check).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { practiceFor, soundLabel } from "./sounds.ts";

const ART = JSON.parse(readFileSync(new URL("../../content/articulation.json", import.meta.url), "utf-8"));
const HANGUL = /[가-힣]/;

test("every English sound has a name in both languages and 3 practice words", () => {
  const syms = Object.keys(ART.sounds.en);
  assert.equal(syms.length, 40);
  for (const sym of syms) {
    assert.ok(soundLabel("en", sym), sym);
    assert.ok(soundLabel("ko", sym), sym);
    assert.equal(practiceFor(sym).length, 3, sym);
  }
  assert.equal(soundLabel("en", "ɛ"), "“bed” vowel");
  assert.match(soundLabel("ko", "ɛ"), HANGUL);
  assert.equal(soundLabel("en", "t"), "T");
});

// Korean sounds (the Korean every-sound check, backend/korean_any_sound.py): the jamo as the name, Korean practice words.
const KO_UNITS = ["ja", "jʌ", "jo", "ju", "je", "jɛ", "wa", "we", "wɛ", "wʌ", "wi", "ɰi"]; // a glide + vowel, one jamo
const SYLLABLES = (w: string) => [...w].map((ch) => ch.normalize("NFD")).join("");

test("every Korean sound and glide + vowel has its jamo as the name and 3 Korean practice words", () => {
  const syms = Object.keys(ART.sounds.ko).filter((s) => !["j", "w", "ɰ"].includes(s)).concat(KO_UNITS);
  for (const sym of syms) {
    const label = soundLabel("en", sym, "ko");
    assert.match(label, /[ㄱ-ㆎ]/, sym);
    assert.equal(soundLabel("ko", sym, "ko"), label, sym); // a jamo reads the same on both sites
    const words = practiceFor(sym, "ko");
    assert.equal(words.length, 3, sym);
    for (const w of words) assert.match(w, /^[가-힣]+$/, `${sym}: ${w}`);
  }
  assert.deepEqual([soundLabel("en", "ʌ", "ko"), soundLabel("en", "p͈", "ko"), soundLabel("en", "jʌ", "ko")], ["ㅓ", "ㅃ", "ㅕ"]);
  assert.equal(soundLabel("en", "ʌ"), "“cut” vowel"); // English stays the default
});

test("Korean practice words really have the sound: the jamo is in every word", () => {
  // decomposed Hangul uses the conjoining jamo, so compare against those (ㅓ = U+1165, ㅃ = U+1108 ...)
  const CONJ: Record<string, string> = { ㅓ: "ᅥ", ㅗ: "ᅩ", ㅜ: "ᅮ", ㅡ: "ᅳ", ㅃ: "ᄈ", ㅍ: "ᄑ", ㅕ: "ᅧ" };
  for (const [sym, jamo] of [["ʌ", "ㅓ"], ["o", "ㅗ"], ["u", "ㅜ"], ["ɯ", "ㅡ"], ["p͈", "ㅃ"], ["pʰ", "ㅍ"], ["jʌ", "ㅕ"]]) {
    for (const w of practiceFor(sym, "ko")) assert.ok(SYLLABLES(w).includes(CONJ[jamo]), `${w} has ${jamo}`);
  }
});
