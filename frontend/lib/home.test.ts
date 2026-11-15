// The home page look: theme, fonts, header, mascot, the typed-lines bubble and the Animate button.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { UI, tr } from "./i18n.ts";
import {
  GITHUB_URL, HOLD_TICKS, HOME_LINES, LINKEDIN_URL, RETURN_TICKS, advance, shuffleOrder, soundFor, startTyping, typeSteps, view,
} from "./home.ts";

const src = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");
const HANGUL = /[가-힣]/;

// a fixed "random" source, so shuffles are repeatable
function seeded(seed: number) {
  return () => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed / 2147483648;
  };
}

// ---------- jamo-by-jamo typing ----------
test("a Hangul block types as onset, then onset + vowel, then the full block", () => {
  assert.deepEqual(typeSteps("한"), ["ㅎ", "하", "한"]);
  assert.deepEqual(typeSteps("가"), ["ㄱ", "가"]); // no final consonant: two steps
  assert.deepEqual(typeSteps("한글"), ["ㅎ", "하", "한", "한ㄱ", "한그", "한글"]);
});

test("anything that isn't a Hangul block types in one step", () => {
  assert.deepEqual(typeSteps("가 @a!"), ["ㄱ", "가", "가 ", "가 @", "가 @a", "가 @a!"]);
});

// ---------- the 21 lines ----------
test("21 lines, each Korean with an English gloss", () => {
  assert.equal(HOME_LINES.length, 21);
  for (const l of HOME_LINES) {
    assert.ok(HANGUL.test(l.ko), l.ko);
    assert.ok(l.en.length > 0 && !HANGUL.test(l.en), l.en);
  }
});

test("the GitHub line links to the GitHub profile; the LinkedIn line links once the URL is set", () => {
  assert.equal(GITHUB_URL, "https://github.com/johntran1626");
  const gh = HOME_LINES.filter((l) => l.en.includes("GitHub"));
  assert.equal(gh.length, 1);
  assert.equal(gh[0].href, GITHUB_URL);
  const li = HOME_LINES.filter((l) => l.en.includes("LinkedIn"));
  assert.equal(li.length, 1);
  assert.equal(li[0].href, LINKEDIN_URL ?? undefined);
  if (LINKEDIN_URL) assert.match(LINKEDIN_URL, /^https:\/\/(www\.)?linkedin\.com\/in\//);
  assert.equal(HOME_LINES.filter((l) => l.href).length, LINKEDIN_URL ? 2 : 1, "no other line is a link");
});

// ---------- shuffled order ----------
test("a shuffle uses every line once and never repeats the line just shown", () => {
  const rand = seeded(7);
  for (let avoid = 0; avoid < 21; avoid++) {
    const order = shuffleOrder(21, avoid, rand);
    assert.deepEqual([...order].sort((a, b) => a - b), [...Array(21).keys()]);
    assert.notEqual(order[0], avoid);
  }
});

test("typing: each line opens with the carriage return (empty bubble), then types, holds, and moves on", () => {
  const rand = seeded(3);
  let s = startTyping(HOME_LINES.length, rand);
  const first = HOME_LINES[s.order[0]];
  const steps = typeSteps(first.ko);
  const tick = (n: number) => { for (let i = 0; i < n; i++) s = advance(s, HOME_LINES.length, rand); };
  assert.equal(view(s, HOME_LINES).typed, "", "the bubble is empty while the carriage slides back");
  assert.equal(view(s, HOME_LINES).returning, true);
  tick(RETURN_TICKS - 1);
  assert.equal(view(s, HOME_LINES).typed, "");
  tick(1);
  assert.equal(view(s, HOME_LINES).returning, false);
  assert.equal(view(s, HOME_LINES).typed, steps[0], "typing starts once the carriage is home");
  assert.equal(view(s, HOME_LINES).gloss, "", "no gloss while typing");
  tick(steps.length - 1);
  assert.equal(view(s, HOME_LINES).typed, first.ko);
  assert.equal(view(s, HOME_LINES).gloss, first.en, "gloss once the line is typed");
  tick(HOLD_TICKS);
  assert.equal(s.pos, 0, "still holding");
  tick(1);
  assert.equal(s.pos, 1, "the next line: bubble clears and the carriage returns on the same tick");
  assert.equal(view(s, HOME_LINES).typed, "");
  assert.equal(view(s, HOME_LINES).progress, 0);
  // jump to the last line and run it out
  const last = s.order[20];
  s = { ...s, pos: 20, step: 0 };
  tick(RETURN_TICKS + typeSteps(HOME_LINES[last].ko).length + HOLD_TICKS);
  assert.equal(s.pos, 0);
  assert.notEqual(s.order[0], last);
});

test("view of a finished step count shows the whole line (used when motion is reduced)", () => {
  const s = { order: [4], pos: 0, step: Number.MAX_SAFE_INTEGER };
  assert.equal(view(s, HOME_LINES).typed, HOME_LINES[4].ko);
  assert.equal(view(s, HOME_LINES).gloss, HOME_LINES[4].en);
  assert.equal(view(s, HOME_LINES).line, HOME_LINES[4]);
});

// ---------- the look ----------
test("fonts: Jua (display) and Outfit (text) via next/font; Geist is gone", () => {
  const layout = src("../app/layout.tsx");
  assert.match(layout, /import \{[^}]*Jua[^}]*\} from "next\/font\/google"/);
  assert.match(layout, /import \{[^}]*Outfit[^}]*\} from "next\/font\/google"/);
  assert.ok(!layout.includes("Geist"));
});

test("theme tokens for the approved palette; light only; reduced motion stops every loop", () => {
  const css = src("../app/globals.css");
  for (const [name, hex] of [["ink", "#111111"], ["sky", "#DCE8FF"], ["blue", "#2F6BFF"], ["pink", "#FF85B8"],
    ["blush", "#FF9CC2"], ["grid", "#FFD3E5"], ["tray", "#F4F8FF"]])
    assert.match(css, new RegExp(`--color-${name}:\\s*${hex}`, "i"), name);
  assert.match(css, /--font-display:/);
  assert.match(css, /@custom-variant dark/); // the design is light only: dark: classes never switch on
  assert.ok(!css.includes("prefers-color-scheme: dark"));
  const reduced = css.slice(css.indexOf("prefers-reduced-motion: reduce"));
  assert.ok(css.includes("prefers-reduced-motion: reduce"));
  for (const c of [".bob", ".blink", ".talk", ".caret", ".ground"]) assert.ok(reduced.includes(c), c);
});

test("the header: small GitHub / LinkedIn links on the left, the ENG / 한 switch on the right; title + byline in the page", () => {
  const page = src("../app/page.tsx");
  const header = page.slice(page.indexOf("<header"), page.indexOf("</header>"));
  assert.match(header, /<SocialLinks \/>[\s\S]*<UiToggle \/>/, "links top-left, ENG / 한 top-right");
  assert.ok(!header.includes("t("), "no other text in the header");
  assert.match(page, /<h1[\s\S]*t\("brand"\)[\s\S]*t\("byline"\)[\s\S]*<\/h1>/);
  assert.equal(tr("en", "byline"), "by John Tran");
  assert.ok(HANGUL.test(tr("ko", "byline")));
});

test("Blueberry, the mascot: its own component with a bilingual label, on the page", () => {
  assert.ok(existsSync(new URL("../components/Blueberry.tsx", import.meta.url)));
  const b = src("../components/Blueberry.tsx");
  assert.match(b, /t\("mascotLabel"\)/);
  for (const c of ["bob", "blink", "talk"]) assert.ok(b.includes(c), c);
  assert.ok(HANGUL.test(UI.mascotLabel.ko));
  assert.match(src("../components/TypewriterBlueberry.tsx"), /className="blink"/);
});

test("the typed-lines bubble: pauses on hover, static when motion is reduced, links open in a new tab", () => {
  assert.ok(existsSync(new URL("../components/TypedBubble.tsx", import.meta.url)));
  const b = src("../components/TypedBubble.tsx");
  assert.match(b, /prefers-reduced-motion: reduce/);
  assert.match(b, /onMouseEnter/);
  assert.match(b, /target="_blank"/);
  assert.match(b, /rel="noopener noreferrer"/);
  assert.match(src("../app/page.tsx"), /useTypedLines\(/);
});

test("the box: 원고지 grid, the language hint above the text, Animate in the display font with an arrow", () => {
  const page = src("../app/page.tsx");
  assert.match(page, /wongoji/);
  assert.equal(tr("en", "langEither"), "English, Korean, or both");
  assert.ok(HANGUL.test(tr("ko", "langEither")));
  assert.equal(tr("en", "animate"), "Animate"); // the arrow is an icon now, not text
  assert.ok(!tr("ko", "animate").includes("→"));
  const go = page.slice(page.indexOf('data-testid="go"') - 600, page.indexOf('data-testid="go"') + 400);
  assert.match(go, /font-display/);
  assert.match(go, /<svg/);
});

test("no Enter-key hint line under the button", () => {
  assert.ok(!("enterHint" in UI));
  assert.ok(!src("../app/page.tsx").includes("Shift + Enter"));
});

// ---------- Blueberry at the typewriter ----------
test("progress through the line: 0 while returning and at the first keystroke, 1 once typed (the carriage position)", () => {
  const steps = typeSteps(HOME_LINES[2].ko).length;
  const at = (step: number) => view({ order: [2], pos: 0, step: RETURN_TICKS + step }, HOME_LINES).progress;
  assert.equal(view({ order: [2], pos: 0, step: 0 }, HOME_LINES).progress, 0);
  assert.equal(at(0), 0);
  assert.ok(at(Math.floor(steps / 2)) > 0.3 && at(Math.floor(steps / 2)) < 0.7);
  assert.equal(at(steps - 1), 1);
  assert.equal(at(steps + 10), 1, "stays at the end while the line is held");
});

test("typing sounds: the carriage return as a line opens, a key click per keystroke, a ding when the line is done", () => {
  const L = typeSteps(HOME_LINES[0].ko).length;
  const R = RETURN_TICKS;
  const s = (pos: number, step: number) => ({ order: [0, 1], pos, step });
  assert.equal(soundFor(s(0, L + R + HOLD_TICKS), s(1, 0), HOME_LINES), "return");
  assert.equal(soundFor(s(0, 1), s(0, 2), HOME_LINES), null, "quiet while the carriage slides");
  assert.equal(soundFor(s(0, R - 1), s(0, R), HOME_LINES), "key", "the first keystroke");
  assert.equal(soundFor(s(0, R + L - 2), s(0, R + L - 1), HOME_LINES), "key", "the last keystroke");
  assert.equal(soundFor(s(0, R + L - 1), s(0, R + L), HOME_LINES), "ding");
  assert.equal(soundFor(s(0, R + L + 5), s(0, R + L + 6), HOME_LINES), null, "silent while the line is held");
});

test("the home mascot: Blueberry in round glasses at a typewriter whose carriage follows the typing", () => {
  const page = src("../app/page.tsx");
  assert.match(page, /<TypewriterBlueberry/);
  const tw = src("../components/TypewriterBlueberry.tsx");
  assert.match(tw, /t\("typewriterLabel"\)/);
  assert.equal((tw.match(/<circle[^>]*r="13"/g) ?? []).length, 2, "two round lenses");
  assert.match(tw, /progress/); // the carriage slides with the typing
  assert.match(tw, /data-testid="carriage"/);
  assert.ok(HANGUL.test(UI.typewriterLabel.ko));
});

test("typing sounds: made in the browser (Web Audio, no files), quiet once the visitor types or a result shows, and a remembered on/off", () => {
  const snd = src("./typingSound.ts");
  assert.match(snd, /AudioContext/);
  const page = src("../app/page.tsx");
  assert.match(page, /const typingSound = !typed && !shown/);
  assert.match(page, /typingSound=\{typingSound\}/);
  const tw = src("../components/TypewriterBlueberry.tsx");
  assert.match(tw, /aria-pressed/);
  assert.match(tw, /localStorage/);
  for (const k of ["typingSoundOn", "typingSoundOff"] as const) assert.ok(HANGUL.test(UI[k].ko), k);
});

// ---------- info icons ----------
test("an info icon beside Autoplay and beside Placement tips: hover, focus or tap shows what the switch does", () => {
  assert.ok(existsSync(new URL("../components/InfoTip.tsx", import.meta.url)));
  const tip = src("../components/InfoTip.tsx");
  for (const ev of ["onMouseEnter", "onFocus", "onClick"]) assert.match(tip, new RegExp(ev), ev);
  assert.match(tip, /role="tooltip"/);
  assert.match(tip, /aria-describedby/);
  assert.match(src("../app/page.tsx"), /<InfoTip text=\{t\("autoplayInfo"\)\}/);
  assert.match(src("../components/NativeMouth.tsx"), /<InfoTip text=\{tr\("placementInfo"\)\}/);
  for (const k of ["autoplayInfo", "placementInfo", "infoAbout"] as const) assert.ok(HANGUL.test(UI[k].ko), k);
});

test("the bubble: a KakaoTalk-style chat bubble (yellow, no border, no shadow, small hooked tail) on phone and desktop", () => {
  const b = src("../components/TypedBubble.tsx");
  const css = src("../app/globals.css");
  assert.match(css, /--color-kakao: #FFEE8C;/);
  assert.ok(!/Cloud|BUMPS|thought-dots/.test(b), "the cloud is gone");
  assert.match(b, /bg-kakao/);
  assert.match(b, /fill="#FFEE8C"/); // the tail, same yellow
  assert.ok(!/border-ink|shadow-pop|rotate-45/.test(b), "no black outline, no offset shadow, no square tail");
  assert.match(b, /tail === "down"/); // desktop: the tail points down at Blueberry; phone: right
});

test("GitHub and LinkedIn links in the top-left corner: small icons, new tab, bilingual labels", () => {
  assert.equal(LINKEDIN_URL, "https://www.linkedin.com/in/johnthientran/");
  const c = src("../components/SocialLinks.tsx");
  assert.match(c, /href=\{GITHUB_URL\}/);
  assert.match(c, /href=\{LINKEDIN_URL\}/);
  assert.equal((c.match(/target="_blank"/g) ?? []).length, 1, "one shared link style");
  assert.match(c, /rel="noopener noreferrer"/);
  for (const k of ["githubLink", "linkedinLink"] as const) {
    assert.match(c, new RegExp(`t\\("${k}"\\)`), k);
    assert.ok(HANGUL.test(UI[k].ko), k);
  }
});
