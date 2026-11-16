// The Practice button = the record button: 3 2 1, record, stop, analyze (or cancel an empty recording).
import { test } from "node:test";
import assert from "node:assert/strict";
import { COUNTDOWN_MS, countdownDigit, emptyRecording, MIN_SECONDS, PRE_ROLL, trimCountdown } from "./practice.ts";

test("the countdown shows 3, 2, 1 over about 2.3 seconds, then recording starts", () => {
  assert.equal(COUNTDOWN_MS, 2300);
  assert.equal(countdownDigit(0), 3);
  assert.equal(countdownDigit(700), 3);
  assert.equal(countdownDigit(800), 2);
  assert.equal(countdownDigit(1600), 1);
  assert.equal(countdownDigit(2299), 1);
  assert.equal(countdownDigit(2300), null);
});

test("the countdown is cut off the recording, keeping a short lead-in so the first sound isn't clipped", () => {
  const rate = 1000;
  const samples = new Float32Array(5000).map((_, i) => i); // 5 s; the countdown ended 2.3 s in
  const out = trimCountdown(samples, rate, 2.3);
  assert.equal(out.length, 5000 - Math.round((2.3 - PRE_ROLL) * rate));
  assert.equal(out[0], Math.round((2.3 - PRE_ROLL) * rate));
  assert.equal(trimCountdown(samples, rate, 0).length, 5000); // nothing to cut
  assert.equal(trimCountdown(samples, rate, 9).length, 0);    // stopped during the countdown
});

test("too short or (almost) silent recordings are not sent for analysis", () => {
  assert.equal(MIN_SECONDS, 0.7);
  assert.equal(emptyRecording({ seconds: 0.4, peak: 0.5, rmsDb: -20 }), "short");
  assert.equal(emptyRecording({ seconds: 3, peak: 0.004, rmsDb: -70 }), "silent");
  assert.equal(emptyRecording({ seconds: 3, peak: 0.05, rmsDb: -62 }), "silent");   // a tick, then nothing
  assert.equal(emptyRecording({ seconds: 3, peak: 0.3, rmsDb: -30 }), null);          // speech
  assert.equal(emptyRecording({ seconds: 3, peak: 0.05, rmsDb: -48 }), null);         // quiet speech still goes
});
