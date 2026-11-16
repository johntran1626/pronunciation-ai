// The native mouth player: speed changes at once at any moment, a fresh 1x player for every new animation, the autoplay
// setting, and Replay kept beside the speed buttons (never over the picture).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { AUTOPLAY_DEFAULT, END_PAD, SPEEDS, applySpeed, playEnd, playerKey, readAutoplay, saveAutoplay, type Media } from "./player.ts";
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

test("changing speed mid-audio takes effect at once: no pause, no seek, however fast it's clicked", () => {
  const a = fakeAudio(1.2);
  for (const s of [0.5, 1, 0.5, 1, 0.5, 1]) {
    applySpeed(a, s);
    assert.equal(a.paused, false, `still playing after ${s}x`);
    assert.equal(a.playbackRate, s);
    assert.equal(a.defaultPlaybackRate, s); // some browsers fall back to the default rate on play()
    assert.equal(a.currentTime, 1.2, "no jump");
  }
  assert.deepEqual(a.log, [], "never paused or restarted, so no click is lost to a half-finished restart");
});

test("changing speed while paused or after the end sets the speed for the next play", () => {
  const a = fakeAudio(0.4);
  a.paused = true;
  applySpeed(a, 0.5);
  assert.equal(a.paused, true);
  assert.equal(a.playbackRate, 0.5);
  assert.equal(a.defaultPlaybackRate, 0.5);
  assert.deepEqual(a.log, []);
});

test("if the browser puts back an old speed (on play, replay or the end), the chosen one is restored", () => {
  const a = fakeAudio();
  applySpeed(a, 1);
  a.playbackRate = 0.5; // the stale rate a browser kept from before
  assert.equal(applySpeed(a, 1), true, "reports that it had to fix the rate");
  assert.equal(a.playbackRate, 1);
  assert.equal(applySpeed(a, 1), false, "already right: touches nothing (safe to call every frame)");
});

test("the player keeps the chosen speed on the clip: on every click, before and after play(), and every frame", () => {
  const src = readFileSync(new URL("../components/NativeMouth.tsx", import.meta.url), "utf8");
  assert.ok(!src.includes("changeSpeed"), "the old pause / seek / play switch is gone");
  assert.match(src, /speedNow\.current = s/, "the click updates the speed the clock reads");
  assert.ok((src.match(/applySpeed\(/g) ?? []).length >= 4, "click, before play, after play, every frame");
  assert.match(src, /onPlaying=\{/, "re-applied once sound actually starts");
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

// the TTS file has up to ~1 s of silence after the last sound: the player stops (Play comes back) when the voice does
test("playback ends just after the last sound, not at the end of the padded file", () => {
  // "Testing": sounds end at 0.72 s, the file runs to 1.82 s
  assert.equal(playEnd([0.31, 0.72, 0.55], 1.82), 0.72 + END_PAD);
  assert.ok(END_PAD > 0 && END_PAD <= 0.1);
});

test("playback never ends past the file, and a clip with no sounds plays to its end", () => {
  assert.equal(playEnd([1.8], 1.82), 1.82);
  assert.equal(playEnd([], 1.82), 1.82);
});

test("the player stops at playEnd on every frame, and Play restarts from the top once there", () => {
  const src = readFileSync(new URL("../components/NativeMouth.tsx", import.meta.url), "utf8");
  assert.match(src, /playEnd\(/);
  assert.doesNotMatch(src, /clip\.duration - 0\.01/);
});
