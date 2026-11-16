// Which stretch of the recording to play for one word / syllable.
import { test } from "node:test";
import assert from "node:assert/strict";
import { COMPARE_TRIM, compareEnd, sliceBounds } from "./replay.ts";

const close = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);

test("pads both sides so the first and last sounds aren't clipped", () => {
  const b = sliceBounds(1.0, 1.4, 3.0, 0.06);
  close(b!.offset, 0.94);
  close(b!.duration, 0.52);
});

test("never starts before 0 or runs past the end of the recording", () => {
  const start = sliceBounds(0.02, 0.3, 3.0, 0.06)!;
  close(start.offset, 0);
  close(start.duration, 0.36);
  const end = sliceBounds(2.8, 2.98, 3.0, 0.06)!;
  close(end.offset, 2.74);
  close(end.duration, 0.26);
});

test("no times (e.g. a digit with no sounds) means nothing to play", () => {
  assert.equal(sliceBounds(undefined, undefined, 3.0), null);
  assert.equal(sliceBounds(null, 1.0, 3.0), null);
});

test("a zero-length or backwards span still plays the padding around it", () => {
  const b = sliceBounds(1.0, 1.0, 3.0, 0.06)!;
  close(b.duration, 0.12);
  assert.equal(sliceBounds(1.2, 1.0, 3.0), null);
});

// "Your [word]" in the detail card: the aligner's word end runs a little into the next word, which is distracting
// next to the native word said on its own, so the compare button stops a little early.
test("compare: your word stops 0.1 s early, but never cuts a short word away", () => {
  assert.equal(COMPARE_TRIM, 0.1);
  assert.ok(Math.abs(compareEnd(1.0, 1.5) - 1.4) < 1e-9);
  assert.ok(compareEnd(1.0, 1.08) >= 1.05);   // a very short word keeps at least 50 ms
});
