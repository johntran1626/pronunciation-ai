// Articulation numbers (content/articulation.json "svg") -> key points of a side-view mouth.
// Pure math (tested in mouth.test.ts); components/MouthDiagram.tsx turns the points into SVG shapes.
//
// Coordinates: a 220 x 200 box, the face looks LEFT. Smaller x = further forward, smaller y = higher.
// Proportions checked against the CC0 (public-domain) sagittal diagrams by Richard Wright & Dan McCloy
// (Wikimedia Commons, "IPA <x> Sagittal Section.svg"): tall incisors, a gum ridge behind the upper teeth, a
// dome-shaped tongue filling the floor of the mouth.

// Zoomed on the mouth (parts were too small). The drawing still uses the 220 x 200 coordinates;
// VIEW is the window we show: from just left of the nose tip to just past the throat, nose to chin.
// X 8 -> 14, w 176 -> 170: the face moved back with the slimmer lips (nose tip now at x = 25)
export const VIEW = { x: 14, y: 34, w: 170, h: 150 };

export type Svg = {
  tongue_x: number; // 0 = back, 1 = front
  tongue_y: number; // 0 = low (jaw open), 1 = high
  tip: "down" | "dental" | "alveolar" | "postalveolar" | "palatal" | "raised";
  contact: boolean; // the tongue (or lips) actually touch
  velum: "raised" | "lowered"; // lowered = air also goes through the nose
  lip_gap: number; // 0 = closed .. 1 = wide
  lip_round: number; // 0 = spread/neutral .. 1 = fully rounded
};
export type Pt = { x: number; y: number };

export const PHARYNX_X = 168; // back wall of the throat
export const TEETH_X = 50; // front edge of the upper teeth
const UPPER_TEETH_TIP = 92;
// The lips stand 13 units in front of the upper teeth (was
// 22, about the incisor's height; now ~0.8 of it), and the chin sits behind the lower lip.
const LIP_FRONT = 36; // front of relaxed (unrounded) upper lip
const CHIN_X = 42; // front of the chin; it moves down with the jaw, not with the lips
const UPPER_TEETH_ROOT = 74; // where the upper incisor comes out of the gum
const VELUM_START: Pt = { x: 125, y: 66 }; // where the hard palate ends and the soft palate begins

// The roof of the mouth, front to back: teeth -> ridge -> hard palate -> soft palate (raised position).
const ROOF: [number, number][] = [
  [50, 86],
  [56, 80],
  [62, 77],
  [72, 72],
  [85, 68],
  [100, 66],
  [125, 66],
  [145, 70],
  [166, 76],
];

export function palateY(x: number): number {
  if (x <= ROOF[0][0]) return ROOF[0][1];
  for (let i = 1; i < ROOF.length; i++) {
    const [x1, y1] = ROOF[i];
    const [x0, y0] = ROOF[i - 1];
    if (x <= x1) return y0 + ((y1 - y0) * (x - x0)) / (x1 - x0);
  }
  return ROOF[ROOF.length - 1][1];
}

export type Geometry = {
  jaw: number; // how far the jaw drops (px)
  lips: { front: number }; // how far forward the lips reach
  upperLip: { front: number; bottom: number };
  lowerLip: { front: number; top: number };
  teeth: { upperRoot: number; upperTip: number; lowerTop: number; lowerRoot: number };
  floorFront: Pt; // front of the floor of the mouth, just behind the lower teeth
  tipFront: Pt; // the rounded front of the tongue tip
  tipBottom: Pt; // underside of the tip (tip thickness = tipBottom.y - tip.y)
  underside: Pt; // where the tongue's underside meets the floor of the mouth
  lipRed: number; // height of the red part of each lip
  body: Pt; // the highest point of the tongue body
  tip: Pt;
  velumTip: Pt;
};

export function geometry(s: Svg, kind: string, lips?: string): Geometry {
  const isVowel = kind === "vowel" || kind === "diphthong";
  const jaw = isVowel ? (1 - s.tongue_y) * 16 : 3;

  // Lips: rounding pushes them forward and narrows the opening.
  const protrude = s.lip_round * 7;
  const front = LIP_FRONT - protrude; // 22 -> 14 units in front of the teeth (lips read as too big)
  const mid = 93 + jaw * 0.5;
  // Open vs closed must read at a glance. Vowels: the lips part mostly WITH the jaw (x1.6), so ㅏ / ah opens
  // ~29 units against 4 for ㅣ / ee (7x). Consonants: the jaw stays nearly shut and the lips only slightly
  // apart (s, t, k, n: 3.6, never more open than ㅣ). Rounding narrows either.
  const gap = (isVowel ? s.lip_gap * 8 + jaw * 1.6 : s.lip_gap * 6 + jaw * 0.4) * (1 - 0.45 * s.lip_round);
  let upperBottom = mid - gap / 2;
  let lowerTop = mid + gap / 2;
  let lowerFront = front + 2;
  if (s.lip_gap === 0) upperBottom = lowerTop = mid; // closed: they meet
  if (lips === "lip_to_teeth") {
    upperBottom = mid - 5; // upper lip lifts a little
    lowerTop = UPPER_TEETH_TIP; // lower lip tucks up under the upper teeth
    lowerFront = TEETH_X - 6;
  }

  // Tongue body: the top of a fixed-size dome (tongueOutline). Front/back from tongue_x, height from tongue_y.
  // Smaller ranges, and the tongue rides on the jaw, so a low vowel
  // opens mostly with the jaw (as real low vowels do) instead of the tongue sinking out of sight.
  const bx = 138 - 48 * s.tongue_x; // ~131 under the soft palate (u, k) .. ~95 under the hard palate (i)
  // +9: even the highest vowel leaves a visible gap under the roof (the soft palate is drawn 8 units thick, so a
  // smaller gap looked like contact on ㅡ/ㅜ; screenshot check).
  let by = Math.max(111 + jaw - (26 + 10 * s.tongue_y), palateY(bx) + 9); // 111 + jaw = floor of the mouth
  if (s.contact && s.tip === "down") by = palateY(bx); // back of the tongue ON the soft palate (k, g, ng)
  if (s.contact && s.tip === "palatal") by = palateY(bx); // front of the tongue ON the hard palate (ㅈ, ㅊ)

  // Tongue tip.
  const restingTip: Pt = { x: 58, y: 104 + jaw };
  let tip: Pt;
  switch (s.tip) {
    case "dental":
      tip = { x: TEETH_X + 1, y: UPPER_TEETH_TIP }; // at the edge of the upper teeth
      break;
    case "alveolar":
      tip = { x: 62, y: s.contact ? palateY(62) : palateY(62) + 4 };
      break;
    case "postalveolar":
      tip = { x: 72, y: s.contact ? palateY(72) : palateY(72) + 4 };
      break;
    case "raised":
      tip = { x: 80, y: palateY(80) + 6 }; // curled up and back, NOT touching (English r)
      break;
    default: // "down" and "palatal": the tip rests behind the lower teeth
      tip = restingTip;
  }

  // Tongue tip with real thickness (a thin tip read as a tiny hook). An "up" tip (t, d, n, l, r, th)
  // is a rounded lobe pointing up; its underside then curves back down to the floor, so the lifted front is visible.
  const up = s.tip !== "down" && s.tip !== "palatal";
  const tipFront = up ? { x: tip.x - 4.5, y: tip.y + 5 } : { x: tip.x - 3, y: tip.y + 3.5 };
  const tipBottom = up ? { x: tip.x + 4, y: tip.y + 11 } : { x: tip.x + 3, y: tip.y + 9 };
  const lowerTeethTop = 97 + jaw;
  // floor of the mouth sits about level with the lower teeth's roots, so the tongue's front and underside show
  const underside = up ? { x: Math.max(tip.x + 14, 70), y: lowerTeethTop + 15 } : { x: tip.x + 7, y: lowerTeethTop + 15 };

  const velumTip = s.velum === "raised" ? { x: PHARYNX_X - 1, y: 80 } : { x: 146, y: 98 };
  return {
    jaw,
    lips: { front },
    upperLip: { front, bottom: upperBottom },
    lowerLip: { front: lowerFront, top: lowerTop },
    teeth: { upperRoot: UPPER_TEETH_ROOT, upperTip: UPPER_TEETH_TIP, lowerTop: 97 + jaw, lowerRoot: 112 + jaw },
    floorFront: { x: TEETH_X + 8, y: 107 + jaw },
    tipFront,
    tipBottom,
    underside,
    lipRed: 10,
    body: { x: bx, y: by },
    tip,
    velumTip,
  };
}

export { VELUM_START };

// ---------- the tongue outline and the floor of the mouth, as point lists ----------
// Points (not SVG curve commands) so tests can measure what is drawn: the tongue's size, where its back sits.
const N = 16; // points per curve piece: smooth at this drawing size
const P = (x: number, y: number): Pt => ({ x, y });
function quad(a: Pt, c: Pt, b: Pt): Pt[] {
  return Array.from({ length: N }, (_, i) => {
    const u = (i + 1) / N, v = 1 - u;
    return P(v * v * a.x + 2 * v * u * c.x + u * u * b.x, v * v * a.y + 2 * v * u * c.y + u * u * b.y);
  });
}
function cubic(a: Pt, c1: Pt, c2: Pt, b: Pt, n = N): Pt[] {
  return Array.from({ length: n }, (_, i) => {
    const u = (i + 1) / n, v = 1 - u;
    const k = [v * v * v, 3 * v * v * u, 3 * v * u * u, u * u * u];
    return P(k[0] * a.x + k[1] * c1.x + k[2] * c2.x + k[3] * b.x, k[0] * a.y + k[1] * c1.y + k[2] * c2.y + k[3] * b.y);
  });
}
const toPath = (pts: Pt[], close: boolean) =>
  pts.map((q, i) => `${i ? "L" : "M"} ${q.x.toFixed(1)} ${q.y.toFixed(1)}`).join(" ") + (close ? " Z" : "");

/** Upper line of the floor of the mouth, front to back (the tongue below it is hidden by the jaw). */
export function floorOutline(g: Geometry): Pt[] {
  const lt = g.teeth.lowerTop, us = g.underside;
  const a = P(TEETH_X + 3, lt + 14), m = P(us.x, us.y + 1), b = P(140, lt + 32);
  return [a, ...quad(a, P(62, lt + 15), m), ...quad(m, P(120, lt + 22), b), ...quad(b, P(152, lt + 38), P(157, 147))];
}
export const floorPath = (g: Geometry) => toPath(floorOutline(g), false);

// The tongue is ONE fixed-size dome that slides with the body point; only the front (blade -> tip) bends.
// Before, the back curve was stretched from a fixed root to the body point, so the tongue ballooned for k/g/ŋ/u
// (4.1x the area of æ) and its back pressed against the throat wall.
const ROOT_BACK_X = 150; // the widest point of the tongue's back when the body is fully back ...
const ROOT_BACK_BODY_X = 131; // ... i.e. with the body point here (u, k)
const smoothstep = (x: number) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
const mixPts = (a: Pt[], b: Pt[], k: number) => a.map((q, i) => P(q.x + (b[i].x - q.x) * k, q.y + (b[i].y - q.y) * k));

export const VELUM_CTRL: Pt = { x: 146, y: 66 }; // control point of the soft palate's curve (as drawn)
/**
 * The lowest the roof reaches at x, including the soft palate wherever it hangs right now (lowered for m, n, ng).
 * The tongue may press against this line but never cross it. Behind the soft palate's tip the ceiling stays at the
 * tip's height (that space is the passage to the nose; with no ceiling there the tongue made a spike past the tip).
 */
export function ceilingY(x: number, g: Geometry): number {
  if (x <= VELUM_START.x) return palateY(x);
  const v = g.velumTip;
  let prev = VELUM_START;
  for (let i = 1; i <= 32; i++) {
    const u = i / 32, w = 1 - u;
    const q = P(w * w * VELUM_START.x + 2 * w * u * VELUM_CTRL.x + u * u * v.x, w * w * VELUM_START.y + 2 * w * u * VELUM_CTRL.y + u * u * v.y);
    if (q.x >= x) return q.x === prev.x ? q.y : prev.y + ((q.y - prev.y) * (x - prev.x)) / (q.x - prev.x);
    prev = q;
  }
  return v.y;
}

/** The whole tongue outline (closed): up the back, over the dome, down the blade to the tip, under the tip. */
export function tongueOutline(g: Geometry): Pt[] {
  const { body: b, tip: t, tipFront: tf, tipBottom: tb, underside: us } = g;
  const tp = P(t.x + 1, t.y);
  // the back: the root stays down in the throat. It moves only 30% as far as the top of the tongue, so the tongue
  // BUNCHES forward (i) or back (u, k) instead of sliding whole (sliding left an empty throat behind i, e, ae).
  // Below its widest point the root runs down and slightly forward, hidden under the floor of the mouth.
  const backX = Math.min(ROOT_BACK_X - 0.3 * (ROOT_BACK_BODY_X - b.x), PHARYNX_X - 10);
  const wide = P(backX, b.y + 30);
  const back = [
    P(backX - 12, 205), // below the picture
    ...cubic(P(backX - 12, 205), P(backX - 6, 160), P(backX, b.y + 50), wide),
    ...cubic(wide, P(backX, b.y + 13), P(b.x + 0.55 * (backX - b.x), b.y), b),
  ];
  // the front, two ways, blended by how high the tip is (no snap between "tip down" and "tip up" mid-animation):
  //   down: from the top of the dome to the tip behind the lower teeth. Body near the front (i, e): a rounded,
  //         convex front. Body pulled back (u, k, ng): the front sags a little (concave), as in real /u/ and /k/.
  //   up:   from the dome to the raised tip (t, d, n, l, s, r, th)
  const d = b.x - tp.x, h = tp.y - b.y;
  const sag = smoothstep((d - 40) / 30); // 0 when the body is forward (d <= 40) .. 1 when it is back (d >= 70)
  const lerpP = (a: Pt, c: Pt) => P(a.x + (c.x - a.x) * sag, a.y + (c.y - a.y) * sag);
  const down = cubic(
    b,
    lerpP(P(b.x - 0.35 * d, b.y), P(b.x - 0.25 * d, b.y + 0.1 * h)),
    lerpP(P(tp.x + 0.3 * d, tp.y - 0.5 * h), P(tp.x + 0.5 * d, tp.y - 0.02 * h)),
    tp,
    2 * N,
  );
  // The line dips a little behind a raised blade (t, n, l: arched upwards it read as a block filling the mouth).
  // A short, curled-back blade (English r: tip only ~30 units ahead of the body) keeps its high, bunched body.
  const dip = smoothstep((b.x - t.x - 30) / 15);
  const up = cubic(b, P(b.x + 0.35 * (t.x - b.x), b.y + 0.35 * (t.y - b.y) - 3 + 7 * dip), P(b.x + 0.8 * (t.x - b.x), b.y + 0.8 * (t.y - b.y) - 3 + 4 * dip), tp, 2 * N);
  const lift = smoothstep((g.teeth.lowerTop + 7 - t.y) / 14); // 0 = tip resting behind the lower teeth .. 1 = tip up
  const outline = [
    ...back,
    ...mixPts(down, up, lift),
    ...quad(tp, P(tf.x, t.y), tf),
    ...quad(tf, P(tf.x, tb.y), tb),
    ...cubic(tb, P(tb.x + 4, tb.y + 5), P(us.x - 4, us.y - 8), us),
    P(us.x + 10, us.y + 14),
    P(us.x + 10, 205),
  ];
  // the roof is solid: where the tongue would cross it (a contact, or two sounds blending, e.g. m -> g with the soft
  // palate still down), the tongue flattens against it instead. +1 / +1.75 = half the drawn line widths.
  return outline.map((q) => {
    if (q.x < TEETH_X) return q;
    const c = ceilingY(q.x, g) + (q.x <= VELUM_START.x ? 1 : 1.75);
    return q.y < c ? P(q.x, c) : q;
  });
}
export const tonguePath = (g: Geometry) => toPath(tongueOutline(g), true);

// ---------- the face profile (nose -> upper lip, lower lip -> chin) as point lists ----------
/** The outside profile in two pieces: `upper` runs from the forehead over the nose and down the upper lip to its
 * inner edge at the teeth; `lower` runs from the lower lip's inner edge down over the chin. Points, so tests can
 * measure how far the face sticks out in front of the teeth. */
export function faceOutline(g: Geometry): { upper: Pt[]; lower: Pt[] } {
  const ul = g.upperLip, ll = g.lowerLip, jaw = g.jaw;
  const a = P(54, 0), nose = P(25, 50), sub = P(38, 62), ulFront = P(ul.front + 0.5, ul.bottom - 2), ulIn = P(TEETH_X - 2, ul.bottom);
  const upper = [a, ...quad(a, P(50, 26), nose), ...quad(nose, P(23, 57), sub),
    ...cubic(sub, P(Math.min(sub.x, ul.front + 4), 72), P(ul.front - 1.5, ul.bottom - 8), ulFront), ...quad(ulFront, P(ul.front + 3, ul.bottom + 0.5), ulIn)];
  const llIn = P(TEETH_X - 2, ll.top), llTop = P(ll.front, ll.top + 3), llLow = P(ll.front, ll.top + 13);
  // under the lower lip: a shallow, smooth groove (labiomental fold), the round of the chin, then the underside of
  // the jaw sweeping back to the neck. Vertical tangents at the groove, so there's no corner.
  const fold = P(CHIN_X + 2, Math.max(ll.top + 18, 117 + jaw)), chin = P(CHIN_X, 136 + jaw);
  const under = P(62, 158 + jaw), neck = P(96, 166 + jaw);
  const lower = [llIn, ...quad(llIn, P(ll.front + 2, ll.top), llTop), ...quad(llTop, P(ll.front - 1.5, ll.top + 8), llLow),
    ...cubic(llLow, P(ll.front + 1, ll.top + 15), P(fold.x, fold.y - 4), fold),
    ...cubic(fold, P(fold.x, fold.y + 5), P(CHIN_X, chin.y - 8), chin),
    ...cubic(chin, P(CHIN_X, chin.y + 10), P(48, under.y), under), ...quad(under, P(80, 163 + jaw), neck), P(112, 200)];
  return { upper, lower };
}
export const facePaths = (g: Geometry) => { const f = faceOutline(g); return { upper: toPath(f.upper, false), lower: toPath(f.lower, false) }; };

// ---------- the dark opening between the lips ----------
/** The air between the lips as a shape to fill dark (fading inwards when drawn): from the front of the lips back
 * past the teeth, exactly as tall as the lip gap. null when the lips are shut (p, b, m). Without it the open mouth
 * was drawn in the background colour and ㅏ looked nearly the same as ㅣ or p. */
export const OPENING_BACK_X = TEETH_X + 14; // how far into the mouth the dark reaches before it has faded out
export function mouthOpening(g: Geometry): Pt[] | null {
  const top = g.upperLip.bottom, bottom = g.lowerLip.top;
  if (bottom - top < 0.5) return null;
  // the front curves INWARDS between the two lips (they bulge forward around the opening), so the dark never
  // pokes out in front of the face
  const front = Math.min(g.upperLip.front, g.lowerLip.front) + 1;
  const inset = Math.min(4, (bottom - top) / 4);
  return [P(OPENING_BACK_X, top), P(front, top), ...quad(P(front, top), P(front + inset * 2, (top + bottom) / 2), P(front, bottom)), P(OPENING_BACK_X, bottom)];
}

// ---------- the playing screen's sound waves ("pop" look of components/MouthDiagram.tsx CutAway) ----------
/** The pop look's window: VIEW with 10 more units on the left, room for the waves in front of the lips. */
export const POP_VIEW = { x: VIEW.x - 10, y: VIEW.y, w: VIEW.w + 10, h: VIEW.h };

/** Blue waves in front of the lips for a GUST OF AIR the sound makes, not for an open mouth (a vowel has none).
 * puff = lib/mouthViews.ts side().puff: 0 none (vowels, tense ㅃ ㄸ ㄲ, b d g, nasals, f s and other fricatives),
 * 1 light (plain ㅂ ㄷ ㄱ ㅈ, h), 2 English p t k, 3 big (aspirated ㅋ ㅌ ㅍ ㅊ). One arc per step, each further out
 * and taller, at the middle of the lip gap (at the lips' meeting line when they are shut: the puff comes on the
 * release). h = half the arc's height; the arc bulges h * 0.55 to the left of x. */
export function soundWaves(g: Geometry, puff: number): { x: number; y: number; h: number }[] {
  const n = Math.max(0, Math.min(3, Math.round(puff)));
  const front = Math.min(g.upperLip.front, g.lowerLip.front);
  const y = (g.upperLip.bottom + g.lowerLip.top) / 2;
  return Array.from({ length: n }, (_, i) => ({ x: front - 3.5 - i * 4.5, y, h: 4 + i * 2.4 }));
}

// ---------- one plain-words label for "where it happens", with a line to the spot ----------
export type Callout = { text: string; at: Pt; textAt: Pt };
type Entry = { svg: Svg; kind: string; lips?: string | null };
const CHAR_W = 4.2; // average width of one Latin character at the 7-unit font the diagram uses
const HANGUL_W = 7; // a Hangul block is about as wide as the font is tall
const TEXT_Y = VIEW.y + 9; // all callouts sit in one row at the top of the picture
/** How wide a label draws at the diagram's 7-unit font (Korean labels are wider per character). */
export const textWidth = (text: string) => [...text].reduce((w, ch) => w + (/[\uac00-\ud7a3]/.test(ch) ? HANGUL_W : CHAR_W), 0);

function placeLabel(text: string, at: Pt): Callout {
  const w = textWidth(text);
  const x = Math.min(Math.max(at.x - w / 2, VIEW.x + 3), VIEW.x + VIEW.w - 3 - w);
  return { text, at, textAt: { x, y: TEXT_Y } };
}

/** The single most useful placement fact for this sound, or null if there's nothing specific to point at.
 * `say` turns the English label into the site language (the ENG / 한 switch). */
export function callout(e: Entry, g: Geometry, say: (english: string) => string = (x) => x): Callout | null {
  const place = (text: string, at: Pt) => placeLabel(say(text), at);
  const s = e.svg;
  if (e.kind === "vowel" || e.kind === "diphthong") return place("Highest point of the tongue", g.body);
  if (e.lips === "closed") return place("Lips pressed together", { x: g.upperLip.front + 2, y: g.upperLip.bottom });
  if (e.lips === "lip_to_teeth") return place("Lower lip on the upper teeth", { x: TEETH_X - 4, y: g.teeth.upperTip });
  if (s.tip === "raised") return place("Tip up, NOT touching the roof", g.tip);
  if (s.tip === "dental") return place("Tip at the edge of the upper teeth", g.tip);
  if (s.contact && s.tip === "alveolar") return place("Tip on the ridge behind the teeth", g.tip);
  if (s.contact && s.tip === "postalveolar") return place("Tongue tip just behind the ridge", g.tip);
  if (s.contact && s.tip === "palatal") return place("Front of the tongue on the hard palate", g.body);
  if (s.contact && s.tip === "down") return place("Back of the tongue on the soft palate", g.body);
  if (s.tip === "alveolar" || s.tip === "postalveolar") return place("Tip close to the ridge, not touching", g.tip);
  if (e.lips === "rounded") return place("Lips rounded and pushed forward", { x: g.lips.front, y: g.upperLip.bottom });
  return null;
}
