// Pack + Custom translations: 존댓말 by default, a small switch shows 반말.
import { test } from "node:test";
import assert from "node:assert/strict";
import { hasBothForms, pickTranslation } from "./translations.ts";

const both = { translation: "정말 감사합니다.", translation_informal: "정말 고마워." };

test("존댓말 is the default; the switch picks 반말", () => {
  assert.deepEqual(pickTranslation(both, false), { form: "존댓말", text: "정말 감사합니다." });
  assert.deepEqual(pickTranslation(both, true), { form: "반말", text: "정말 고마워." });
  assert.equal(hasBothForms(both), true);
});

test("one translation (Korean packs, Korean -> English) shows as is, whatever the switch says", () => {
  const one = { translation: "Two coffees, please.", translation_informal: null };
  assert.deepEqual(pickTranslation(one, false), { form: null, text: "Two coffees, please." });
  assert.deepEqual(pickTranslation(one, true), { form: null, text: "Two coffees, please." });
  assert.deepEqual(pickTranslation({ translation: "Hello." }, true), { form: null, text: "Hello." });
  assert.equal(hasBothForms(one), false);
});

test("no translation (dev packs) gives null", () => {
  assert.equal(pickTranslation({ translation: null }, false), null);
  assert.equal(hasBothForms({ translation: null }), false);
});

// Korean packs: each line IS one speech level, so the same switch filters the sentence list instead.
import { bySpeech, hasSpeechLevels } from "./translations.ts";

const koItems = [
  { id: "a", speech: "존댓말" as const },
  { id: "b", speech: "반말" as const },
  { id: "c", speech: "존댓말" as const },
];

test("a Korean pack shows only 존댓말 lines by default, only 반말 lines with the switch on", () => {
  assert.deepEqual(bySpeech(koItems, false).map((it) => it.id), ["a", "c"]);
  assert.deepEqual(bySpeech(koItems, true).map((it) => it.id), ["b"]);
  assert.equal(hasSpeechLevels(koItems), true);
});

test("packs without speech levels (English, dev) are never filtered", () => {
  const plain = [{ id: "x" }, { id: "y" }];
  assert.deepEqual(bySpeech(plain, true), plain);
  assert.deepEqual(bySpeech(plain, false), plain);
  assert.equal(hasSpeechLevels(plain), false);
});
