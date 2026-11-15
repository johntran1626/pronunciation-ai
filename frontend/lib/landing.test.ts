// The type-first landing page: which language a typed sentence is in, and what English input can do.
import { test } from "node:test";
import assert from "node:assert/strict";
import { detectLang, practiceHintKey, practiceOffered } from "./landing.ts";

test("Hangul means Korean, Latin letters mean English, whatever the site language is", () => {
  assert.equal(detectLang("안녕하세요"), "ko");
  assert.equal(detectLang("커피 2잔 주세요."), "ko");
  assert.equal(detectLang("ㅋㅋ 진짜?"), "ko"); // lone jamo count too
  assert.equal(detectLang("Thank you very much."), "en");
  assert.equal(detectLang("I'd like 2 coffees, please."), "en");
});

test("text with both Hangul and Latin letters is mixed; nothing to read gives null", () => {
  assert.equal(detectLang("I really like 김치"), "mix");
  assert.equal(detectLang("오늘 BTS 콘서트 가요"), "mix");
  assert.equal(detectLang("Ben이 왔어."), "mix");
  assert.equal(detectLang(""), null);
  assert.equal(detectLang("   "), null);
  assert.equal(detectLang("123 !?"), null);
});

// ---------- mixed English + Korean ----------
test("Practice is offered for one-language sentences only (scoring was never measured on mixed ones)", () => {
  assert.equal(practiceOffered("ko"), true);
  assert.equal(practiceOffered("en"), true);
  assert.equal(practiceOffered("mix"), false);
});

test("Korean grading is live but partial, and the Practice hint says which sounds BEFORE recording", () => {
  assert.equal(practiceHintKey("en"), "practiceHint");
  assert.equal(practiceHintKey("ko"), "practiceHintKo");
});
