// The loading screen between Animate and the animation. Pure (no React), tested in loading.test.ts;
// components/LoadingScreen.tsx runs the clocks.
//
// The bar is a "fake determinate" bar: the backend can't report how far along it is, so the bar eases quickly up
// to a random stop between 88% and 98%, waits there, and fills smoothly to 100% once the real answer is in.
// It never claims to be finished before it is.

import { shuffleOrder, typeSteps } from "./home.ts";

// ---------- the bar ----------
export const CAP_MIN = 88;
export const CAP_MAX = 98;
export const FILL_MS = 1600; // 0 -> the cap
export const FINISH_MS = 450; // where it was -> 100, once the answer is in
export const DONE_HOLD_MS = 250; // 100% stays on screen this long before the animation shows

/** Where the fake fill stops: a whole number from 88 to 98, each equally likely. */
export function pickCap(rand: () => number = Math.random): number {
  return CAP_MIN + Math.min(CAP_MAX - CAP_MIN, Math.floor(rand() * (CAP_MAX - CAP_MIN + 1)));
}

const easeOut = (x: number) => 1 - Math.pow(1 - x, 3); // fast start, gentle stop

/** The bar `ms` after Animate, while the answer is still on its way: eases up to `cap`, then waits there. */
export function fakePct(ms: number, cap: number): number {
  const x = Math.min(1, Math.max(0, ms / FILL_MS));
  return x >= 1 ? cap : cap * easeOut(x);
}

/** The bar `ms` after the answer arrived, starting from wherever it was (`from`): smoothly up to 100. */
export function finishPct(from: number, ms: number): number {
  const x = Math.min(1, Math.max(0, ms / FINISH_MS));
  return x >= 1 ? 100 : from + (100 - from) * easeOut(x);
}

/** How full each of the 10 blocks is (0..1): block i covers i*10% .. (i+1)*10%. */
export function barFills(pct: number): number[] {
  return Array.from({ length: 10 }, (_, i) => Math.min(1, Math.max(0, (pct - i * 10) / 10)));
}

// ---------- Blueberry's poses ----------
export const POSES = ["nerd", "detective", "pencil", "painter", "reader", "sweeper"] as const;
export type Pose = (typeof POSES)[number];

/** A different pose from the one showing (each new line gets one). */
export function nextPose(current: Pose | null, rand: () => number = Math.random): Pose {
  const others = POSES.filter((p) => p !== current);
  return others[Math.min(others.length - 1, Math.floor(rand() * others.length))];
}

// ---------- the lines ----------
export type LoadingLine = { ko: string; en: string };

// Playful "what Blueberry is doing" lines about Korean sounds. Shown in both languages whatever the site language
// is: the Korean is typed, the English sits under it.
export const LOADING_LINES: LoadingLine[] = [
  { ko: "음절 쪼개는 중…", en: "Splitting syllables" },
  { ko: "받침 챙기는 중…", en: "Minding the final consonants" },
  { ko: "연음 이어 붙이는 중…", en: "Linking sounds across syllables" },
  { ko: "혀 자리 잡는 중…", en: "Placing the tongue" },
  { ko: "거센소리에 바람 넣는 중…", en: "Adding the puff to aspirated sounds" },
  { ko: "입술 모양 다듬는 중…", en: "Shaping the lips" },
  { ko: "된소리 힘주는 중…", en: "Tightening the tense sounds" },
  { ko: "모음 높낮이 재는 중…", en: "Measuring vowel height" },
  { ko: "비음화 살피는 중…", en: "Checking nasal assimilation" },
  { ko: "구개음화 찾는 중…", en: "Hunting for palatalization" },
  { ko: "경음화 확인하는 중…", en: "Checking for tensing" },
  { ko: "억양 고르는 중…", en: "Smoothing the intonation" },
  { ko: "자음 모음 줄 세우는 중…", en: "Lining up consonants and vowels" },
  { ko: "혀끝 튕기는 연습 중…", en: "Practicing the tongue-tip tap" },
  { ko: "성대 울림 확인하는 중…", en: "Checking the vocal cords" },
  { ko: "입천장 지도 그리는 중…", en: "Mapping the roof of the mouth" },
  { ko: "발음 기호 정리하는 중…", en: "Sorting the phonetic symbols" },
  { ko: "음소 하나하나 세는 중…", en: "Counting every sound" },
  { ko: "턱 높이 맞추는 중…", en: "Setting the jaw height" },
  { ko: "소리 길이 재는 중…", en: "Timing each sound" },
];

export const TICK_MS = 75; // one typing step
export const HOLD_TICKS = 18; // a finished line stays ~1.35 s (loading is short, so lines move on quickly)

/** Which shuffled line (`pos` into `order`), how many keystrokes into it, and Blueberry's pose for it. */
export type Lines = { order: number[]; pos: number; step: number; pose: Pose };

export function startLines(rand: () => number = Math.random): Lines {
  return { order: shuffleOrder(LOADING_LINES.length, -1, rand), pos: 0, step: 0, pose: nextPose(null, rand) };
}

/** One tick later: the next keystroke, the hold, then the next line with a new pose (after the 20th, a new shuffle). */
export function advanceLine(s: Lines, rand: () => number = Math.random): Lines {
  const step = s.step + 1;
  if (step < typeSteps(LOADING_LINES[s.order[s.pos]].ko).length + HOLD_TICKS) return { ...s, step };
  const pose = nextPose(s.pose, rand);
  if (s.pos + 1 < s.order.length) return { ...s, pos: s.pos + 1, step: 0, pose };
  return { order: shuffleOrder(LOADING_LINES.length, s.order[s.order.length - 1], rand), pos: 0, step: 0, pose };
}

/** The text on screen now; the gloss only once the line is fully typed. */
export function lineView(s: Lines) {
  const line = LOADING_LINES[s.order[s.pos]];
  const steps = typeSteps(line.ko);
  const k = Math.min(s.step, steps.length - 1);
  return { typed: steps[k], gloss: k === steps.length - 1 ? line.en : "" };
}
