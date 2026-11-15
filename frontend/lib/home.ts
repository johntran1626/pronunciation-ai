// The home page's speech bubble: Blueberry "types" short lines in the site language (Korean jamo by jamo, English
// letter by letter), each with the other language as a small gloss once it is typed. Pure (no React), tested in
// home.test.ts; components/TypedBubble.tsx runs the clock.
import type { Ui } from "./i18n.ts";

export const GITHUB_URL = "https://github.com/johntran1626";
export const LINKEDIN_URL: string | null = "https://www.linkedin.com/in/johnthientran/";

export type HomeLine = { ko: string; en: string; href?: string };

// Every line is shown in both languages: the site language is typed (big), the other sits under it (small).
export const HOME_LINES: HomeLine[] = [
  { ko: "좋아하는 드라마 대사 써 봐!", en: "Try a line from your favorite drama!" },
  { ko: "노래 가사 한 줄 넣어 봐!", en: "Drop in a line from a song!" },
  { ko: "오늘 점심 메뉴를 써 봐!", en: "Type what you had for lunch!" },
  { ko: "카페에서 주문하듯이 써 봐!", en: "Type it like you’re ordering at a café!" },
  { ko: "영어 문장도 괜찮아!", en: "English sentences work too!" },
  { ko: "한국어랑 영어 섞어도 돼!", en: "Mixing Korean and English is fine!" },
  { ko: "혀가 꼬이는 말 도전!", en: "Try a tongue twister!" },
  { ko: "친구한테 보낼 문자를 써 봐!", en: "Type a text you’d send a friend!" },
  { ko: "0.5배속으로 천천히 봐 봐!", en: "Watch it slowly at 0.5× speed!" },
  { ko: "소리 하나를 누르면 그 소리만 들려!", en: "Tap a sound to hear just that sound!" },
  { ko: "발음 위치 팁을 켜 봐!", en: "Turn on Placement tips!" },
  { ko: "다 보고 나면 직접 녹음해 봐!", en: "Done watching? Record yourself!" },
  { ko: "숫자도 읽어 줄게!", en: "I’ll read numbers out loud too!" },
  { ko: "짧은 문장이 제일 좋아!", en: "Short sentences work best!" },
  { ko: "인사말부터 시작해 볼까?", en: "Want to start with a greeting?" },
  { ko: "좋아하는 음식 이름을 써 봐!", en: "Type your favorite food!" },
  { ko: "길 물어보는 말 연습해 볼까?", en: "Practice asking for directions?" },
  { ko: "엔터만 눌러도 시작해!", en: "Just press Enter to start!" },
  { ko: "오늘 기분을 한 문장으로 써 봐!", en: "Sum up your mood in one sentence!" },
  { ko: "GitHub에서 날 찾아 줘! @johntran1626", en: "Find me on GitHub @johntran1626", href: GITHUB_URL },
  { ko: "링크드인에서 연결하자!", en: "Connect with me on LinkedIn!", ...(LINKEDIN_URL ? { href: LINKEDIN_URL } : {}) },
];

export const TICK_MS = 60; // one typing step
export const HOLD_TICKS = 45; // a finished line stays ~2.7 s
export const RETURN_TICKS = 8; // ~0.5 s: the carriage slides back (bubble empty) before a line is typed

const FIRST = 0xac00; // 가
const ONSETS = [..."ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"];

/** The side of a line that is typed (the site language) and the side shown under it once it is done. */
export const typedSide = (line: HomeLine, ui: Ui) => (ui === "ko" ? line.ko : line.en);
export const glossSide = (line: HomeLine, ui: Ui) => (ui === "ko" ? line.en : line.ko);

/** What the bubble shows after each keystroke: a block appears as its first consonant, then with its vowel,
 *  then (if it has one) with its final consonant, the way a Korean keyboard builds it. */
export function typeSteps(str: string): string[] {
  const out: string[] = [];
  let done = "";
  for (const ch of str) {
    const i = ch.codePointAt(0)! - FIRST;
    if (i >= 0 && i < 11172) {
      const onset = Math.floor(i / 588);
      const vowel = Math.floor((i % 588) / 28);
      out.push(done + ONSETS[onset]);
      out.push(done + String.fromCharCode(FIRST + onset * 588 + vowel * 28));
      if (i % 28) out.push(done + ch);
    } else {
      out.push(done + ch);
    }
    done += ch;
  }
  return out;
}

/** Every index 0..n-1 once, in random order (Fisher-Yates), never starting with `avoidFirst`. */
export function shuffleOrder(n: number, avoidFirst: number, rand: () => number = Math.random): number[] {
  const a = [...Array(n).keys()];
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  if (n > 1 && a[0] === avoidFirst) [a[0], a[1]] = [a[1], a[0]];
  return a;
}

/** Where the bubble is: which shuffled line (`pos` into `order`) and how many steps into it. */
export type Typing = { order: number[]; pos: number; step: number };

export function startTyping(n: number, rand: () => number = Math.random): Typing {
  return { order: shuffleOrder(n, -1, rand), pos: 0, step: 0 };
}

/** One tick later: the carriage return, the next keystroke, the hold, then the next line (after the last line, a
 *  new shuffle). Each line is RETURN_TICKS (carriage sliding back, bubble empty) + one tick per keystroke + the hold. */
export function advance(s: Typing, n: number, rand: () => number = Math.random, lines = HOME_LINES, ui: Ui = "ko"): Typing {
  const step = s.step + 1;
  if (step < RETURN_TICKS + typeSteps(typedSide(lines[s.order[s.pos]], ui)).length + HOLD_TICKS) return { ...s, step };
  if (s.pos + 1 < s.order.length) return { ...s, pos: s.pos + 1, step: 0 };
  return { order: shuffleOrder(n, s.order[s.order.length - 1], rand), pos: 0, step: 0 };
}

/** The text on screen now (empty while the carriage returns); the gloss only once the line is fully typed. */
export function view(s: Typing, lines: HomeLine[], ui: Ui = "ko") {
  const line = lines[s.order[s.pos]];
  const steps = typeSteps(typedSide(line, ui));
  const last = steps.length - 1;
  const returning = s.step < RETURN_TICKS;
  const k = s.step - RETURN_TICKS; // keystrokes so far (index into steps)
  const done = k >= last;
  // how far along the line the typing is, 0..1: where the typewriter's carriage sits
  const progress = returning ? 0 : last > 0 ? Math.min(1, k / last) : 1;
  const typed = returning ? "" : steps[Math.min(k, last)];
  return { typed, gloss: done ? glossSide(line, ui) : "", line, done, progress, returning };
}

export type TypingSound = "key" | "lever" | "return";

/** The typewriter sound for one tick: the carriage return as a line opens (the same tick the bubble clears),
 *  a click per keystroke, a soft lever click the tick after the line is finished, nothing while sliding or holding. */
export function soundFor(prev: Typing, next: Typing, lines: HomeLine[], ui: Ui = "ko"): TypingSound | null {
  if (next.pos !== prev.pos || (next.step === 0 && prev.step !== 0)) return "return"; // a new line (or a new shuffle)
  if (next.step === prev.step) return null;
  const last = typeSteps(typedSide(lines[next.order[next.pos]], ui)).length - 1;
  const k = next.step - RETURN_TICKS;
  if (k >= 0 && k <= last) return "key";
  if (k === last + 1) return "lever";
  return null;
}
