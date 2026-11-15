// The type-first landing page: which language a typed sentence is in, and which sample sentences to offer.
import { test } from "node:test";
import assert from "node:assert/strict";
import { detectLang, SAMPLE_PACKS, sampleLines } from "./landing.ts";

test("Hangul means Korean, Latin letters mean English, whatever the site language is", () => {
  assert.equal(detectLang("안녕하세요"), "ko");
  assert.equal(detectLang("커피 2잔 주세요."), "ko");
  assert.equal(detectLang("ㅋㅋ 진짜?"), "ko"); // lone jamo count too
  assert.equal(detectLang("Thank you very much."), "en");
  assert.equal(detectLang("I'd like 2 coffees, please."), "en");
});

test("mixed text goes by the larger share of letters; nothing to read gives null", () => {
  assert.equal(detectLang("I really like 김치"), "en");
  assert.equal(detectLang("오늘 BTS 콘서트 가요"), "ko");
  assert.equal(detectLang(""), null);
  assert.equal(detectLang("   "), null);
  assert.equal(detectLang("123 !?"), null);
});

test("samples come from Basics and Casual only, in both languages", () => {
  assert.deepEqual(SAMPLE_PACKS, { en: ["en-basics", "en-casual"], ko: ["ko-basics", "ko-casual"] });
});

const item = (text: string, speech?: "존댓말" | "반말") => ({ id: text, text, translation: null, tags: [], speech });
test("Korean samples: Basics shows the polite lines, Casual the casual ones; English lines are all shown", () => {
  const ko = [item("감사합니다.", "존댓말"), item("고마워.", "반말")];
  assert.deepEqual(sampleLines({ id: "ko-basics", items: ko }).map((i) => i.text), ["감사합니다."]);
  assert.deepEqual(sampleLines({ id: "ko-casual", items: ko }).map((i) => i.text), ["고마워."]);
  const en = [item("Thank you."), item("Hi.")];
  assert.equal(sampleLines({ id: "en-casual", items: en }).length, 2);
});

// ---------- English input -> "Translate to KR" / "Translate to KR and Animate" ----------
import { koreanToAnimate, storedTranslation, translateOffered } from "./landing.ts";

test("only English input offers the translate buttons", () => {
  assert.equal(translateOffered("en"), true);
  assert.equal(translateOffered("ko"), false);
  assert.equal(translateOffered(null), false);
});

test("an English sample uses its stored Korean (no translate call); typed or edited text has none", () => {
  const it = { id: "x", text: "Thank you very much.", translation: "정말 감사합니다.", translation_informal: "정말 고마워.", tags: [] };
  assert.deepEqual(storedTranslation(it, "Thank you very much."), { translation: "정말 감사합니다.", translation_informal: "정말 고마워." });
  assert.equal(storedTranslation(it, "Thank you so much."), null); // the box was edited after picking it
  assert.equal(storedTranslation(null, "Thank you very much."), null);
  assert.equal(storedTranslation({ ...it, translation: null }, it.text), null);
});

test("the Korean that gets animated is the form the switch shows: 존댓말 by default, 반말 when flipped", () => {
  const t = { translation: "정말 감사합니다.", translation_informal: "정말 고마워." };
  assert.equal(koreanToAnimate(t, false), "정말 감사합니다.");
  assert.equal(koreanToAnimate(t, true), "정말 고마워.");
  assert.equal(koreanToAnimate({ translation: "감사합니다.", translation_informal: null }, true), "감사합니다."); // one form only
});
