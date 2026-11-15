// The native mouth player: speed changes at any moment, a fresh 1x player for every new animation, the autoplay
// setting, and Replay kept beside the speed buttons (never over the picture).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { AUTOPLAY_DEFAULT, SPEEDS, changeSpeed, playerKey, readAutoplay, saveAutoplay, type Media } from "./player.ts";
import { DEFAULT_SPEED } from "./animate.ts";

// a stand-in for the <audio> element: the clock moves only while playing
function fakeAudio(at = 1.2): Media & { log: string[] } {
  const log: string[] = [];
  return {
    log, paused: false, ended: false, currentTime: at, playbackRate: 1, defaultPlaybackRate: 1,
    pause() { this.paused = true; log.push("pause"); },
    play() { this.paused = false; log.push(`play@${this.currentTime}x${this.playbackRate}`); return Promise.resolve(); },
  };
}

test("the speeds are 1x and 0.5x, and every player starts at 1x", () => {
  assert.deepEqual(SPEEDS, [1, 0.5]);
  assert.equal(DEFAULT_SPEED, 1);
});

test("changing speed mid-audio keeps playing from the same spot at the new speed, however often it's changed", async () => {
  const a = fakeAudio(1.2);
  for (const s of [0.5, 1, 0.5, 1, 0.5]) {
    await changeSpeed(a, s);
    assert.equal(a.paused, false, `still playing after ${s}x`);
    assert.equal(a.playbackRate, s);
    assert.equal(a.defaultPlaybackRate, s); // some browsers fall back to the default rate on play()
    assert.equal(a.currentTime, 1.2, "no jump");
  }
  assert.equal(a.log.at(-1), "play@1.2x0.5");
});

test("changing speed while paused or after the end only sets the speed for the next play", async () => {
  const a = fakeAudio(0.4);
  a.paused = true;
  await changeSpeed(a, 0.5);
  assert.equal(a.paused, true);
  assert.equal(a.playbackRate, 0.5);
  assert.deepEqual(a.log, []);
});

test("a blocked play() after a speed change doesn't throw", async () => {
  const a = fakeAudio();
  a.play = () => Promise.reject(new Error("NotAllowedError"));
  await changeSpeed(a, 0.5);
  assert.equal(a.playbackRate, 0.5);
});

test("every new animation gets its own player, even for the same sentence (so it starts at 1x and plays again)", () => {
  const one = { run: 1, lang: "ko" as const, text: "정말 감사합니다." };
  assert.notEqual(playerKey(one), playerKey({ ...one, run: 2 }));
  assert.equal(playerKey(one), playerKey({ ...one }));
});

test("autoplay is on by default and remembered; blocked or empty storage means on", () => {
  assert.equal(AUTOPLAY_DEFAULT, true);
  const mem = new Map<string, string>();
  const store = { getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => void mem.set(k, v) };
  assert.equal(readAutoplay(store), true);
  saveAutoplay(store, false);
  assert.equal(readAutoplay(store), false);
  saveAutoplay(store, true);
  assert.equal(readAutoplay(store), true);
  const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.equal(readAutoplay(blocked), true);
  assert.doesNotThrow(() => saveAutoplay(blocked, false));
  assert.equal(readAutoplay(null), true);
});

test("Replay sits beside the speed buttons, never over the mouth picture", () => {
  const src = readFileSync(new URL("../components/NativeMouth.tsx", import.meta.url), "utf8");
  assert.ok(!src.includes("replay-overlay"), "no Replay overlay");
  assert.ok(!/absolute inset-0/.test(src), "nothing laid over the picture");
});
