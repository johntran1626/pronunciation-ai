// The "hear native" URL.
import { test } from "node:test";
import assert from "node:assert/strict";
import { API_BASE, ttsUrl } from "./api.ts";

test("points at the backend's /tts with the sentence, language, voice and speed", () => {
  const u = new URL(ttsUrl("같이 가요.", "ko"));
  assert.equal(u.origin + u.pathname, `${API_BASE}/tts`);
  assert.equal(u.searchParams.get("text"), "같이 가요.");
  assert.equal(u.searchParams.get("lang"), "ko");
  assert.equal(u.searchParams.get("voice"), "female"); // the woman's voice by default
  assert.equal(u.searchParams.get("rate"), "0");
});

test("text with & ? # survives the trip (it is encoded, not cut off)", () => {
  const text = "Tom & Jerry? #1";
  assert.equal(new URL(ttsUrl(text, "en")).searchParams.get("text"), text);
});

test("slow version asks for 30% slower; the man's voice can be chosen", () => {
  const u = new URL(ttsUrl("Hi.", "en", { slow: true, voice: "male" }));
  assert.equal(u.searchParams.get("rate"), "-30");
  assert.equal(u.searchParams.get("voice"), "male");
});

test("no API key or Azure address ever appears in the URL", () => {
  assert.doesNotMatch(ttsUrl("Hi.", "en"), /azure|microsoft|key=/i);
});

test("a mixed sentence asks for lang=mix (the backend picks the multilingual voice)", () => {
  assert.equal(new URL(ttsUrl("I want 떡볶이.", "mix")).searchParams.get("lang"), "mix");
});
