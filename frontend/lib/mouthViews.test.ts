// "Mirror" (front), side and inside views in a line-art style.
// Checks placement FACTS per sound, not pixels.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { caption, front, side, views } from "./mouthViews.ts";

const T = JSON.parse(readFileSync(new URL("../../content/articulation.json", import.meta.url), "utf-8")).sounds;
const en = (s: string) => T.en[s];
const ko = (s: string) => T.ko[s];

test("every sound gets a mirror view, plus a side view or (when the key action is hidden) an inside view", () => {
  for (const s of ["p", "b", "m", "f", "v", "θ", "ð", "h", "w", "iː", "ɪ", "uː"]) assert.deepEqual(views(en(s)), ["front", "side"], s);
  for (const s of ["ɹ", "l", "t", "d", "n", "s", "k", "ɡ", "ŋ"]) assert.deepEqual(views(en(s)), ["front", "inside"], s);
  for (const s of ["p", "p͈", "pʰ", "ʌ", "o", "ɯ", "u"]) assert.deepEqual(views(ko(s)), ["front", "side"], s);
  assert.deepEqual(views(ko("ɾ")), ["front", "inside"]);
});

test("mirror view: lips closed for p/b/m, no teeth showing", () => {
  for (const s of ["p", "b", "m"]) {
    const f = front(en(s));
    assert.equal(f.closed, true, s);
    assert.equal(f.upperTeeth || f.lowerTeeth, false, s);
  }
});

test("mirror view: f/v show the upper teeth resting on the lower lip", () => {
  const f = front(en("f"));
  assert.equal(f.lowerLipUnderTeeth, true);
  assert.equal(f.upperTeeth, true);
  assert.equal(f.lowerTeeth, false);
  assert.equal(f.closed, false);
});

test("mirror view: TH shows the tongue tip between the teeth", () => {
  for (const s of ["θ", "ð"]) assert.equal(front(en(s)).tongue, "out", s);
  assert.notEqual(front(en("s")).tongue, "out");
});

test("mirror view: l, n, t, ㄹ show the tongue tip up behind the upper teeth; English r pulls it back out of sight", () => {
  for (const s of ["l", "n", "t"]) assert.equal(front(en(s)).tongue, "tip_up", s);
  assert.equal(front(ko("ɾ")).tongue, "tip_up");
  assert.equal(front(en("ɹ")).tongue, "hidden");
});

test("mirror view: rounded lips are narrower and rounder than spread lips; open vowels open the mouth more", () => {
  const u = front(ko("u")), eu = front(ko("ɯ")), a = front(ko("a")), i = front(ko("i"));
  assert.ok(u.width < eu.width); // ㅜ rounded vs ㅡ spread
  assert.ok(u.height / u.width > eu.height / eu.width);
  assert.ok(a.height > i.height); // ㅏ jaw open vs ㅣ almost closed
  assert.ok(front(ko("ʌ")).width > front(ko("o")).width); // ㅓ relaxed vs ㅗ rounded
});

test("side view: puff of air tells ㅂ, ㅃ and ㅍ apart; nose air for m; voice for voiced sounds", () => {
  assert.equal(side(ko("pʰ")).puff, 3);
  assert.equal(side(ko("p")).puff, 1);
  assert.equal(side(ko("p͈")).puff, 0);
  assert.equal(side(ko("p͈")).tight, true);
  assert.equal(side(ko("p")).tight, false);
  assert.ok(side(en("p")).puff >= 2); // English p: strong puff at the start of a stressed syllable
  assert.equal(side(en("b")).puff, 0);
  assert.equal(side(en("m")).nose, true);
  assert.equal(side(en("p")).nose, false);
  assert.equal(side(en("b")).voice, true);
  assert.equal(side(en("p")).voice, false);
});

test("side view: f/v tuck the lower lip under the upper teeth; TH pokes the tongue tip out; rounding pushes lips forward", () => {
  assert.equal(side(en("f")).lowerLipTucked, true);
  assert.equal(side(en("p")).lowerLipTucked, false);
  assert.equal(side(en("θ")).tongueOut, true);
  assert.ok(side(ko("u")).protrude > side(ko("ɯ")).protrude);
});

test("caption: one plain line saying where things go", () => {
  assert.match(caption(en("f")), /lower lip/i);
  assert.match(caption(en("θ")), /between/i);
  assert.match(caption(en("p")), /lips/i);
  assert.match(caption(ko("pʰ")), /big puff/i);
  assert.match(caption(ko("p͈")), /no puff/i);
  assert.match(caption(ko("p")), /light puff/i);
  assert.match(caption(ko("u")), /rounded/i);
  assert.match(caption(ko("ɯ")), /spread/i);
  assert.match(caption(ko("a")), /open/i);
  assert.match(caption(en("l")), /ridge/i);
  assert.match(caption(en("ɹ")), /not touch/i);
  for (const lang of ["en", "ko"]) for (const e of Object.values(T[lang])) assert.ok(caption(e as never).length <= 70);
});

// ---------- audit: pictures must not contradict their captions ----------
test("side view: an open mouth shows a gap between the upper and lower teeth (not a clenched bite)", () => {
  for (const s of ["ʌ", "a", "ɛ", "e", "o"]) assert.ok(side(ko(s)).teethGap >= 1.5, s); // ㅓ ㅏ ㅐ ㅔ ㅗ
  for (const s of ["ɑː", "æ", "ɛ", "ʌ"]) assert.ok(side(en(s)).teethGap >= 1.5, s);
  assert.ok(side(ko("a")).teethGap > side(ko("ʌ")).teethGap); // ㅏ more open than ㅓ
  assert.ok(side(en("f")).teethGap <= 0); // f: the teeth rest on the lip, no gap
});

test("captions tell neighbouring vowels apart by how open the mouth is", () => {
  assert.notEqual(caption(ko("ɛ")), caption(ko("e"))); // ㅐ vs ㅔ
  assert.notEqual(caption(en("ɪ")), caption(en("iː"))); // ship vs sheep
  assert.match(caption(ko("e")), /slightly open/); // ㅔ is a mid vowel, not "almost closed"
  assert.match(caption(ko("ʌ")), /half open/);
});

test("mirror view: s/z show both rows of teeth close together", () => {
  const s = front(en("s"));
  assert.equal(s.upperTeeth && s.lowerTeeth, true);
});
