// Developer-only content stays out of the public build.
import { test } from "node:test";
import assert from "node:assert/strict";
import { showDevContent } from "./devOnly.ts";

test("dev content shows only outside a production build", () => {
  assert.equal(showDevContent("development"), true);
  assert.equal(showDevContent("test"), true);
  assert.equal(showDevContent(undefined), true);
  assert.equal(showDevContent("production"), false);
});
