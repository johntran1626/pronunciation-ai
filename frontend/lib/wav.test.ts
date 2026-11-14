// The WAV encoder. Run with `npm test` (Node's built-in test runner; no extra package).
import { test } from "node:test";
import assert from "node:assert/strict";
import { decodeWav16, encodeWav16, louderForPlayback, trimToSeconds } from "./wav.ts";

// Reading the native (Azure) WAV ourselves, so it plays through the same slice player as YOUR audio.
test("decodeWav16 reads back what encodeWav16 wrote (rate + samples, within 1 step of 16-bit)", () => {
  const x = new Float32Array([0, 0.5, -0.5, 0.25, -1, 0.999]);
  const { samples, rate } = decodeWav16(encodeWav16(x, 24000));
  assert.equal(rate, 24000);
  assert.equal(samples.length, x.length);
  x.forEach((s, i) => assert.ok(Math.abs(samples[i] - s) <= 1 / 32767, `sample ${i}`));
});

test("decodeWav16 skips extra chunks (e.g. LIST metadata) before the audio", () => {
  const plain = new Uint8Array(encodeWav16(new Float32Array([0.5, -0.5]), 16000));
  const list = new Uint8Array([...("LIST")].map((c) => c.charCodeAt(0)).concat([4, 0, 0, 0, 1, 2, 3, 4]));
  const withList = new Uint8Array(plain.length + list.length); // RIFF/WAVE + fmt (36 bytes), LIST, then data
  withList.set(plain.subarray(0, 36), 0);
  withList.set(list, 36);
  withList.set(plain.subarray(36), 36 + list.length);
  const { samples, rate } = decodeWav16(withList.buffer);
  assert.equal(rate, 16000);
  assert.equal(samples.length, 2);
  assert.ok(Math.abs(samples[0] - 0.5) < 1e-3);
});

test("decodeWav16 refuses anything that isn't 16-bit mono PCM WAV", () => {
  assert.throws(() => decodeWav16(new TextEncoder().encode("<html>error</html>").buffer as ArrayBuffer));
  const stereo = encodeWav16(new Float32Array([0, 0]), 16000);
  new DataView(stereo).setUint16(22, 2, true); // claim 2 channels
  assert.throws(() => decodeWav16(stereo));
});

const ascii = (v: DataView, at: number, n: number) =>
  String.fromCharCode(...Array.from({ length: n }, (_, i) => v.getUint8(at + i)));

test("header says RIFF/WAVE, PCM, mono, 16 kHz, 16-bit", () => {
  const v = new DataView(encodeWav16(new Float32Array([0, 0, 0]), 16000));
  assert.equal(ascii(v, 0, 4), "RIFF");
  assert.equal(v.getUint32(4, true), 36 + 6); // file size minus the first 8 bytes
  assert.equal(ascii(v, 8, 4), "WAVE");
  assert.equal(ascii(v, 12, 4), "fmt ");
  assert.equal(v.getUint16(20, true), 1); // 1 = plain PCM (uncompressed)
  assert.equal(v.getUint16(22, true), 1); // channels
  assert.equal(v.getUint32(24, true), 16000); // sample rate
  assert.equal(v.getUint32(28, true), 16000 * 2); // bytes per second
  assert.equal(v.getUint16(32, true), 2); // bytes per sample frame
  assert.equal(v.getUint16(34, true), 16); // bits per sample
  assert.equal(ascii(v, 36, 4), "data");
  assert.equal(v.getUint32(40, true), 6); // 3 samples x 2 bytes
});

test("total size is 44 header bytes + 2 bytes per sample", () => {
  assert.equal(encodeWav16(new Float32Array(1000), 16000).byteLength, 44 + 2000);
});

test("samples are scaled to 16-bit and clipped, never wrapped around", () => {
  const v = new DataView(encodeWav16(new Float32Array([0, 1, -1, 0.5, -0.5, 2, -2]), 16000));
  const got = Array.from({ length: 7 }, (_, i) => v.getInt16(44 + 2 * i, true));
  assert.deepEqual(got, [0, 32767, -32768, 16384, -16384, 32767, -32768]);
});

test("trimToSeconds cuts long audio to the limit and leaves short audio alone", () => {
  const long = new Float32Array(16000 * 16);
  assert.equal(trimToSeconds(long, 16000, 15).length, 16000 * 15);
  const short = new Float32Array(16000 * 3);
  assert.equal(trimToSeconds(short, 16000, 15), short);
});

// ---------- playback volume (raw recordings play back too quietly) ----------

test("louderForPlayback raises quiet audio so its peak hits the target", () => {
  const out = louderForPlayback(new Float32Array([0.05, -0.1, 0.02]), 0.9, 20);
  assert.ok(Math.abs(Math.max(...out.map(Math.abs)) - 0.9) < 1e-6);
  assert.ok(Math.abs(out[0] / out[1] - 0.05 / -0.1) < 1e-6); // same shape, just louder
});

test("louderForPlayback never boosts more than maxGain (so near-silence doesn't become loud hiss)", () => {
  const out = louderForPlayback(new Float32Array([0.001, -0.001]), 0.9, 20);
  assert.ok(Math.abs(out[0] - 0.02) < 1e-6);
});

test("louderForPlayback leaves already-loud audio alone and returns a copy", () => {
  const x = new Float32Array([0.95, -0.5]);
  const out = louderForPlayback(x, 0.9, 20);
  assert.deepEqual(Array.from(out), Array.from(x));
  assert.notEqual(out, x);
});
