// The Development tab at the top of the site (the long write-up). Every piece of text exists in English and Korean, every figure file exists, and the chart numbers match the
// results files they come from.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { TABS, activeTab } from "./tabs.ts";
import { UI } from "./i18n.ts";
import { SECTIONS, type Block, type L } from "./development.ts";
import { BASELINE_VS_APP, FINETUNE_PER, R_MARGIN_SWEEP } from "./devCharts.ts";

const HANGUL = /[가-힣]/;
const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf8"));
const both = (l: L, where: string) => {
  assert.ok(l.en.trim() && l.ko.trim(), `${where}: empty`);
  assert.ok(HANGUL.test(l.ko), `${where}: no Hangul in the Korean version`);
};
// pieces of text a block carries, so each can be checked the same way
function texts(b: Block): L[] {
  if (b.kind === "p") return [b.text];
  if (b.kind === "list") return b.items;
  if (b.kind === "figure") return [b.alt, b.caption];
  return [b.caption];
}

test("one tab, Development, with a bilingual label", () => {
  assert.deepEqual(TABS.map((t) => t.href), ["/development"]);
  for (const t of TABS) assert.ok(t.label in UI, t.label);
});

test("activeTab picks the tab whose page is open, and none on the home page", () => {
  assert.equal(activeTab("/development"), "/development");
  assert.equal(activeTab("/development/"), "/development");
  assert.equal(activeTab("/how-it-works"), null);
  assert.equal(activeTab("/"), null);
});

test("Development: every heading and block is in English and Korean, with unique section ids", () => {
  const ids = SECTIONS.map((s) => s.id);
  assert.equal(new Set(ids).size, ids.length);
  for (const s of SECTIONS) {
    assert.match(s.id, /^[a-z0-9-]+$/);
    both(s.heading, s.id);
    assert.ok(s.blocks.length > 0, s.id);
    s.blocks.forEach((b, i) => texts(b).forEach((l) => both(l, `${s.id}[${i}]`)));
  }
});

test("Development is a long write-up", () => {
  const words = SECTIONS.flatMap((s) => s.blocks.flatMap(texts)).map((l) => l.en.split(/\s+/).length).reduce((a, b) => a + b, 0);
  assert.ok(words >= 3000, `Development has ${words} words`);
});

test("the page title is just Development, with no subtitle", () => {
  assert.equal(UI.devTitle.en, "Development");
  assert.ok(!("devIntro" in UI));
});

test("the opening is one short paragraph about the concept", () => {
  const first = SECTIONS[0];
  assert.equal(first.blocks.length, 1);
  assert.notEqual(first.heading.en, "The idea");
});

test("the false-alarm rule is brief, under a short title", () => {
  const rule = SECTIONS.find((s) => s.id === "false-alarms-first");
  assert.ok(rule, "section exists");
  assert.ok(rule.heading.en.split(" ").length <= 4, rule.heading.en);
  const words = rule.blocks.flatMap(texts).map((l) => l.en.split(/\s+/).length).reduce((a, b) => a + b, 0);
  assert.ok(words <= 120, `${words} words`);
});

test("every section heading is four words or fewer", () => {
  for (const s of SECTIONS) assert.ok(s.heading.en.split(/\s+/).length <= 4, s.heading.en);
});

test("the sections end with Limitations; no lessons section", () => {
  assert.equal(SECTIONS.at(-1)?.heading.en, "Limitations");
  assert.ok(!SECTIONS.some((s) => s.id === "lessons"));
});

test("no colons anywhere in the write-up or its charts, in either language", () => {
  const all = SECTIONS.flatMap((s) => [s.heading, ...s.blocks.flatMap(texts)]);
  const charts = [R_MARGIN_SWEEP, BASELINE_VS_APP, FINETUNE_PER].flatMap((c) =>
    Object.values(c).flatMap((v) => (Array.isArray(v) ? v.map((r) => r.label).filter(Boolean) : [v])))
    .filter((v): v is L => typeof v === "object" && v !== null && "en" in v);
  for (const l of [...all, ...charts]) {
    assert.ok(!l.en.includes(":"), l.en);
    assert.ok(!l.ko.includes(":"), l.ko);
  }
  const src = readFileSync(new URL("../components/DevChart.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(src, /\$\{[^}]*\}: |\]\}: \{|": "/, "chart tooltips show no colons either");
});

test("every figure file is in public/ and has its real size, so the page doesn't jump while it loads", () => {
  for (const b of SECTIONS.flatMap((s) => s.blocks)) {
    if (b.kind !== "figure") continue;
    const url = new URL(`../public${b.src}`, import.meta.url);
    assert.ok(existsSync(url), b.src);
    const png = readFileSync(url);
    assert.equal(png.readUInt32BE(16), b.width, `${b.src} width`);
    assert.equal(png.readUInt32BE(20), b.height, `${b.src} height`);
  }
});

test("each chart named in the write-up exists", () => {
  const charts = SECTIONS.flatMap((s) => s.blocks).filter((b) => b.kind === "chart").map((b) => b.chart);
  assert.deepEqual([...charts].sort(), ["baselineVsApp", "finetunePer", "rMarginSweep"]);
});

test("the baseline-vs-app chart uses the exact counts in results/listeners.json (the live English listener)", () => {
  const pairs = read("../../results/listeners.json").pairs;
  for (const row of BASELINE_VS_APP.rows) {
    const rule = pairs[row.pair].new["margin rule"];
    assert.ok(pairs[row.pair].new["passes bar"], `${row.pair} is live`);
    const app = rule["test (korean)"].false_alarms;
    const base = rule["baseline (korean)"].false_alarms;
    assert.deepEqual([row.app.k, row.app.n], [app.k, app.n], `${row.pair} app`);
    assert.deepEqual([row.baseline.k, row.baseline.n], [base.k, base.n], `${row.pair} baseline`);
  }
});

test("the fine-tune curve starts at the untrained listener and falls to the chosen checkpoint", () => {
  assert.equal(FINETUNE_PER.points[0].epoch, 0);
  assert.equal(FINETUNE_PER.points.at(-1)?.epoch, 8);
  const per = FINETUNE_PER.points.map((p) => p.per);
  assert.equal(Math.min(...per), per.at(-1));
});

test("the margin sweep moves the right way: a higher margin never catches more or flags more", () => {
  const pts = R_MARGIN_SWEEP.points;
  for (let i = 1; i < pts.length; i++) {
    assert.ok(pts[i].margin > pts[i - 1].margin);
    assert.ok(pts[i].caught.k <= pts[i - 1].caught.k);
    assert.ok(pts[i].falseAlarms.k <= pts[i - 1].falseAlarms.k);
  }
});

test("no internal labels in the published text (step numbers, decision ids)", () => {
  const all = SECTIONS.flatMap((s) => [s.heading, ...s.blocks.flatMap(texts)]);
  for (const l of all) assert.doesNotMatch(l.en, /\bStep \d+|\bD\d{1,2}\b/, l.en);
});
