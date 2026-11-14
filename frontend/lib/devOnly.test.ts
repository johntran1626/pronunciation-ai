// Developer-only content stays out of the public build.
import { test } from "node:test";
import assert from "node:assert/strict";
import { pickerPacks, showDevContent } from "./devOnly.ts";

const packs = [
  { id: "dev-en", dev_only: true },
  { id: "en-basics", dev_only: false },
  { id: "en-office", dev_only: false },
];

test("the public build lists only learner packs", () => {
  assert.deepEqual(pickerPacks(packs, false).map((p) => p.id), ["en-basics", "en-office"]);
});

test("a local dev server still lists the dev packs, in the backend's order", () => {
  assert.deepEqual(pickerPacks(packs, true).map((p) => p.id), ["dev-en", "en-basics", "en-office"]);
});

test("dev content shows only outside a production build", () => {
  assert.equal(showDevContent("development"), true);
  assert.equal(showDevContent("test"), true);
  assert.equal(showDevContent(undefined), true);
  assert.equal(showDevContent("production"), false);
});
