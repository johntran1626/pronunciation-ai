// Finding the native speaker's version of a word / sound, for the "Native" button in the detail card.
import { test } from "node:test";
import assert from "node:assert/strict";
import { API_BASE, ttsTimingsUrl, ttsUrl, type NativeTimings } from "./api.ts";
import { nativePart } from "./native.ts";

const T: NativeTimings = {
  version: 1,
  lang: "en",
  duration_s: 2.0,
  words: [
    { word: "From", start: 0.3, end: 0.7, phonemes: [
      { ipa: "f", start: 0.3, end: 0.4 }, { ipa: "ɹ", start: 0.4, end: 0.5 },
      { ipa: "ʌ", start: 0.5, end: 0.6 }, { ipa: "m", start: 0.6, end: 0.7 },
    ] },
    { word: "now", start: 0.8, end: 1.2, phonemes: [{ ipa: "n", start: 0.8, end: 0.9 }, { ipa: "aʊ", start: 0.9, end: 1.2 }] },
  ],
};

test("the timings URL asks the backend for the SAME clip the Hear native button plays", () => {
  const t = new URL(ttsTimingsUrl("같이 가요.", "ko"));
  const a = new URL(ttsUrl("같이 가요.", "ko"));
  assert.equal(t.origin + t.pathname, `${API_BASE}/tts/timings`);
  assert.equal(t.search, a.search); // same text, lang, voice, rate -> same cached WAV on the backend
  assert.equal(new URL(ttsTimingsUrl("Hi.", "en", { slow: true })).searchParams.get("rate"), "-30");
});

test("a word: found by its position, and it must be the same word", () => {
  assert.deepEqual(nativePart(T, 0, "From", null), { start: 0.3, end: 0.7 });
  assert.deepEqual(nativePart(T, 1, "now", null), { start: 0.8, end: 1.2 });
  assert.equal(nativePart(T, 1, "From", null), null); // positions don't line up: play nothing, never the wrong word
  assert.equal(nativePart(T, 5, "now", null), null);
});

test("a sound: the same sound number inside the word", () => {
  assert.deepEqual(nativePart(T, 0, "From", 1), { start: 0.4, end: 0.5 }); // the R of From
  assert.equal(nativePart(T, 0, "From", 9), null);
});

test("the same sound must be the target: a wrong symbol is refused", () => {
  assert.deepEqual(nativePart(T, 0, "From", 1, "ɹ"), { start: 0.4, end: 0.5 });
  assert.equal(nativePart(T, 0, "From", 1, "l"), null);
});

test("Korean typed in another Unicode form (decomposed jamo) still matches", () => {
  const ko: NativeTimings = { ...T, lang: "ko", words: [{ word: "가요", start: 0.1, end: 0.5, phonemes: [] }] };
  assert.deepEqual(nativePart(ko, 0, "가요".normalize("NFD"), null), { start: 0.1, end: 0.5 });
});

test("no timings yet (still loading, or failed) -> nothing to play", () => {
  assert.equal(nativePart(null, 0, "From", null), null);
});
