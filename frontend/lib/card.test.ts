// The logic behind the detail card.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import type { PhonemeResult, TipsTable, WordResult } from "./api.ts";
import { allCards, buildCard, hoverCards, issuesOf, plainDescription } from "./card.ts";
import type { ArticulationTable } from "./api.ts";

const TIPS: TipsTable = JSON.parse(readFileSync(new URL("../../content/tips.json", import.meta.url), "utf-8"));
const ART: ArticulationTable = JSON.parse(readFileSync(new URL("../../content/articulation.json", import.meta.url), "utf-8"));

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
  assert.deepEqual(issuesOf(w), [{ pair: "r_as_l", ipa: "ɹ", index: 0, start: 0.1, end: 0.15, produced: null }]); // index: finds the same sound in the native clip
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
test("hovering a red word previews the correct mouth for each red sound that has one", () => {
  const w = word("From", [ph("f", "green"), ph("ɹ", "red", "r_as_l")]);
  assert.deepEqual(hoverCards(w, TIPS, "en").map((c) => c.target), [{ lang: "en", sym: "ɹ" }]);
  const k = word("빵", [ph("p͈", "red", "pp_as_p"), ph("a", "green"), ph("ŋ", "green")]);
  assert.deepEqual(hoverCards(k, TIPS, "ko").map((c) => c.target), [{ lang: "ko", sym: "p͈" }]);
  // nothing to draw: a word that wasn't heard, an extra vowel (no single target sound), an all-green word
  assert.deepEqual(hoverCards(word("now", [ph("n", "red", "word_not_heard")], { not_heard: true }), TIPS, "en"), []);
  assert.deepEqual(hoverCards(word("bus", [ph("b", "green"), ph("s", "red", "extra_vowel")]), TIPS, "en"), []);
  assert.deepEqual(hoverCards(word("now", [ph("n", "green")]), TIPS, "en"), []);
});

// ---------- the every-sound check: a card for ANY English sound swapped or left out ----------
test("a swapped sound gets a card with both mouths, plain labels and practice words", () => {
  const w = word("Testing", [ph("t", "green"), { ...ph("ɛ", "red", "sound_swap", 0.1, 0.2), produced: "eɪ" }]);
  const [issue] = issuesOf(w);
  assert.equal(issue.produced, "eɪ");
  const c = buildCard(issue, w, TIPS, "en")!;
  // the sounds as IPA, then a familiar word that has the sound it came out as
  assert.equal(c.whatHappened, "In “Testing”, your [ɛ] sounded like [eɪ], as in “day”.");
  assert.deepEqual([c.target, c.produced], [{ lang: "en", sym: "ɛ" }, { lang: "en", sym: "eɪ" }]);
  assert.equal(c.simple, false);
  assert.equal(c.practice.length, 3);
  assert.equal(c.reviewed, true); // no phonetic claim of its own: the pictures come from the sound table
  assert.match(buildCard(issue, w, TIPS, "en", "ko")!.whatHappened, /“Testing”에서/);
  assert.deepEqual(hoverCards(w, TIPS, "en").map((x) => x.target), [{ lang: "en", sym: "ɛ" }]);
});

test("a left-out sound gets a card with the correct mouth only", () => {
  const w = word("acts", [ph("æ", "green"), { ...ph("k", "red", "sound_missing"), produced: null }]);
  const c = buildCard(issuesOf(w)[0], w, TIPS, "en")!;
  assert.equal(c.whatHappened, "In “acts”, the [k] sound (as in “key”) seems to be missing.");
  assert.deepEqual(c.target, { lang: "en", sym: "k" });
  assert.equal(c.produced, null);
  assert.equal(c.simple, false); // the correct mouth is still drawn
});

test("two different swaps in one word give two cards", () => {
  const w = word("Stopping", [
    { ...ph("s", "red", "sound_swap"), produced: "d" }, { ...ph("t", "red", "sound_swap"), produced: "ɹ" },
  ]);
  assert.deepEqual(issuesOf(w).map((i) => i.ipa), ["s", "t"]);
});

test("how to fix a swap: make the target sound like the green picture, in the picture's own words", () => {
  const w = word("soup", [ph("s", "green"), { ...ph("uː", "red", "sound_swap"), produced: "æ" }, ph("p", "green")]);
  const c = buildCard(issuesOf(w)[0], w, TIPS, "en", "en", ART.sounds)!;
  assert.equal(c.whatHappened, "In “soup”, your [uː] sounded like [æ], as in “cat”.");
  assert.equal(c.tip, "Make [uː] like the green picture: lips rounded and pushed forward, mouth almost closed. "
    + "Say the practice words slowly, then “soup”.");
  const ko = buildCard(issuesOf(w)[0], w, TIPS, "en", "ko", ART.sounds)!;
  assert.match(ko.whatHappened, /\[uː\].*\[æ\]/);
  assert.match(ko.tip, /입술을 둥글게 앞으로/); // the picture's line in Korean
  // without the sound table (hover preview): still a readable tip, just without the picture's line
  assert.equal(buildCard(issuesOf(w)[0], w, TIPS, "en")!.tip, "Make [uː] like the green picture. Say the practice words slowly, then “soup”.");
});

test("how to fix a left-out sound names it and the picture's line", () => {
  const w = word("acts", [ph("æ", "green"), { ...ph("k", "red", "sound_missing"), produced: null }]);
  const c = buildCard(issuesOf(w)[0], w, TIPS, "en", "en", ART.sounds)!;
  assert.match(c.tip, /^Don't skip \[k\]: .+\. Say “acts” slowly so every sound is there, then speed up\.$/);
});

// ---------- the results page: every card open at once, the pictures' text kept short ----------
test("allCards: every red word's cards, in sentence order, with the word's position", () => {
  const a = word("Testing", [ph("t", "green"), { ...ph("ɛ", "red", "sound_swap"), produced: "eɪ" }]);
  const b = word("the", [ph("ð", "green"), ph("ə", "green")]);
  const c = word("From", [ph("f", "green"), ph("ɹ", "red", "r_as_l")]);
  const cards = allCards([a, b, c], TIPS, "en");
  assert.deepEqual(cards.map((x) => [x.wordIndex, x.card.pair]), [[0, "sound_swap"], [2, "r_as_l"]]);
});

test("plainDescription drops the example-word label in front of a sound's description", () => {
  assert.equal(plainDescription("ship: tongue a little lower and further back than in sheep, relaxed and short."),
    "Tongue a little lower and further back than in sheep, relaxed and short.");
  assert.equal(plainDescription("cat: jaw quite open, tongue low and forward."), "Jaw quite open, tongue low and forward.");
  assert.equal(plainDescription("ㅓ: 혀를 낮추고"), "혀를 낮추고");
  assert.equal(plainDescription("Both lips close, air builds up: lips pop open."), "Both lips close, air builds up: lips pop open.");
});

// ---------- the Korean every-sound check: Korean sounds, Korean mouths, jamo names ----------
test("a Korean swap names both sounds by jamo and draws them from the Korean sound table", () => {
  const w = word("멀을", [ph("m", "green"), { ...ph("ʌ", "red", "sound_swap"), produced: "a" }, ph("ɾ", "green")]);
  const c = buildCard(issuesOf(w)[0], w, TIPS, "ko", "en", ART.sounds)!;
  assert.match(c.whatHappened, /^In “멀을”, your \[ㅓ\] sounded like \[ㅏ\], as in “[가-힣]+”\.$/);
  assert.deepEqual([c.target, c.produced], [{ lang: "ko", sym: "ʌ" }, { lang: "ko", sym: "a" }]);
  assert.deepEqual([c.targetLabel, c.producedLabel], ["ㅓ", "ㅏ"]);
  assert.ok(c.practice.length === 3 && c.practice.every((x) => /^[가-힣]+$/.test(x)));
  assert.match(c.tip, /^Make \[ㅓ\] like the green picture: .+\. Say the practice words slowly, then “멀을”\.$/);
  assert.match(buildCard(issuesOf(w)[0], w, TIPS, "ko", "ko", ART.sounds)!.whatHappened, /“멀을”에서 \[ㅓ\]/);
});

test("a Korean glide + vowel swap is one card, drawn with its vowel", () => {
  const red = (ipa: string) => ({ ...ph(ipa, "red", "sound_swap"), produced: "jo", unit: "jʌ" });
  const w = word("여", [red("j"), red("ʌ")]);
  const issues = issuesOf(w);
  assert.equal(issues.length, 1);
  const c = buildCard(issues[0], w, TIPS, "ko", "en", ART.sounds)!;
  assert.deepEqual([c.targetLabel, c.producedLabel], ["ㅕ", "ㅛ"]);
  assert.deepEqual([c.target, c.produced], [{ lang: "ko", sym: "ʌ" }, { lang: "ko", sym: "o" }]);
});

test("a Korean swap with a hand-written tip uses the tip card, as before", () => {
  const w = word("거", [ph("k", "green"), { ...ph("ʌ", "red", "eo_as_o"), produced: "o" }]);
  assert.equal(buildCard(issuesOf(w)[0], w, TIPS, "ko")!.pair, "eo_as_o");
});
