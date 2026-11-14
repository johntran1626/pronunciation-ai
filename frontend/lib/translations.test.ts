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
