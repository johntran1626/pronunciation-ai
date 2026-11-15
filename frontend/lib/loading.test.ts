// The loading screen: the fake progress bar tied to the real answer, Blueberry's six poses, the 20 lines.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { UI, tr } from "./i18n.ts";
import { typeSteps } from "./home.ts";
import {
  CAP_MAX, CAP_MIN, FILL_MS, FINISH_MS, HOLD_TICKS, LOADING_LINES, POSES,
  advanceLine, barFills, fakePct, finishPct, lineView, nextPose, pickCap, startLines,
} from "./loading.ts";

const src = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");
const HANGUL = /[가-힣]/;

function seeded(seed: number) {
  return () => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed / 2147483648;
  };
}

// ---------- the fake bar ----------
test("the fake fill stops at a random whole number from 88 to 98, and every value in that range can come up", () => {
  assert.equal(CAP_MIN, 88);
  assert.equal(CAP_MAX, 98);
  assert.equal(pickCap(() => 0), 88);
  assert.equal(pickCap(() => 0.999999), 98);
  const seen = new Set<number>();
  const rand = seeded(7);
  for (let i = 0; i < 2000; i++) {
    const c = pickCap(rand);
    assert.ok(Number.isInteger(c) && c >= 88 && c <= 98, String(c));
    seen.add(c);
  }
  assert.equal(seen.size, 11);
});

test("the fake fill rises fast at first, reaches its cap at FILL_MS, then waits there (never past it)", () => {
  assert.equal(fakePct(0, 93), 0);
  assert.ok(fakePct(FILL_MS * 0.25, 93) > 93 * 0.5, "more than half way in the first quarter (ease-out)");
  let last = 0;
  for (let ms = 0; ms <= FILL_MS; ms += 20) {
    const p = fakePct(ms, 93);
    assert.ok(p >= last && p <= 93, `${ms}: ${p}`);
    last = p;
  }
  assert.equal(fakePct(FILL_MS, 93), 93);
  assert.equal(fakePct(60_000, 93), 93); // a slow answer: the bar waits at the cap
  assert.equal(fakePct(-50, 93), 0);
});

test("once the real answer arrives, the bar fills smoothly from where it was to 100", () => {
  assert.equal(finishPct(91, 0), 91);
  let last = 91;
  for (let ms = 0; ms <= FINISH_MS; ms += 10) {
    const p = finishPct(91, ms);
    assert.ok(p >= last && p <= 100, `${ms}: ${p}`);
    last = p;
  }
  assert.equal(finishPct(91, FINISH_MS), 100);
  assert.equal(finishPct(40, FINISH_MS * 10), 100); // a fast (cached) answer finishes from lower down
});

test("ten blocks: each fills by its own tenth, so the bar moves smoothly inside a block", () => {
  assert.deepEqual(barFills(0), [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
  assert.deepEqual(barFills(100), [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]);
  const at = barFills(88);
  assert.deepEqual(at.slice(0, 8), [1, 1, 1, 1, 1, 1, 1, 1]);
  assert.ok(Math.abs(at[8] - 0.8) < 1e-9);
  assert.equal(at[9], 0);
  assert.deepEqual(barFills(150), barFills(100));
  assert.deepEqual(barFills(-5), barFills(0));
});

// ---------- poses and lines ----------
test("six poses; a new line always brings a different pose", () => {
  assert.deepEqual([...POSES], ["nerd", "detective", "pencil", "painter", "reader", "sweeper"]);
  const rand = seeded(3);
  for (const p of POSES) for (let i = 0; i < 50; i++) {
    const n = nextPose(p, rand);
    assert.ok(POSES.includes(n) && n !== p);
  }
});

test("20 linguistics lines, each Korean ending in … with an English gloss", () => {
  assert.equal(LOADING_LINES.length, 20);
  for (const l of LOADING_LINES) {
    assert.ok(HANGUL.test(l.ko) && l.ko.endsWith("…"), l.ko);
    assert.ok(l.en.length > 0 && !HANGUL.test(l.en), l.en);
  }
  assert.equal(new Set(LOADING_LINES.map((l) => l.ko)).size, 20);
});

test("a line types jamo by jamo, its gloss shows once it's typed, it holds, then the next line (and pose) comes", () => {
  const rand = seeded(11);
  let s = startLines(rand);
  assert.equal(s.step, 0);
  assert.equal(new Set(s.order).size, 20);
  const steps = typeSteps(LOADING_LINES[s.order[0]].ko);
  assert.equal(lineView(s).typed, steps[0]);
  assert.equal(lineView(s).gloss, "");
  for (let i = 0; i < steps.length - 1; i++) s = advanceLine(s, rand);
  assert.equal(lineView(s).typed, LOADING_LINES[s.order[0]].ko);
  assert.equal(lineView(s).gloss, LOADING_LINES[s.order[0]].en);
  const pose = s.pose;
  for (let i = 0; i < HOLD_TICKS; i++) s = advanceLine(s, rand);
  assert.equal(s.pos, 0, "still holding");
  s = advanceLine(s, rand);
  assert.equal(s.pos, 1);
  assert.equal(s.step, 0);
  assert.notEqual(s.pose, pose);
});

test("after the 20th line a fresh shuffle starts, never repeating the line just shown", () => {
  const rand = seeded(5);
  let s = startLines(rand);
  let prev = -1;
  for (let guard = 0; guard < 100_000 && s.pos < 19; guard++) s = advanceLine(s, rand); // reach the 20th line
  assert.equal(s.pos, 19);
  prev = s.order[19];
  for (let guard = 0; guard < 100_000 && s.pos === 19; guard++) s = advanceLine(s, rand); // and past it
  assert.equal(s.pos, 0);
  assert.notEqual(s.order[0], prev);
  assert.equal(new Set(s.order).size, 20);
});

// ---------- the screen ----------
test("the loading screen: Blueberry in one of six poses, the bar with a %, the typed line + gloss", () => {
  assert.ok(existsSync(new URL("../components/LoadingScreen.tsx", import.meta.url)));
  const screen = src("../components/LoadingScreen.tsx");
  for (const p of POSES) assert.match(screen, new RegExp(`${p}:`), p);
  assert.match(screen, /<LoadingBar/);
  assert.match(screen, /lang="ko"/);
  assert.match(screen, /gloss/);
  assert.match(screen, /prefers-reduced-motion/);
});

test("the bar is all blue (no pink), a real progressbar with a bilingual label and the % next to it", () => {
  const bar = src("../components/LoadingBar.tsx");
  assert.match(bar, /role="progressbar"/);
  assert.match(bar, /aria-valuenow/);
  assert.match(bar, /bg-blue/);
  assert.ok(!/pink|FF85B8|blush/i.test(bar), "no pink in the bar");
  assert.match(bar, /t\("loadingLabel"\)/);
  assert.ok(HANGUL.test(tr("ko", "loadingLabel")));
});

test("each pose has a bilingual label", () => {
  for (const k of ["poseNerd", "poseDetective", "posePencil", "posePainter", "poseReader", "poseSweeper"] as const) {
    assert.ok(k in UI, k);
    assert.ok(HANGUL.test(tr("ko", k)), k);
    assert.ok(!HANGUL.test(tr("en", k).replace(/ㅎㅇ|한들/g, "")), k);
  }
});

test("the page: Animate shows the loading screen (home hidden, kept) until the sentence, its clip and the card data are all in", () => {
  const page = src("../app/page.tsx");
  assert.match(page, /<LoadingScreen/);
  assert.match(page, /loadNativeClip\(/);
  assert.match(page, /loadCardData\(/);
  assert.match(page, /hidden=\{busy\}|hidden=\{loading !== null\}/); // the box keeps its text and isn't refocused
  assert.match(page, /onFinished=/); // the result appears only after the bar reaches 100
});

test("the loading loops have their own names and stop when motion is reduced", () => {
  const css = src("../app/globals.css");
  for (const c of ["ld-bob", "ld-tap", "ld-shadow", "ld-search", "ld-pen", "ld-brush", "ld-read", "ld-flip", "ld-swing", "ld-dust"]) {
    assert.match(css, new RegExp(`\\.${c}\\b`), c);
  }
  const reduced = css.slice(css.indexOf("prefers-reduced-motion"));
  assert.match(reduced, /\.ld-bob/);
  assert.match(reduced, /\.ld-pen/);
});
