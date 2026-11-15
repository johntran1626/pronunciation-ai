// The type-first landing page: which language a typed sentence is in, and what English input can do.
import { test } from "node:test";
import assert from "node:assert/strict";
import { detectLang, practiceOffered } from "./landing.ts";

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

// ---------- English input -> "Translate to KR" / "Translate to KR and Animate" ----------
import { koreanToAnimate, translateOffered } from "./landing.ts";

test("only English input offers the translate buttons", () => {
  assert.equal(translateOffered("en"), true);
  assert.equal(translateOffered("ko"), false);
  assert.equal(translateOffered(null), false);
});

test("the Korean that gets animated is the form the switch shows: 존댓말 by default, 반말 when flipped", () => {
  const t = { translation: "정말 감사합니다.", translation_informal: "정말 고마워." };
  assert.equal(koreanToAnimate(t, false), "정말 감사합니다.");
  assert.equal(koreanToAnimate(t, true), "정말 고마워.");
  assert.equal(koreanToAnimate({ translation: "감사합니다.", translation_informal: null }, true), "감사합니다."); // one form only
});

// ---------- mixed English + Korean ----------
test("Practice is offered for one-language sentences only (scoring was never measured on mixed ones)", () => {
  assert.equal(practiceOffered("ko"), true);
  assert.equal(practiceOffered("en"), true);
  assert.equal(practiceOffered("mix"), false);
});

test("no Translate to KR for a mixed sentence (it is already part Korean)", () => {
  assert.equal(translateOffered("mix"), false);
});
