// The page and the native mouth player, checked from their source: what's on screen and in which order.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { UI, tr } from "./i18n.ts";
import * as landing from "./landing.ts";

const src = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");
const mouth = src("../components/NativeMouth.tsx");
const page = src("../app/page.tsx");
const HANGUL = /[가-힣]/;

test("Play/Pause only plays and pauses; a separate Replay button sits right after it", () => {
  assert.match(mouth, /playing \? tr\("pause"\) : tr\("play"\)/);
  const play = mouth.indexOf('data-testid="play"');
  const replay = mouth.indexOf('data-testid="replay"');
  const speeds = mouth.indexOf("SPEEDS.map");
  assert.ok(play > 0 && replay > play && speeds > replay, "Play, then Replay, then the speeds");
});

test("no caption under the animation", () => {
  assert.ok(!mouth.includes("figcaption") && !mouth.includes("mouthCaption"));
  assert.ok(!("mouthCaption" in UI));
});

test("a small sound on/off button in the top-right corner of the animation box, in both site languages", () => {
  assert.match(mouth, /data-testid="sound"/);
  assert.match(mouth, /absolute right-\d+ top-\d+/);
  assert.match(mouth, /muted=\{muted\}/); // the clip itself
  assert.match(mouth, /if \(!muted\) playSlice/); // and the single sounds the timeline plays
  for (const k of ["soundOn", "soundOff"] as const) assert.ok(HANGUL.test(UI[k].ko), k);
});

test("'Show what matters' is now 'Placement tips', in English and Korean", () => {
  assert.equal(tr("en", "placementTips"), "Placement tips");
  assert.ok(HANGUL.test(tr("ko", "placementTips")));
  assert.ok(!("showKey" in UI));
  assert.match(mouth, /tr\("placementTips"\)/);
});

test("no sample sentences beside the box", () => {
  assert.ok(!page.includes('data-testid="samples"') && !page.includes("fetchPack"));
  for (const gone of ["SAMPLE_PACKS", "sampleLines", "sampleGroups", "findSample", "storedTranslation"])
    assert.ok(!(gone in landing), gone);
  for (const k of ["samplesTitle", "samplePick", "tabEn", "tabKo", "pack_Basics", "pack_Casual"]) assert.ok(!(k in UI), k);
});

test("no pack code left in the frontend", () => {
  const api = src("./api.ts");
  assert.ok(!/fetchPack|PackItem|PackSummary/.test(api));
  assert.ok(!existsSync(new URL("./tags.ts", import.meta.url)), "pack tag names");
  assert.ok(!/pickerPacks/.test(src("./devOnly.ts")));
});

test("no backend status line on the page (it was a developer aid); the backend is still woken on load", () => {
  assert.ok(!page.includes("BackendStatus"));
  assert.ok(!existsSync(new URL("../components/BackendStatus.tsx", import.meta.url)));
  for (const k of ["backendChecking", "backendConnected", "backendDown", "checkAgain"]) assert.ok(!(k in UI), k);
  assert.match(page, /checkHealth\(\)/);
});

// ---------- mixed English + Korean ----------
test("a mixed sentence hides Practice and says why, in both site languages", () => {
  assert.match(page, /practiceOffered\(shown\.lang\)/);
  assert.match(page, /t\("practiceMixed"\)/);
  assert.ok(HANGUL.test(UI.practiceMixed.ko));
  assert.ok(HANGUL.test(UI.langMix.ko));
  assert.equal(tr("en", "langMix"), "English + Korean");
});

test("the player looks each sound up in its own language's table", () => {
  assert.match(mouth, /soundsFromTimings\(native\.timings, articulation\.sounds\)/);
  assert.match(mouth, /descText\(ui, s\[0\]\.lang,/); // s = the sounds on screen
});

test("Korean Practice warns up front that nothing will be marked green or red yet", () => {
  assert.match(page, /gradingLive\(shown\.lang\) \? "practiceHint" : "practiceHintUngraded"/);
  for (const key of ["practiceHintUngraded", "nothingGraded"] as const) {
    assert.ok(UI[key], `${key} exists`);
    assert.match(tr("ko", key), HANGUL, `${key} has Korean`);
  }
  assert.match(tr("en", "practiceHintUngraded"), /Korean grading isn't ready yet/);
  assert.match(tr("en", "nothingGraded"), /green or red/);
});

// ---------- one button: Animate ----------
test("the box has one button, Animate, for English, Korean and mixed text alike", () => {
  for (const gone of ['data-testid="kr"', 'data-testid="kr-animate"', 'data-testid="kr-result"', "fetchTranslation", "FormalityLine", "casual"])
    assert.ok(!page.includes(gone), gone);
  for (const gone of ["translateOffered", "koreanToAnimate"]) assert.ok(!(gone in landing), gone);
  for (const k of ["translateKr", "translateKrAnimate", "errTranslate", "koreanFor", "casualLabel"]) assert.ok(!(k in UI), k);
  // Animate sends whatever was typed, in the language its letters show (en, ko or mix)
  assert.match(page, /fetchCustom\(typed\.trim\(\), lang\)/);
  assert.match(page, /t\("animate"\)/);
});

test("no 존댓말 / 반말 switch left (only English -> Korean translations had two forms)", () => {
  for (const f of ["../components/FormalitySwitch.tsx", "../components/FormalityLine.tsx", "./translations.ts", "./translations.test.ts"])
    assert.ok(!existsSync(new URL(f, import.meta.url)), f);
});

test("a typed Korean sentence still shows its English meaning", () => {
  assert.match(page, /<Translation text=\{shown\.text\}/);
});
