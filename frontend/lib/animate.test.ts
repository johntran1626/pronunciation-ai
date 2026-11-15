// The native mouth animation. Checks phonetic facts, not pixels.
import { test } from "node:test";
import assert from "node:assert/strict";
import { frameAt, roles, type Sound } from "./animate.ts";
import { geometry } from "./mouth.ts";
import type { ArticulationEntry } from "./api.ts";

type E = ArticulationEntry;
const svg = (s: Partial<E["svg"]>): E["svg"] => ({
  tongue_x: 0.5, tongue_y: 0.5, tip: "down", contact: false, velum: "raised", lip_gap: 0.4, lip_round: 0, ...s,
});
const e = (x: Partial<E>): E => ({
  kind: "consonant", voicing: "voiced", laryngeal: null, lips: "neutral", description: "", reviewed: true,
  svg: svg({}), ...x,
} as E);

const A = e({ kind: "vowel", lips: "neutral", svg: svg({ tongue_x: 0.3, tongue_y: 0.1, lip_gap: 0.9 }) });
const I = e({ kind: "vowel", lips: "spread", svg: svg({ tongue_x: 0.95, tongue_y: 0.95, lip_gap: 0.3 }) });
const U = e({ kind: "vowel", lips: "rounded", svg: svg({ tongue_x: 0.1, tongue_y: 0.9, lip_gap: 0.2, lip_round: 1 }) });
const P = e({ place: "bilabial", manner: "stop", lips: "closed", voicing: "voiceless", svg: svg({ lip_gap: 0, contact: true }) });
const M = e({ place: "bilabial", manner: "nasal", lips: "closed", svg: svg({ lip_gap: 0, contact: true, velum: "lowered" }) });
const S = e({ place: "alveolar", manner: "fricative", lips: "spread", svg: svg({ tip: "alveolar", lip_gap: 0.2 }) });
const K = e({ place: "velar", manner: "stop", svg: svg({ tongue_x: 0.1, tongue_y: 1, contact: true }) });
const H = e({ place: "glottal", manner: "fricative", svg: svg({ tongue_x: 0.5, tongue_y: 0.4, lip_gap: 0.5 }) });

const seq = (...es: E[]): Sound[] => es.map((entry, i) => ({ ipa: String(i), start: i * 0.1, end: i * 0.1 + 0.1, entry }));
const mid = (i: number) => i * 0.1 + 0.05;
const gap = (g: ReturnType<typeof geometry>) => g.lowerLip.top - g.upperLip.bottom;

test("the lips really close in the middle of p between two open vowels", () => {
  const f = frameAt(seq(A, P, A), mid(1));
  const open = gap(geometry(A.svg, A.kind, A.lips));
  assert.ok(gap(f) < 0.15 * open, `gap ${gap(f)} vs vowel ${open}`);
});

test("a vowel in the middle of its own time reaches its tongue target", () => {
  const f = frameAt(seq(P, I, P), mid(1));
  const t = geometry(I.svg, I.kind, I.lips).body;
  assert.ok(Math.abs(f.body.x - t.x) < 1.5 && Math.abs(f.body.y - t.y) < 1.5, JSON.stringify([f.body, t]));
});

test("coarticulation: the lips start rounding during s when u comes next (and not before i)", () => {
  const beforeU = frameAt(seq(A, S, U), mid(1)).lips.front;
  const beforeI = frameAt(seq(A, S, I), mid(1)).lips.front;
  assert.ok(beforeU < beforeI - 0.5, `${beforeU} vs ${beforeI}`); // smaller x = lips pushed forward
});

test("the tongue is free during p: it already moves toward the next vowel", () => {
  const toI = frameAt(seq(A, P, I), mid(1) + 0.03).body.x;
  const toU = frameAt(seq(A, P, U), mid(1) + 0.03).body.x;
  assert.ok(toI < toU - 2, `${toI} vs ${toU}`); // front vowel next -> tongue further forward (smaller x)
});

test("h takes the shape of the vowel after it", () => {
  const f = frameAt(seq(H, I), mid(0) + 0.02);
  const i = geometry(I.svg, I.kind, I.lips).body;
  const h = geometry(H.svg, H.kind, H.lips).body;
  assert.ok(Math.abs(f.body.x - i.x) < Math.abs(f.body.x - h.x), JSON.stringify([f.body, i, h]));
});

test("k keeps the back of the tongue on the soft palate", () => {
  const f = frameAt(seq(A, K, A), mid(1));
  const t = geometry(K.svg, K.kind, K.lips).body;
  assert.ok(Math.abs(f.body.y - t.y) < 1.5, `${f.body.y} vs ${t.y}`);
});

test("the soft palate drops for m, and is up for p", () => {
  assert.ok(frameAt(seq(A, M, A), mid(1)).velumTip.y > frameAt(seq(A, P, A), mid(1)).velumTip.y + 10);
});

test("before the first sound and after the last: a finite pose, no NaN", () => {
  for (const t of [-1, 0, 0.3, 5]) {
    const f = frameAt(seq(A, P, I), t);
    for (const v of [f.body.x, f.body.y, f.tip.x, f.lips.front, f.upperLip.bottom, f.velumTip.y, f.jaw])
      assert.ok(Number.isFinite(v), `t=${t}`);
  }
});

test("roles: who must hit the target for each sound", () => {
  assert.equal(roles(P).lips, "critical");
  assert.equal(roles(P).body, "free");
  assert.equal(roles(S).tip, "critical");
  assert.equal(roles(S).lips, "free");
  assert.equal(roles(K).body, "critical");
  assert.equal(roles(M).velum, "critical");
  assert.equal(roles(U).lips, "critical");
  assert.equal(roles(H).body, "free");
});

test("sounds with no table entry (null) are skipped, not drawn as a default shape", () => {
  const s = seq(A, P, A);
  s[1] = { ...s[1], entry: null };
  const f = frameAt(s, mid(1));
  const a = geometry(A.svg, A.kind, A.lips);
  assert.ok(Math.abs(gap(f) - gap(a)) < 0.5);
});

test("the tongue tip comes back down in the middle of a vowel after t (vowels have a tip target too)", () => {
  const T = e({ place: "alveolar", manner: "stop", voicing: "voiceless", svg: svg({ tip: "alveolar", contact: true }) });
  const f = frameAt(seq(T, A, P), mid(1));
  const down = geometry(A.svg, A.kind, A.lips).tip.y;
  const up = geometry(T.svg, T.kind, T.lips).tip.y;
  assert.ok(Math.abs(f.tip.y - down) < 0.25 * Math.abs(up - down), `${f.tip.y}: up ${up}, down ${down}`);
  assert.equal(roles(A).tip, "critical");
});

// ---------- stop-motion frames (the smooth blend jittered) ----------
// One still pose per sound (the pose at the sound's middle), neighbours that look the same merged, a short eased
// change between frames, then a hold.
import { EASE, frameIndexAt, framesFor, MERGE, poseAt, poseDistance, wordFrames } from "./animate.ts";

test("one frame per sound; its parts the sound doesn't need are the blended pose at the sound's middle", () => {
  const s = seq(A, P, I);
  const fr = framesFor(s);
  assert.equal(fr.length, 3);
  fr.forEach((f, i) => {
    assert.deepEqual(f.sounds, [i]);
    assert.equal(f.start, s[i].start);
    assert.equal(f.end, s[i].end);
  });
  // p needs only the lips (and the soft palate is "involved"): its tongue is the blend at its middle (coarticulation)
  assert.deepEqual(fr[1].pose.body, frameAt(s, mid(1)).body);
  assert.deepEqual(fr[1].pose.tip, frameAt(s, mid(1)).tip);
});

test("pose distance: 0 for the same pose, large for a vs i, in drawing units", () => {
  const a = geometry(A.svg, A.kind, A.lips), i = geometry(I.svg, I.kind, I.lips);
  assert.equal(poseDistance(a, a), 0);
  assert.ok(poseDistance(a, i) > 10 * MERGE, String(poseDistance(a, i)));
  assert.equal(poseDistance(a, i), poseDistance(i, a));
});

test("neighbours whose poses barely differ become ONE frame (no tiny twitches)", () => {
  const A2 = e({ ...A, svg: svg({ ...A.svg, tongue_x: A.svg.tongue_x + 0.01 }) }); // almost the same vowel
  // 400 ms sounds: with 100 ms ones the middle of A2 is already closing its lips for P (coarticulation), which is a
  // real difference, not the near-duplicate this test is about (first version of this test failed on exactly that)
  const s: Sound[] = [A, A2, P].map((entry, i) => ({ ipa: String(i), start: i * 0.4, end: i * 0.4 + 0.4, entry }));
  const fr = framesFor(s);
  assert.equal(fr.length, 2);
  assert.deepEqual(fr[0].sounds, [0, 1]);
  assert.equal(fr[0].start, s[0].start);
  assert.equal(fr[0].end, s[1].end);
  assert.deepEqual(framesFor(seq(A, I, A)).map((f) => f.sounds.length), [1, 1, 1]); // different poses stay apart
});

test("sounds with no table entry make no frame", () => {
  const s = seq(A, P, I);
  s[1] = { ...s[1], entry: null };
  assert.deepEqual(framesFor(s).map((f) => f.sounds), [[0], [2]]);
  assert.deepEqual(framesFor([]), []);
});

const same = (a: ReturnType<typeof geometry>, b: ReturnType<typeof geometry>) => poseDistance(a, b) < 1e-9;

test("between changes the picture holds perfectly still (that is what removes the jitter)", () => {
  const fr = framesFor(seq(A, P, I, S, U));
  for (let k = 0; k < fr.length; k++) {
    const f = fr[k];
    const len = f.end - f.start;
    // the middle half of every frame is a hold, whatever the ease length
    for (let x = 0.26; x <= 0.74; x += 0.04) assert.ok(same(poseAt(fr, f.start + x * len), f.pose), `frame ${k} at ${x}`);
  }
});

test("a change is eased, lasts at most EASE, and is centred on the boundary between two sounds", () => {
  const long = (...es: E[]): Sound[] => es.map((entry, i) => ({ ipa: String(i), start: i * 0.4, end: i * 0.4 + 0.4, entry }));
  const fr = framesFor(long(A, I));
  const b = fr[1].start, a = fr[0].pose.body.x, z = fr[1].pose.body.x;
  assert.ok(same(poseAt(fr, b - EASE / 2 - 1e-6), fr[0].pose));
  assert.ok(same(poseAt(fr, b + EASE / 2 + 1e-6), fr[1].pose));
  const half = poseAt(fr, b).body.x;
  assert.ok(Math.abs(half - (a + z) / 2) < 0.01 * Math.abs(z - a), `${half} vs ${(a + z) / 2}`);
  // eased: slow at the start of the change, fast in the middle
  const early = poseAt(fr, b - EASE / 2 + EASE / 10).body.x;
  assert.ok(Math.abs(early - a) < 0.1 * Math.abs(z - a));
  // the page passes ease = EASE * speed, so at 0.5x the change is still ~100 ms on screen
  assert.ok(same(poseAt(fr, b + EASE / 4 + 1e-6, EASE / 2), fr[1].pose));
});

test("in a pause the last frame holds; before the first sound the first frame shows", () => {
  const s: Sound[] = [
    { ipa: "a", start: 0.2, end: 0.4, entry: A },
    { ipa: "i", start: 0.9, end: 1.1, entry: I },
  ];
  const fr = framesFor(s);
  assert.ok(same(poseAt(fr, 0), fr[0].pose));
  assert.ok(same(poseAt(fr, 0.6), fr[0].pose));
  assert.ok(same(poseAt(fr, 5), fr[1].pose));
  assert.deepEqual([0, 0.3, 0.6, 0.95, 5].map((t) => frameIndexAt(fr, t)), [0, 0, 0, 1, 1]);
});

test("each word gets the frames whose middle falls inside it (for the words under the slider)", () => {
  const fr = framesFor(seq(A, P, I, S, U)); // 0.0-0.5 s
  const words = [
    { word: "ap", start: 0, end: 0.2 },
    { word: "isu", start: 0.2, end: 0.5 },
    { word: "pause", start: 0.6, end: 0.8 },
  ];
  assert.deepEqual(wordFrames(words, fr), [{ first: 0, last: 1 }, { first: 2, last: 4 }, null]);
});

test("in its own frame, each sound's critical parts sit ON target (a vowel between t and k is a clean vowel)", () => {
  // Screenshots: frozen as a still, the blended middle of ㅡ between n and l had the tongue tip up at the
  // teeth, and ㅏ between k and ㄹ a half-raised tip and body (pulled ~10 units by the neighbours)
  const T = e({ place: "alveolar", manner: "stop", voicing: "voiceless", svg: svg({ tip: "alveolar", contact: true }) });
  const own = geometry(A.svg, A.kind, A.lips);
  const f = framesFor(seq(T, A, K))[1].pose;
  for (const k of ["tip", "body"] as const) assert.ok(Math.hypot(f[k].x - own[k].x, f[k].y - own[k].y) < 0.01, k);
  assert.equal(f.jaw, own.jaw);
  // parts the sound does not need still follow the neighbours: h takes the vowel's tongue, p lets the tongue move
  const h = framesFor(seq(H, I))[0].pose.body, i = geometry(I.svg, I.kind, I.lips).body;
  assert.ok(Math.abs(h.x - i.x) < Math.abs(geometry(H.svg, H.kind, H.lips).body.x - i.x));
  assert.ok(framesFor(seq(A, P, I))[1].pose.body.x < framesFor(seq(A, P, U))[1].pose.body.x - 2);
});

test("a vowel's own frame shows its own mouth opening, even between lip sounds (ㅏ after m, 'time')", () => {
  // 'ah' frames next to m / b / p were barely open (lips are only 'involved' for a plain vowel, so
  // the closing lips of the neighbours pulled them shut: aɪ in "time" 4.2 units instead of 12)
  const f = framesFor(seq(M, A, P))[1].pose;
  const own = geometry(A.svg, A.kind, A.lips);
  assert.ok(Math.abs(gap(f) - gap(own)) < 0.01, `${gap(f)} vs ${gap(own)}`);
});

// ---------- the app's player: the backend's /tts/timings -> timed sounds with their table entries ----------
import { soundsFromTimings } from "./animate.ts";
import type { NativeTimings } from "./api.ts";

const TIMINGS: NativeTimings = {
  version: 1, lang: "en", duration_s: 0.9,
  words: [
    { word: "map", start: 0.1, end: 0.4, phonemes: [
      { ipa: "m", start: 0.1, end: 0.2 }, { ipa: "æ", start: 0.2, end: 0.3 }, { ipa: "p", start: 0.3, end: 0.4 },
    ] },
    { word: "ski", start: 0.5, end: 0.8, phonemes: [
      { ipa: "s", start: 0.5, end: 0.6 }, { ipa: "k", start: 0.6, end: 0.7 }, { ipa: "i", start: 0.7, end: 0.8 },
    ] },
  ],
};
const TABLE: Record<string, ArticulationEntry> = { m: M, æ: A, p: P, s: S, k: K, i: I };

test("every word's sounds come out in time order, each with its own table entry", () => {
  const { sounds } = soundsFromTimings(TIMINGS, TABLE);
  assert.deepEqual(sounds.map((s) => s.ipa), ["m", "æ", "p", "s", "k", "i"]);
  assert.deepEqual(sounds.map((s) => [s.start, s.end]), [[0.1, 0.2], [0.2, 0.3], [0.3, 0.4], [0.5, 0.6], [0.6, 0.7], [0.7, 0.8]]);
  assert.equal(sounds[2].entry, P);
  assert.equal(sounds[5].entry, I);
});

test("the words keep their own times (for the words under the slider)", () => {
  const { words } = soundsFromTimings(TIMINGS, TABLE);
  assert.deepEqual(words, [{ word: "map", start: 0.1, end: 0.4 }, { word: "ski", start: 0.5, end: 0.8 }]);
});

test("a sound missing from the table gets no entry, so it gets no frame (never a wrong pose)", () => {
  const { sounds } = soundsFromTimings(TIMINGS, { ...TABLE, k: undefined as unknown as ArticulationEntry });
  assert.equal(sounds[4].entry, null);
  assert.equal(framesFor(sounds, 0).length, 5);
});
