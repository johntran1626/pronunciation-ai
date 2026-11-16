// A NATIVE side-view mouth animation from timed sounds. Pure math (tested in animate.test.ts);
// app/dev/animate draws each frame with the same cut-away drawing as the detail card (components/MouthDiagram.tsx).
//
// In brief: every sound has a textbook pose (content/articulation.json -> lib/mouth.ts geometry). Speech is not
// a slideshow of poses: neighbours blend ("coarticulation"). The lips start rounding during the s of "soon", and
// the tongue is already moving to the next vowel while the lips are shut for p. So the mouth is split into 5 parts
// (lips, jaw, tongue tip, tongue body, soft palate), and for every part each sound gets a "pull":
//   critical  the sound needs this part (lips for p, tip for t/s, body for k, body+tip for vowels)  pull 10
//   involved  it cares a bit (lip shape for a plain vowel, velum up for oral sounds)       pull 1
//   free      it doesn't care (tongue during p, lips during s, everything during h)        pull 0.1
// A pull fades with distance in time (halves every ~21 ms outside the sound). At each moment, each part sits at the
// pull-weighted average of all the poses. A "free" part simply follows whichever neighbour pulls hardest.
// This is the dominance model of Cohen & Massaro (1993), simplified (one fixed fade rate).
//
// Closure hold: averaging never quite reaches a full closure (the open vowels on both sides pull the lips apart a
// little), but a real p, b, m, k, t DOES close. So inside a closure sound's own time, the part that makes the
// closure is eased onto its exact target (eased in and out at the edges, so there is no jump).
//
// What this is NOT: a measurement of any speaker. It is the TARGET articulation from phonetics tables, timed to a
// native recording. Diphthongs show one pose (their "to" glide is not animated yet).
import { callout, geometry, type Callout, type Geometry, type Svg } from "./mouth.ts";
import { front, type Front } from "./mouthViews.ts";
import type { ArticulationEntry, Lang, NativeTimings } from "./api.ts";

// lang: which language's table the entry came from (a mixed sentence has both)
export type Sound = { ipa: string; lang: Lang; start: number; end: number; entry: ArticulationEntry | null };
export type Role = "critical" | "involved" | "free";
export type Part = "lips" | "jaw" | "tip" | "body" | "velum";
export const PARTS: Part[] = ["lips", "jaw", "tip", "body", "velum"];
const PULL: Record<Role, number> = { critical: 10, involved: 1, free: 0.1 };
export const FADE = 0.03; // seconds: pull = PULL * exp(-time outside the sound / FADE)
const HOLD_RAMP = 0.02; // seconds to ease onto a closure (at most 25% of the sound's length)

// which Geometry fields move with which part
const FIELDS: Record<Part, (keyof Geometry)[]> = {
  lips: ["lips", "upperLip", "lowerLip"],
  jaw: ["jaw", "teeth", "floorFront"],
  tip: ["tip", "tipFront", "tipBottom", "underside"],
  body: ["body"],
  velum: ["velumTip"],
};

const REST: Svg = { tongue_x: 0.5, tongue_y: 0.5, tip: "down", contact: false, velum: "raised", lip_gap: 0.2, lip_round: 0 };
const TIP_UP = ["dental", "alveolar", "postalveolar", "raised"];

export function roles(e: ArticulationEntry): Record<Part, Role> {
  const s = e.svg;
  const rounded = e.lips === "rounded" || s.lip_round > 0.3;
  if (e.kind === "vowel" || e.kind === "diphthong") {
    // tip critical: the tip rests behind the lower teeth in a vowel; as "free" it floated up near every t/d/n/l
    // (seen in screenshots)
    return { lips: rounded ? "critical" : "involved", jaw: "critical", tip: "critical", body: "critical", velum: "involved" };
  }
  if (e.kind === "glide") {
    return rounded // w: the lips do the work; j: the tongue body does
      ? { lips: "critical", jaw: "free", tip: "free", body: "involved", velum: "involved" }
      : { lips: "free", jaw: "free", tip: "free", body: "critical", velum: "involved" };
  }
  const lipsMade = e.lips === "closed" || e.lips === "lip_to_teeth";
  const bodyMade = bodyContact(e);
  return {
    lips: lipsMade ? "critical" : e.lips === "rounded" ? "involved" : "free", // English r, sh: a little rounding
    jaw: e.place === "alveolar" || e.place === "postalveolar" ? "involved" : "free",
    tip: TIP_UP.includes(s.tip) ? "critical" : "free",
    body: bodyMade ? "critical" : e.manner === "approximant" ? "involved" : "free",
    velum: e.manner === "nasal" ? "critical" : "involved",
  };
}

// the parts that make a full closure / contact for this sound: they get the closure hold
function holds(e: ArticulationEntry): Part[] {
  if (e.kind !== "consonant") return [];
  const out: Part[] = [];
  if (e.lips === "closed" || e.lips === "lip_to_teeth") out.push("lips");
  if (e.svg.contact && TIP_UP.includes(e.svg.tip)) out.push("tip");
  if (bodyContact(e)) out.push("body");
  return out;
}

// k, g, ng, ㅈ: the tongue BODY touches the roof. For p, b, m the "contact" is the lips, so they don't count.
function bodyContact(e: ArticulationEntry): boolean {
  const lips = e.lips === "closed" || e.lips === "lip_to_teeth";
  return e.svg.contact && !lips && (e.svg.tip === "down" || e.svg.tip === "palatal");
}

const outside = (t: number, s: Sound) => (t < s.start ? s.start - t : t > s.end ? t - s.end : 0);

type Val = number | { [k: string]: Val };
function mix(vals: Val[], w: number[]): Val {
  if (typeof vals[0] === "number") return (vals as number[]).reduce((a, v, i) => a + v * w[i], 0);
  const out: { [k: string]: Val } = {};
  for (const k of Object.keys(vals[0])) out[k] = mix(vals.map((v) => (v as { [k: string]: Val })[k]), w);
  return out;
}
const lerp = (a: Val, b: Val, k: number): Val => mix([a, b], [1 - k, k]);
const smooth = (x: number) => x * x * (3 - 2 * x);

/** The mouth at time t (seconds) for a timed sentence: a Geometry ready for the cut-away drawing. */
export function frameAt(sounds: Sound[], t: number): Geometry {
  const live = sounds.filter((s): s is Sound & { entry: ArticulationEntry } => s.entry !== null);
  if (!live.length) return geometry(REST, "vowel", "neutral");
  const poses = live.map((s) => geometry(s.entry.svg, s.entry.kind, s.entry.lips));
  const role = live.map((s) => roles(s.entry));
  const out = { ...poses[0] } as unknown as { [k: string]: Val };
  for (const part of PARTS) {
    // weights in log space, so a sound far away (seconds) can't underflow every weight to 0
    const lw = live.map((s, i) => Math.log(PULL[role[i][part]]) - outside(t, s) / FADE);
    const top = Math.max(...lw);
    const raw = lw.map((x) => Math.exp(x - top));
    const sum = raw.reduce((a, b) => a + b, 0);
    const w = raw.map((x) => x / sum);
    for (const f of FIELDS[part]) out[f] = mix(poses.map((g) => g[f] as unknown as Val), w);
  }
  // closure hold for the sound we're inside
  live.forEach((s, i) => {
    if (t < s.start || t > s.end) return;
    const ramp = Math.min(HOLD_RAMP, 0.25 * (s.end - s.start));
    const k = ramp > 0 ? smooth(Math.min(1, (t - s.start) / ramp, (s.end - t) / ramp)) : 1;
    for (const part of holds(s.entry))
      for (const f of FIELDS[part]) out[f] = lerp(out[f], poses[i][f] as unknown as Val, k);
  });
  return out as unknown as Geometry;
}

/** The sound playing at time t (for the label under the picture), or null in a pause. */
export function soundAt(sounds: Sound[], t: number): Sound | null {
  return sounds.find((s) => t >= s.start && t < s.end) ?? null;
}

// ---------- stop-motion ----------
// The smooth blend above changed the picture on every screen refresh, so the tongue looked like it was shivering.
// Stop-motion instead: ONE still pose per sound (frameAt at the sound's middle, with the parts the sound needs put on
// target; the coarticulation of the other parts and the fixed-size tongue shape stay), neighbours that look the same merged into one frame, and a short eased change between frames.
//   hold  -> the picture is perfectly still for at least the middle half of every frame
//   ease  -> each change takes EASE of screen time (the page passes EASE * playback speed), centred on the boundary
//            between two sounds, but never more than half of either neighbour (that keeps the hold)
export type Frame = { start: number; end: number; sounds: number[]; pose: Geometry };
export const MERGE = 2.5; // drawing units: two poses closer than this look the same (~5 px on a phone)
export const EASE = 0.1; // seconds on screen per change
export const DEFAULT_SPEED = 1; // the player starts at normal speed; 0.5x is one tap away

/** "Show what matters": the one defining contact or shape for a frame (F: lower lip on the upper teeth, t: tip on
 * the ridge, k: back of the tongue on the soft palate, vowels: highest point of the tongue), placed on the pose
 * that is showing right now. A merged frame uses its first sound that has one; null when there's nothing to mark. */
export function frameMark(sounds: Sound[], g: Geometry, say?: (english: string) => string): Callout | null {
  for (const s of sounds) {
    if (!s.entry) continue;
    const c = callout(s.entry, g, say);
    if (c) return c;
  }
  return null;
}

const pt = (a: { x: number; y: number }, b: { x: number; y: number }) => Math.hypot(a.x - b.x, a.y - b.y);
/** How different two poses look: the biggest move of any visible part, in drawing units. */
export function poseDistance(a: Geometry, b: Geometry): number {
  return Math.max(
    pt(a.body, b.body), pt(a.tip, b.tip), pt(a.tipFront, b.tipFront), pt(a.velumTip, b.velumTip),
    Math.abs(a.jaw - b.jaw), Math.abs(a.lips.front - b.lips.front), Math.abs(a.lowerLip.front - b.lowerLip.front),
    Math.abs(a.upperLip.bottom - b.upperLip.bottom), Math.abs(a.lowerLip.top - b.lowerLip.top),
  );
}

/** A sound's still: the blended pose at its middle, with every part the sound NEEDS (critical) put exactly on
 * its own target. Frozen, a blend that is 10 units short reads as a different sound (ㅡ between n and l showed
 * the tongue tip up at the teeth); parts the sound doesn't need still come from the neighbours (h, tongue in p). */
function framePose(sounds: Sound[], s: Sound & { entry: ArticulationEntry }): Geometry {
  const out = frameAt(sounds, s.start + 0.5 * (s.end - s.start)) as unknown as { [k: string]: Val };
  const own = geometry(s.entry.svg, s.entry.kind, s.entry.lips) as unknown as { [k: string]: Val };
  const r = roles(s.entry);
  // A vowel's own frame also shows its own lips (how open the mouth is IS the vowel: 'ah' next to m or b
  // was frozen nearly shut); during the short change between frames the lips still blend
  const vowel = s.entry.kind === "vowel" || s.entry.kind === "diphthong";
  for (const part of PARTS)
    if (r[part] === "critical" || (vowel && part === "lips")) for (const f of FIELDS[part]) out[f] = own[f];
  return out as unknown as Geometry;
}

/** One frame per sound, in time order; a sound whose pose is within `merge` of the current frame joins it. */
export function framesFor(sounds: Sound[], merge = MERGE): Frame[] {
  const out: Frame[] = [];
  sounds.forEach((s, i) => {
    if (!s.entry) return; // no table entry: no pose to show
    const pose = framePose(sounds, s as Sound & { entry: ArticulationEntry });
    const last = out[out.length - 1];
    // compare with the frame's KEPT pose (its first sound), so a slow drift can't chain into one long frame
    if (last && poseDistance(last.pose, pose) < merge) {
      last.end = s.end;
      last.sounds.push(i);
    } else out.push({ start: s.start, end: s.end, sounds: [i], pose });
  });
  return out;
}

/** The frame showing at time t: the latest one that has started (the first one before any sound). */
export function frameIndexAt(frames: Frame[], t: number): number {
  let k = 0;
  for (let i = 1; i < frames.length; i++) if (frames[i].start <= t) k = i;
  return k;
}

/** Which frames make the picture at time t: frame a alone (w = 0), or an eased change from a to b (w = 0..1)
 * near their boundary. Shared by the side view (poseAt) and the front view (frontAt), so they always change together. */
function blendAt(frames: Frame[], t: number, ease: number): { a: number; b: number; w: number } {
  const k = frameIndexAt(frames, t);
  // the boundary nearest t: into frame k (at its start) or out of it (at the next frame's start)
  for (const j of [k, k + 1]) {
    if (j < 1 || j >= frames.length) continue;
    const prev = frames[j - 1], next = frames[j], b = next.start;
    // prev's time runs on through any pause until next starts
    const e = Math.min(ease, 0.5 * (b - prev.start), 0.5 * (next.end - next.start));
    if (e > 0 && Math.abs(t - b) < e / 2) return { a: j - 1, b: j, w: smooth((t - (b - e / 2)) / e) };
  }
  return { a: k, b: k, w: 0 };
}

/** The picture at time t: a frame's still pose, or an eased change between two frames near their boundary. */
export function poseAt(frames: Frame[], t: number, ease = EASE): Geometry {
  if (!frames.length) return geometry(REST, "vowel", "neutral");
  const { a, b, w } = blendAt(frames, t, ease);
  if (a === b) return frames[a].pose;
  return lerp(frames[a].pose as unknown as Val, frames[b].pose as unknown as Val, w) as unknown as Geometry;
}

// ---------- the front (mirror) view ----------
// The same stop-motion frames, seen from the front: each frame shows the mirror view of its first sound (the same
// rules as the detail card's picture, lib/mouthViews.ts front()), and changes with the same easing as the side view.
// Limit: the side view's poses blend neighbours (lips rounding during the s of "soon"); the front view shows each
// sound's own textbook shape.
export type FrontPose = Front & { round: number }; // round = how rounded the lips are (0..1), for the lip outline

const frontPose = (e: ArticulationEntry): FrontPose => ({ ...front(e), round: e.svg.lip_round });
const REST_FRONT = frontPose({ kind: "vowel", lips: "neutral", svg: REST } as ArticulationEntry);

/** One front view per frame (frames from framesFor on the same sounds). */
export function frontsFor(frames: Frame[], sounds: Sound[]): FrontPose[] {
  return frames.map((f) => frontPose(sounds[f.sounds[0]].entry!)); // framesFor only makes frames for sounds with entries
}

/** The front view at time t. Sizes blend; parts that are there or not (teeth, tongue) switch halfway; the lips
 * only shut once the opening has nearly closed, so p after a vowel shrinks the mouth and then closes it. */
export function frontAt(frames: Frame[], fronts: FrontPose[], t: number, ease = EASE): FrontPose {
  if (!frames.length || !fronts.length) return REST_FRONT;
  const { a, b, w } = blendAt(frames, t, ease);
  const A = fronts[a], B = fronts[b];
  if (a === b) return A;
  const near = w < 0.5 ? A : B;
  const height = A.height + (B.height - A.height) * w;
  return {
    ...near,
    width: A.width + (B.width - A.width) * w,
    height,
    round: A.round + (B.round - A.round) * w,
    closed: (A.closed || B.closed) && height < 1,
  };
}

/** For each word, the first and last frame whose middle falls inside it (null if none: a word with no sounds). */
export function wordFrames(
  words: { start: number; end: number }[],
  frames: Frame[],
): ({ first: number; last: number } | null)[] {
  return words.map((w) => {
    const idx = frames.map((f, i) => [0.5 * (f.start + f.end), i]).filter(([m]) => m >= w.start && m < w.end).map(([, i]) => i);
    return idx.length ? { first: idx[0], last: idx[idx.length - 1] } : null;
  });
}

/** The backend's timings for a native clip (/tts/timings) -> the timed sounds the animation plays, each with its
 * articulation table entry (null when the table has no entry: that sound gets no frame), plus the words' times. */
export function soundsFromTimings(
  timings: NativeTimings,
  tables: Record<Lang, Record<string, ArticulationEntry>>,
): { words: { word: string; start: number; end: number }[]; sounds: Sound[] } {
  const words = timings.words.map(({ word, start, end }) => ({ word, start, end }));
  const sentenceLang: Lang = timings.lang === "mix" ? "en" : timings.lang; // a mixed word always carries its own
  const sounds = timings.words.flatMap((w) => {
    const lang = w.lang ?? sentenceLang;
    return w.phonemes.map(({ ipa, start, end }) => ({ ipa, lang, start, end, entry: tables[lang][ipa] ?? null }));
  });
  return { words, sounds };
}
