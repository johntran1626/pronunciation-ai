// The playing screen (approved design rows D phone + E desktop): sentence on top, the mouth card beside Blueberry's
// sound tip, Placement tips, Animate another and Practice; the timeline (words, sounds, scrubber) with the controls
// under it; speeds 1x and 0.5x only. Checked from the source plus the pure helpers in lib/player.ts.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { UI, tr } from "./i18n.ts";
import { SPEEDS, scrubFill, speedLabel } from "./player.ts";

const src = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");
const mouth = src("../components/NativeMouth.tsx");
const page = src("../app/page.tsx");
const HANGUL = /[가-힣]/;

test("two speeds only, 1x and 0.5x, labelled 1× and .5×", () => {
  assert.deepEqual(SPEEDS, [1, 0.5]);
  assert.deepEqual(SPEEDS.map(speedLabel), ["1×", ".5×"]);
  assert.match(mouth, /speedLabel\(s\)/);
});

test("the scrubber's pink fill ends at the middle of the current sound's cell", () => {
  assert.equal(scrubFill(0, 10), 5);
  assert.equal(scrubFill(9, 10), 95);
  assert.equal(scrubFill(0, 1), 50);
  assert.equal(scrubFill(0, 0), 0); // no frames yet
});

test("timeline order: the words, then the sounds, then the scrubber; the controls come after all three", () => {
  const words = mouth.indexOf('data-testid="words"');
  const sounds = mouth.indexOf('data-testid="frames"');
  const bar = mouth.indexOf('type="range"');
  const play = mouth.indexOf('data-testid="play"');
  assert.ok(words > 0 && sounds > words && bar > sounds, "words, sounds, scrubber");
  assert.ok(play > bar, "Pause / Replay / speeds under the timeline");
});

test("words after the first are set off by a dashed line; the word being said is shaded", () => {
  assert.match(mouth, /border-dashed/);
  assert.match(mouth, /i === word \? "bg-sky"/);
});

test("Blueberry sits beside the sound tip bubble (IPA + plain-words description, both site languages)", () => {
  assert.match(mouth, /<Blueberry /);
  assert.match(mouth, /data-testid="now"/);
  assert.match(mouth, /descText\(ui, s\[0\]\.lang,/);
  assert.match(mouth, /\{tip\(shown\)\}/);
});

test("Placement tips is a switch, like Autoplay", () => {
  assert.match(mouth, /role="switch"[\s\S]{0,200}data-testid="show-key"/);
});

test("phone: one column (mouth, tip, timeline, then the buttons); desktop: mouth left, tip + buttons right, timeline under both", () => {
  assert.match(mouth, /actions\?: ReactNode/);
  assert.match(mouth, /\[grid-template-areas:'mouth'_'side'_'timeline'_'actions'\]/);
  assert.match(mouth, /lg:\[grid-template-areas:'mouth_side'_'mouth_actions'_'timeline_timeline'\]/);
  for (const area of ["mouth", "side", "timeline", "actions"]) assert.match(mouth, new RegExp(`\\[grid-area:${area}\\]`), area);
});

test("Animate another (both site languages) sits above Practice and goes back to an empty, focused box", () => {
  assert.equal(tr("en", "animateAnother"), "Animate another");
  assert.ok(HANGUL.test(UI.animateAnother.ko));
  const another = page.indexOf('data-testid="another"');
  const practice = page.indexOf('data-testid="practice"');
  assert.ok(another > 0 && practice > another, "Animate another, then Practice");
  assert.match(page, /function another\(\)/);
  assert.match(page, /setTyped\(""\)/);
  assert.match(page, /box\.current\?\.focus\(\)/);
});

test("a Home button (both site languages) sits just left of ENG/한 and does what Animate another does, even mid-loading", () => {
  assert.equal(tr("en", "home"), "Home");
  assert.ok(HANGUL.test(UI.home.ko));
  const header = page.slice(page.indexOf("<header"), page.indexOf("</header>"));
  const home = header.indexOf('data-testid="home"');
  assert.ok(home > 0 && header.indexOf("<UiToggle") > home, "Home, then ENG/한");
  assert.match(header, /onClick=\{another\}/);
  // going home while the loading screen is up drops that request, so its answer never pops up later
  const another = page.slice(page.indexOf("function another()"), page.indexOf("function openPractice()"));
  assert.match(another, /setBusy\(false\)/);
  assert.match(another, /request\.current\+\+/);
  assert.match(page, /if \(id !== request\.current\) return/);
});

test("the playing screen replaces the home (like the loading screen), and the recorder opens full width under the player", () => {
  assert.match(page, /hidden=\{busy \|\| shown !== null\}/);
  const player = page.indexOf("<NativeMouth");
  const recorder = page.indexOf("<Recorder");
  assert.ok(player > 0 && recorder > player, "the recorder comes after the player, not inside its button column");
});
