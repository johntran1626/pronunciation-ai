// The logic behind the green/red sentence.
import { test } from "node:test";
import assert from "node:assert/strict";
import { decompose } from "./hangul.ts";
import { GREEN_STYLE, jamoParts, pieceStyle, RED_STYLE, summarize } from "./results.ts";

test("decompose splits a Hangul block into onset, vowel and (optional) coda", () => {
  assert.deepEqual(decompose("같"), [
    { jamo: "ㄱ", slot: "onset" },
    { jamo: "ㅏ", slot: "vowel" },
    { jamo: "ㅌ", slot: "coda" },
  ]);
  assert.deepEqual(decompose("이"), [
    { jamo: "ㅇ", slot: "onset" },
    { jamo: "ㅣ", slot: "vowel" },
  ]);
  assert.deepEqual(decompose("닭")?.map((p) => p.jamo), ["ㄷ", "ㅏ", "ㄺ"]); // double final
  assert.deepEqual(decompose("힣")?.map((p) => p.jamo), ["ㅎ", "ㅣ", "ㅎ"]); // last block in Unicode
});

test("decompose returns null for anything that isn't one Hangul block", () => {
  assert.equal(decompose("a"), null);
  assert.equal(decompose("3"), null);
  assert.equal(decompose("ㄱ"), null); // a lone letter, not a block
});

test("jamoParts paints only the slot that was wrong, even when a letter appears twice", () => {
  const parts = jamoParts({ text: "각", status: "red", red_jamo: ["ㄱ"], red_slots: ["coda"] });
  assert.deepEqual(
    parts?.map((p) => [p.jamo, p.red]),
    [
      ["ㄱ", false],
      ["ㅏ", false],
      ["ㄱ", true],
    ],
  );
});

test("jamoParts falls back to matching the letter when there are no slots", () => {
  const parts = jamoParts({ text: "같", status: "red", red_jamo: ["ㅌ"] });
  assert.deepEqual(
    parts?.map((p) => p.red),
    [false, false, true],
  );
});

test("jamoParts is null for green pieces and for non-Hangul", () => {
  assert.equal(jamoParts({ text: "같", status: "green", red_jamo: [], red_slots: [] }), null);
  assert.equal(jamoParts({ text: "igh", status: "red" }), null);
});

test("summarize counts words that need work", () => {
  const word = (status: "green" | "red") => ({ word: "x", status, start: 0, end: 1, display: [] });
  assert.deepEqual(summarize({ text: "", lang: "en", duration_s: 1, matched: true, reason: null, checks: [], words: [word("green"), word("red"), word("red")] }), {
    words: 3,
    red: 2,
  });
});

// ---------- how red looks ----------

test("red is underlined with a straight line, not a wavy one", () => {
  assert.match(RED_STYLE, /\bunderline\b/);
  assert.doesNotMatch(RED_STYLE, /wavy/);
});

test("a practice result has no plain black text: every piece is green or red", () => {
  assert.equal(pieceStyle("red"), RED_STYLE);
  assert.equal(pieceStyle("green"), GREEN_STYLE);
  assert.equal(pieceStyle("unchecked"), GREEN_STYLE); // nothing found wrong = green
});
