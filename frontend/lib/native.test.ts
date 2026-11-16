// The native clips: the URLs the backend caches by, and the word sent on its own for the detail card.
import { test } from "node:test";
import assert from "node:assert/strict";
import { API_BASE, ttsTimingsUrl, ttsUrl } from "./api.ts";
import { wordToSay } from "./native.ts";

test("the timings URL asks the backend for the SAME clip the Hear native button plays", () => {
  const t = new URL(ttsTimingsUrl("같이 가요.", "ko"));
  const a = new URL(ttsUrl("같이 가요.", "ko"));
  assert.equal(t.origin + t.pathname, `${API_BASE}/tts/timings`);
  assert.equal(t.search, a.search); // same text, lang, voice, rate -> same cached WAV on the backend
  assert.equal(new URL(ttsTimingsUrl("Hi.", "en", { slow: true })).searchParams.get("rate"), "-30");
});

// The native "soup" button and the practice words: a fresh clip of the word said on its own (the cut-out piece of
// the sentence could run into the next word: "soup wh-"), so only the word's own letters go to the voice.
test("a word to say on its own: punctuation around it goes, apostrophes and hyphens inside stay", () => {
  assert.equal(wordToSay("standing."), "standing");
  assert.equal(wordToSay("“soup”,"), "soup");
  assert.equal(wordToSay("don't"), "don't");
  assert.equal(wordToSay("red-eye's!"), "red-eye's");
  assert.equal(wordToSay("가요."), "가요");
  assert.equal(wordToSay("(I'm"), "I'm");
});
