// The logic behind the green/red sentence.
import { test } from "node:test";
import assert from "node:assert/strict";
import { decompose } from "./hangul.ts";
import { describeChecks, jamoParts, summarize } from "./results.ts";

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

// ---------- say exactly what was checked ----------

test("describeChecks names every live check in plain words", () => {
  assert.equal(
    describeChecks(["sentence_match", "word_heard", "r_as_l"]),
    "This version checks that you read the sentence, that each word was heard, and R (said like L). Plain text = not checked yet.",
  );
});

test("describeChecks is honest when only the sentence check is live", () => {
  assert.equal(
    describeChecks(["sentence_match"]),
    "This version checks that you read the sentence. Plain text = not checked yet.",
  );
});

test("describeChecks with nothing live says nothing was graded", () => {
  assert.equal(describeChecks([]), "No checks are switched on yet, so nothing was graded.");
});
