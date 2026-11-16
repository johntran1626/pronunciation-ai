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
