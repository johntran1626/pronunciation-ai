// Custom mode ("type your own").
import { test } from "node:test";
import assert from "node:assert/strict";
import { API_BASE, customUrl, fetchCustom } from "./api.ts";
import { MAX_CUSTOM_CHARS, checkLine, typedProblem } from "./custom.ts";

// Swap the browser's fetch for a fake one for a single test, and remember which URL was asked for.
function fakeFetch(status: number, body: unknown) {
  const asked: string[] = [];
  globalThis.fetch = (async (url: string) => {
    asked.push(String(url));
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  return asked;
}

test("the URL asks the backend's /custom with the typed text and language, encoded", () => {
  const u = new URL(customUrl("커피 2잔 & 물?", "ko"));
  assert.equal(u.origin + u.pathname, `${API_BASE}/custom`);
  assert.equal(u.searchParams.get("text"), "커피 2잔 & 물?"); // & and ? survive (not cut off)
  assert.equal(u.searchParams.get("lang"), "ko");
});

test("a good reply gives back the spoken-words sentence", async () => {
  const asked = fakeFetch(200, { text: "커피 두 잔 주세요.", typed: "커피 2잔 주세요.", changed: true });
  const r = await fetchCustom("커피 2잔 주세요.", "ko");
  assert.equal(r.text, "커피 두 잔 주세요.");
  assert.equal(r.changed, true);
  assert.equal(asked.length, 1);
});

test("a 400 shows the backend's own reason, word for word (it is written for the learner)", async () => {
  fakeFetch(400, { detail: "That's 95 characters. Keep it to 80 or fewer (one short sentence)." });
  await assert.rejects(fetchCustom("x".repeat(95), "en"), {
    message: "That's 95 characters. Keep it to 80 or fewer (one short sentence).",
  });
});

test("no backend at all -> the usual 'can't reach' message", async () => {
  globalThis.fetch = (async () => {
    throw new TypeError("Failed to fetch");
  }) as typeof fetch;
  await assert.rejects(fetchCustom("Hi.", "en"), /Can't reach the backend/);
});

test("instant checks before asking the backend: empty and too long", () => {
  assert.equal(MAX_CUSTOM_CHARS, 80); // same limit as backend/custom.py MAX_CHARS
  assert.match(typedProblem("   ") ?? "", /Type a sentence/);
  assert.match(typedProblem("a".repeat(81)) ?? "", /81 characters.*80/);
  assert.equal(typedProblem("a".repeat(80)), null);
  assert.equal(typedProblem("  Hi there.  "), null); // spaces around it don't count
});

test("'We'll check' line: the converted sentence, plus a note only when something was rewritten", () => {
  const changed = checkLine({ text: "커피 두 잔 주세요.", typed: "커피 2잔 주세요.", changed: true });
  assert.equal(changed.text, "커피 두 잔 주세요.");
  assert.match(changed.note ?? "", /written out the way (they're|it's) said/);
  const same = checkLine({ text: "Hello there.", typed: "Hello there.", changed: false });
  assert.equal(same.note, null);
});
