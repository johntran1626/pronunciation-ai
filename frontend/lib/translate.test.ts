// Custom-mode translation.
import { test } from "node:test";
import assert from "node:assert/strict";
import { API_BASE, fetchTranslation, translateUrl } from "./api.ts";

function fakeFetch(status: number, body: unknown) {
  const asked: string[] = [];
  globalThis.fetch = (async (url: string) => {
    asked.push(String(url));
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  return asked;
}

test("the URL asks /translate with the sentence and its language, encoded", () => {
  const u = new URL(translateUrl("Tom & Jerry?", "en"));
  assert.equal(u.origin + u.pathname, `${API_BASE}/translate`);
  assert.equal(u.searchParams.get("text"), "Tom & Jerry?");
  assert.equal(u.searchParams.get("lang"), "en");
});

test("a translation comes back with both Korean forms", async () => {
  const asked = fakeFetch(200, { translation: "커피 두 잔 주세요.", translation_informal: "커피 두 잔 줘.", cached: false });
  assert.deepEqual(await fetchTranslation("Two coffees, please.", "en"), {
    translation: "커피 두 잔 주세요.",
    translation_informal: "커피 두 잔 줘.",
  });
  assert.equal(asked.length, 1);
});

test("Korean -> English has one form", async () => {
  fakeFetch(200, { translation: "Two coffees, please.", translation_informal: null, cached: true });
  assert.deepEqual(await fetchTranslation("커피 두 잔 주세요.", "ko"), {
    translation: "Two coffees, please.",
    translation_informal: null,
  });
});

test("a failed translation is just missing (null), never an error that blocks practice", async () => {
  for (const status of [400, 429, 503]) {
    fakeFetch(status, { detail: "nope" });
    assert.equal(await fetchTranslation("Hello there.", "en"), null);
  }
  globalThis.fetch = (async () => {
    throw new TypeError("network down");
  }) as typeof fetch;
  assert.equal(await fetchTranslation("Hello there.", "en"), null);
});

test("a malformed answer is treated as missing", async () => {
  fakeFetch(200, { translation: 42 });
  assert.equal(await fetchTranslation("Hello there.", "en"), null);
});
