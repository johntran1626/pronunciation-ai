// What each picture shows, decided from the articulation facts (pure; tested in mouthViews.test.ts).
// Goal: a viewer looks once and knows where to put lips, teeth and tongue. Style follows the line-art
// reference he chose: a "mirror" (front) view of the mouth for every sound, plus
//   - a SIDE view (outside profile) when the key action is visible from outside (lips, teeth, tongue between the
//     teeth, airflow), or
//   - an INSIDE view (simple cut-away, components/MouthDiagram InsideView) when it happens out of sight
//     (tongue on the ridge, R not touching, K/G at the back).
import { callout, geometry, type Svg } from "./mouth.ts";

export type Entry = {
  kind: string;
  manner?: string | null;
  voicing?: string | null;
  laryngeal?: string | null;
  lips?: string | null;
  svg: Svg;
};
export type View = "front" | "side" | "inside";

const isVowel = (e: Entry) => e.kind === "vowel" || e.kind === "diphthong";

/** Is the key action hidden inside the mouth? Then the second picture is the inside view. */
function hidden(e: Entry): boolean {
  if (isVowel(e)) return false;
  const t = e.svg.tip;
  return t === "alveolar" || t === "postalveolar" || t === "palatal" || t === "raised" || (t === "down" && e.svg.contact);
}

export function views(e: Entry): [View, View] {
  return ["front", hidden(e) ? "inside" : "side"];
}

/** What the mirror view shows in blue (the key part): the lips when they ARE the action (p/b/m, f/v, every vowel,
 * w and other rounding you can see from the side), the tongue when its tip is the action you can see (l, t, d, n,
 * TH). English r / sh round the lips a little, but their key action is the tongue (hidden), so nothing is blue. */
export function keyParts(e: Entry): { lips: boolean; tongue: boolean } {
  const lips = isVowel(e) || e.lips === "closed" || (e.lips === "rounded" && views(e)[1] === "side");
  return { lips, tongue: e.svg.tip === "alveolar" || e.svg.tip === "dental" };
}

// ---------- mirror (front) view ----------
export type Front = {
  width: number; // mouth width (drawing units, out of a 120-wide picture)
  height: number; // how far the lips are apart
  closed: boolean;
  upperTeeth: boolean;
  lowerTeeth: boolean;
  lowerLipUnderTeeth: boolean; // f, v
  tongue: "out" | "tip_up" | "low" | "hidden";
};

export function front(e: Entry): Front {
  const s = e.svg;
  const jawOpen = isVowel(e) ? 1 - s.tongue_y : 0; // open vowels drop the jaw
  let width = (e.lips === "spread" ? 46 : 40) * (1 - 0.42 * s.lip_round);
  let height = e.lips === "closed" ? 0 : (3 + s.lip_gap * 8 + jawOpen * 14) * (1 - 0.15 * s.lip_round);
  const lipToTeeth = e.lips === "lip_to_teeth";

  let tongue: Front["tongue"] = "hidden";
  if (s.tip === "dental") {
    tongue = "out"; // TH: the tip shows between the teeth
    height = Math.max(height, 8);
  } else if (s.tip === "alveolar" && s.contact) {
    tongue = "tip_up"; // l, t, d, n, ㄹ: open a little and you can see the tip up behind the top teeth
    height = Math.max(height, 13);
  } else if (s.tip === "down" && height >= 9) {
    tongue = "low"; // resting behind the lower teeth
  }
  if (lipToTeeth) height = 4;
  width = Math.round(width * 10) / 10;
  const closed = e.lips === "closed";
  return {
    width,
    height: Math.round(height * 10) / 10,
    closed,
    upperTeeth: !closed && (lipToTeeth || height >= 4),
    lowerTeeth: !closed && !lipToTeeth && height >= 6, // s/z: both rows close together
    lowerLipUnderTeeth: lipToTeeth,
    tongue,
  };
}

// ---------- side (outside profile) view ----------
export type Side = {
  protrude: number; // how far rounding pushes the lips forward
  open: number; // gap between the lips
  teethGap: number; // gap between the upper and lower teeth as seen from the side (<= 0: teeth together)
  lowerLipTucked: boolean; // f, v
  tongueOut: boolean; // th
  puff: number; // puff-of-air marks in front of the mouth (0 = none, 3 = big)
  nose: boolean; // air through the nose (m, n, ng)
  voice: boolean; // voice on (buzz in the throat)
  tight: boolean; // Korean tense: throat tight
};

function puffOf(e: Entry): number {
  if (e.manner !== "stop" && e.manner !== "affricate") {
    return e.manner === "fricative" && e.svg.tip === "down" && e.lips === "neutral" ? 1 : 0; // h: just a breath
  }
  if (e.laryngeal === "aspirated") return 3;
  if (e.laryngeal === "plain") return 1;
  if (e.laryngeal === "tense") return 0;
  return e.voicing === "voiceless" ? 2 : 0; // English p t k: a clear puff (in stressed syllables); b d g: none
}

// From the side, each tooth shows a little past its lip: the upper one hangs below the upper lip, the lower one
// rises above the lower lip. The old drawing let the upper tooth reach the middle of the
// mouth, so every open vowel (ㅓ, ㅐ) looked like a clenched bite, contradicting "mouth half open".
export const UPPER_TOOTH_SHOWS = 2.5;
export const LOWER_TOOTH_SHOWS = 1.5;

export function side(e: Entry): Side {
  const f = front(e);
  const s = e.svg;
  const jawOpen = isVowel(e) ? 1 - s.tongue_y : 0;
  // the side opening follows the jaw; rounding narrows the mouth from the FRONT but barely closes it from the side
  const open = f.closed ? 0 : e.lips === "lip_to_teeth" ? 1 : Math.max(f.height, 3 + s.lip_gap * 8 + jawOpen * 14) * 0.6;
  const teethGap = e.lips === "lip_to_teeth" ? -1 : open - UPPER_TOOTH_SHOWS - LOWER_TOOTH_SHOWS;
  return {
    protrude: Math.round(s.lip_round * 6 * 10) / 10,
    open: Math.round(open * 10) / 10,
    teethGap: Math.round(teethGap * 10) / 10,
    lowerLipTucked: e.lips === "lip_to_teeth",
    tongueOut: e.svg.tip === "dental",
    puff: puffOf(e),
    nose: e.manner === "nasal",
    voice: e.voicing === "voiced",
    tight: e.laryngeal === "tense",
  };
}

// ---------- the one-line caption ----------
// what happens to the air after a stop, appended to the placement line ("Lips pressed together, then a light puff")
export const airflowPhrases = ["then a big puff of air", "then a light puff", "throat tight, no puff", "then a puff of air"];
type Say = (english: string) => string;
function airflow(e: Entry, say: Say): string {
  if (e.manner !== "stop" && e.manner !== "affricate") return "";
  const [big, light, tight, puff] = airflowPhrases;
  if (e.laryngeal === "aspirated") return `, ${say(big)}`;
  if (e.laryngeal === "plain") return `, ${say(light)}`;
  if (e.laryngeal === "tense") return `, ${say(tight)}`;
  return e.voicing === "voiceless" ? `, ${say(puff)}` : "";
}

/** Where things go, in one plain line (shown big under the sound's name). */
export function caption(e: Entry, say: Say = (x) => x): string {
  const s = e.svg;
  if (isVowel(e)) {
    const lips = e.lips === "rounded" ? "Lips rounded and pushed forward" : e.lips === "spread" ? "Lips spread, like a slight smile" : "Lips relaxed";
    // four steps, so neighbours differ (ㅐ half open vs ㅔ slightly open; ship slightly open vs sheep almost closed)
    const jaw = s.tongue_y < 0.25 ? "mouth open wide" : s.tongue_y < 0.5 ? "mouth half open" : s.tongue_y < 0.9 ? "mouth slightly open" : "mouth almost closed";
    return `${say(lips)}, ${say(jaw)}`;
  }
  if (s.tip === "dental") return say("Tongue tip lightly between the teeth");
  const c = callout(e, geometry(s, e.kind, e.lips ?? undefined), say);
  if (c) return c.text + airflow(e, say);
  if (s.tip === "palatal") return say("Front of the tongue up near the roof");
  if (e.manner === "fricative") return say("Mouth open, breathe out");
  return say("Mouth relaxed");
}
