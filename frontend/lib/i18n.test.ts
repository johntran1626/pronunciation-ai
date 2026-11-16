// The ENG / 한 switch: every piece of site text, tip and sound description exists in both languages.
// The Korean text is machine-written and not yet checked by a native speaker.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DEFAULT_UI, UI, descText, problemText, say, tipText } from "./i18n.ts";
import { caption, airflowPhrases } from "./mouthViews.ts";
import { callout, geometry, VIEW, textWidth } from "./mouth.ts";

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf8"));
const tips = read("../../content/tips.json").tips;
const sounds = read("../../content/articulation.json").sounds;
const HANGUL = /[가-힣]/;
const slots = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

test("the site opens in English", () => {
  assert.equal(DEFAULT_UI, "en");
});

test("every site string has a Korean version with the same {slots}", () => {
  for (const [key, v] of Object.entries(UI)) {
    assert.ok(v.en && v.ko, key);
    assert.ok(HANGUL.test(v.ko), `${key}: no Hangul in "${v.ko}"`);
    assert.deepEqual(slots(v.ko), slots(v.en), key);
  }
});

test("every tip has Korean labels, a what-happened line with the {word} slot, and a tip", () => {
  for (const lang of ["en", "ko"] as const)
    for (const [id, t] of Object.entries<{ produced_label: string | null; what_happened: string; tip: string; target_label: string }>(tips[lang])) {
      const k = tipText("ko", lang, id, t);
      assert.ok(HANGUL.test(k.what_happened) && k.what_happened.includes("{word}"), `${lang} ${id}`);
      assert.ok(HANGUL.test(k.tip), `${lang} ${id} tip`);
      assert.ok(k.target_label, `${lang} ${id} target_label`);
      assert.equal(k.produced_label === null, t.produced_label === null, `${lang} ${id} produced_label`);
      assert.deepEqual(tipText("en", lang, id, t), t); // English stays exactly what tips.json says
    }
});

test("every sound has a Korean description, and none repeats an unverified claim", () => {
  for (const lang of ["en", "ko"] as const)
    for (const [ipa, e] of Object.entries<{ description: string }>(sounds[lang])) {
      const k = descText("ko", lang, ipa, e.description);
      assert.ok(HANGUL.test(k), `${lang} ${ipa}`);
      assert.ok(!/UNVERIFIED/i.test(k), `${lang} ${ipa}`);
      assert.equal(descText("en", lang, ipa, e.description), e.description);
    }
});

test("every phrase the mouth pictures can show (captions, callouts, puffs) has a Korean version", () => {
  const strict = (p: string) => { const k = say("ko")(p); assert.ok(HANGUL.test(k), `missing Korean for "${p}"`); return k; };
  for (const p of airflowPhrases) strict(p.trim().replace(/^, /, ""));
  for (const lang of ["en", "ko"] as const)
    for (const e of Object.values<{ svg: never; kind: string; lips: string }>(sounds[lang])) {
      caption(e as never, strict);
      const c = callout(e as never, geometry(e.svg, e.kind, e.lips));
      if (c) strict(c.text);
    }
});

test("Korean callouts still fit inside the picture (Hangul is wider than Latin letters)", () => {
  for (const lang of ["en", "ko"] as const)
    for (const e of Object.values<{ svg: never; kind: string; lips: string }>(sounds[lang])) {
      const c = callout(e as never, geometry(e.svg, e.kind, e.lips), say("ko"));
      if (!c) continue;
      assert.ok(c.textAt.x >= VIEW.x + 2 && c.textAt.x + textWidth(c.text) <= VIEW.x + VIEW.w - 2, c.text);
    }
});


test("typing problems in both languages", () => {
  assert.equal(problemText("en", "  "), "Type a sentence first.");
  assert.ok(HANGUL.test(problemText("ko", "")!));
  assert.ok(HANGUL.test(problemText("ko", "a".repeat(81))!) && problemText("ko", "a".repeat(81))!.includes("81"));
  assert.equal(problemText("ko", "hello"), null);
});
