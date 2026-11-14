// The logic behind the detail card.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import type { PhonemeResult, TipsTable, WordResult } from "./api.ts";
import { buildCard, issuesOf, tapAction } from "./card.ts";

const TIPS: TipsTable = JSON.parse(readFileSync(new URL("../../content/tips.json", import.meta.url), "utf-8"));

const ph = (ipa: string, status: PhonemeResult["status"], pair?: string, start = 0.1, end = 0.2): PhonemeResult => ({
  ipa, status, pair, start, end,
});
const word = (w: string, phonemes: PhonemeResult[], extra: Partial<WordResult> = {}): WordResult => ({
  word: w, status: phonemes.some((p) => p.status === "red") ? "red" : "green", start: 0, end: 0.5, display: [],
  phonemes, ...extra,
});

test("issuesOf lists each red pair once, in order, and ignores green / unchecked sounds", () => {
  const w = word("rarer", [
    ph("ɹ", "red", "r_as_l", 0.1, 0.15), ph("ɛ", "green"), ph("ɹ", "red", "r_as_l", 0.3, 0.35), ph("ɚ", "unchecked"),
  ]);
  assert.deepEqual(issuesOf(w), [{ pair: "r_as_l", ipa: "ɹ", index: 0, start: 0.1, end: 0.15 }]); // index: finds the same sound in the native clip
  assert.deepEqual(issuesOf(word("now", [ph("n", "green"), ph("aʊ", "green")])), []);
  assert.deepEqual(issuesOf({ ...w, phonemes: undefined }), []); // older / fake results without sounds
});

test("a word that wasn't heard gives one word_not_heard issue", () => {
  const w = word("now", [ph("n", "red", "word_not_heard"), ph("aʊ", "red", "word_not_heard")], { not_heard: true });
  assert.deepEqual(issuesOf(w).map((i) => i.pair), ["word_not_heard"]);
});

test("buildCard fills in the word and uses the right table for each side", () => {
  const w = word("From", [ph("f", "green"), ph("ɹ", "red", "r_as_l", 0.12, 0.2)]);
  const c = buildCard(issuesOf(w)[0], w, TIPS, "en")!;
  assert.equal(c.whatHappened, "In “From”, the R probably sounded like an L.");
  assert.deepEqual([c.target, c.produced], [{ lang: "en", sym: "ɹ" }, { lang: "en", sym: "l" }]);
  assert.equal(c.simple, false);
  assert.deepEqual(c.sound, { start: 0.12, end: 0.2 });
  assert.equal(c.soundIndex, 1); // The 2nd sound of the word, to find the same sound in the native clip
  assert.equal(c.practice.length, 3);

  const k = word("나라", [ph("n", "green"), ph("a", "green"), ph("ɾ", "red", "tap_as_r"), ph("a", "green")]);
  const kc = buildCard(issuesOf(k)[0], k, TIPS, "ko")!;
  assert.deepEqual(kc.produced, { lang: "en", sym: "ɹ" }); // ㄹ said as an ENGLISH r: drawn from the English table
  assert.equal(kc.needsNativeReview, false); // ㄹ tip approved by a native speaker (2026-11-13)

  const b = word("빵", [ph("p͈", "red", "pp_as_p"), ph("a", "green"), ph("ŋ", "green")]);
  const bc = buildCard(issuesOf(b)[0], b, TIPS, "ko")!;
  assert.equal(bc.whatHappened, "In “빵”, you probably said a plain ㅂ where the word needs a tense ㅃ.");
  assert.equal(bc.needsNativeReview, true); // reworded after her review: waits for her OK
});

test("not-heard and extra-vowel cards are simple (no mouth diagrams)", () => {
  const nh = word("now", [ph("n", "red", "word_not_heard")], { not_heard: true });
  const c = buildCard(issuesOf(nh)[0], nh, TIPS, "en")!;
  assert.equal(c.simple, true);
  assert.equal(c.whatHappened, "We couldn't hear “now” in your recording.");
  assert.equal(c.sound, null); // nothing of "now" was heard, so there's no sound to replay
  assert.equal(c.soundIndex, null); // ...and no single native sound to compare with (the native WORD still plays)
  const ev = word("bus", [ph("b", "green"), ph("ʌ", "green"), ph("s", "red", "extra_vowel")]);
  assert.equal(buildCard(issuesOf(ev)[0], ev, TIPS, "en")!.simple, true);
});

test("an unknown pair gives no card instead of a broken one", () => {
  const w = word("x", [ph("x", "red", "made_up_pair")]);
  assert.equal(buildCard(issuesOf(w)[0], w, TIPS, "en"), null);
});

test("every tip in tips.json builds a card", () => {
  for (const lang of ["en", "ko"] as const) {
    for (const [pair, t] of Object.entries(TIPS.tips[lang])) {
      const w = word("w", [ph(t.target ?? "x", "red", pair)]);
      const c = buildCard(issuesOf(w)[0], w, TIPS, lang);
      assert.ok(c && c.tip && c.whatHappened.includes("“w”"), `${lang} ${pair}`);
    }
  }
});

// Tapping a red word opens its card ONLY; it no longer also plays the audio.
// The card's own buttons replay. Green / plain words have no card, so a tap still plays them.
test("tapAction: a red word opens the card and does not play", () => {
  const red = word("from", [ph("f", "green"), ph("ɹ", "red", "r_as_l")]);
  assert.deepEqual(tapAction(red), { play: false, toggleCard: true });
});

test("tapAction: a word without issues plays and has no card", () => {
  const green = word("now", [ph("n", "green"), ph("aʊ", "green")]);
  assert.deepEqual(tapAction(green), { play: true, toggleCard: false });
});
