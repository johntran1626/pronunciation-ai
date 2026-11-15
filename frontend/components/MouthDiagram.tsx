import { useId, useLayoutEffect, useRef, useState } from "react";
import { useUi } from "@/components/UiLang";
import { say } from "@/lib/i18n";
import type { ArticulationEntry } from "@/lib/api";
import { facePaths, floorPath, geometry, mouthOpening, textWidth, type Callout, OPENING_BACK_X, palateY, PHARYNX_X, POP_VIEW, soundWaves, tonguePath, VELUM_CTRL, VELUM_START, VIEW, type Geometry, type Pt } from "@/lib/mouth";
import { caption, front, LOWER_TOOTH_SHOWS, side, UPPER_TOOTH_SHOWS, views, type View } from "@/lib/mouthViews";

// Line-art mouth pictures in a line-art style (thin brown lines on a cream background, the key part
// in an accent colour). Two small pictures per sound, picked by lib/mouthViews.ts from articulation.json:
//   - "mirror" (front) view for every sound;
//   - side view (outside profile) when the action is visible from outside, with marks for airflow / voice;
//   - inside view (simple cut-away, geometry from lib/mouth.ts) when it's hidden (tongue on the ridge, English r,
//     k/g).
// They show the TEXTBOOK target for a sound, not a picture of the user's mouth.

const p = (pt: Pt) => `${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`;

const BG = "fill-[#f7f3ec] dark:fill-[#211d1a]";
const INK = "stroke-[#5b4b40] dark:stroke-[#d8cbbd]";
const ACCENT = "stroke-[#c2410c] dark:stroke-[#fb923c]";
const ACCENT_FILL = "fill-[#c2410c] dark:fill-[#fb923c]";
const MOUTH = "fill-[#e9ddd0] dark:fill-[#3a322c]"; // inside of the open mouth
const TONGUE = "fill-[#f1c6be] dark:fill-[#9c625c]";
const TEETH = "fill-white dark:fill-[#f3ede4]";
const line = { fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

// ---------- 1. mirror (front) view ----------
function FrontView({ e, focusLips, focusTongue }: { e: ArticulationEntry; focusLips: boolean; focusTongue: boolean }) {
  const f = front(e);
  const cx = 60, cy = 54;
  const hw = f.width / 2;
  const top = f.height * 0.45, bot = f.height * 0.55; // the opening is a little deeper below the centre line
  const round = e.svg.lip_round > 0.5;
  const lipInk = focusLips ? ACCENT : INK;
  // the opening between the lips: a lens, or an oval when the lips are rounded
  const opening = round
    ? `M ${cx - hw + 4} ${cy} C ${cx - hw + 4} ${cy - top * 1.3} ${cx + hw - 4} ${cy - top * 1.3} ${cx + hw - 4} ${cy} C ${cx + hw - 4} ${cy + bot * 1.3} ${cx - hw + 4} ${cy + bot * 1.3} ${cx - hw + 4} ${cy} Z`
    : `M ${cx - hw + 3} ${cy} Q ${cx} ${cy - 2 * top} ${cx + hw - 3} ${cy} Q ${cx} ${cy + 2 * bot} ${cx - hw + 3} ${cy} Z`;
  const upper = `M ${cx - hw} ${cy} C ${cx - hw * 0.65} ${cy - top - 9} ${cx - 7} ${cy - top - 10} ${cx} ${cy - top - 7} C ${cx + 7} ${cy - top - 10} ${cx + hw * 0.65} ${cy - top - 9} ${cx + hw} ${cy}`;
  const lower = `M ${cx - hw} ${cy} C ${cx - hw * 0.6} ${cy + bot + 12} ${cx + hw * 0.6} ${cy + bot + 12} ${cx + hw} ${cy}`;
  const clip = `front-${e.svg.tip}-${f.width}-${f.height}-${e.lips}`.replace(/[^a-zA-Z0-9-]/g, "");
  const teethRow = (y: number, h: number) => (
    <g>
      <rect x={cx - hw} y={y} width={2 * hw} height={h} className={`${TEETH} ${INK}`} strokeWidth={0.8} />
      {[-21, -15, -9, 0, 9, 15, 21].map((dx) => (
        <line key={dx} x1={cx + dx} y1={y} x2={cx + dx} y2={y + h} className={INK} strokeWidth={0.6} />
      ))}
    </g>
  );
  return (
    <svg viewBox="0 0 120 100" className="w-full" aria-hidden>
      <rect width={120} height={100} className={BG} />
      <g transform="translate(60 60) scale(1.5) translate(-60 -54)">
      {/* nose */}
      <path d="M 49 17 Q 45 24 51 26 M 71 17 Q 75 24 69 26 M 53 25 Q 56 29 60 27 Q 64 29 67 25" className={INK} strokeWidth={1.2} {...line} />
      {f.lowerLipUnderTeeth ? (
        <>
          {/* f, v: the upper teeth rest on the lower lip */}
          <path d={upper} className={INK} strokeWidth={1.4} {...line} />
          <path d={`M ${cx - hw + 3} ${cy - 1} Q ${cx} ${cy - 3} ${cx + hw - 3} ${cy - 1}`} className={INK} strokeWidth={1} {...line} />
          <path d={`M ${cx - 14} ${cy - 1.5} L ${cx - 14} ${cy + 3.5} L ${cx + 14} ${cy + 3.5} L ${cx + 14} ${cy - 1.5} Z`} className={`${TEETH} ${INK}`} strokeWidth={0.9} />
          {[-7, 0, 7].map((dx) => <line key={dx} x1={cx + dx} y1={cy - 1.5} x2={cx + dx} y2={cy + 3.5} className={INK} strokeWidth={0.6} />)}
          <path d={`M ${cx - hw} ${cy + 1} Q ${cx} ${cy + 3} ${cx + hw} ${cy + 1}`} className={ACCENT} strokeWidth={1.4} {...line} />
          <path d={`M ${cx - hw} ${cy + 1} C ${cx - hw * 0.6} ${cy + 13} ${cx + hw * 0.6} ${cy + 13} ${cx + hw} ${cy + 1}`} className={ACCENT} strokeWidth={1.6} {...line} />
        </>
      ) : f.closed ? (
        <>
          <path d={upper} className={lipInk} strokeWidth={1.5} {...line} />
          <path d={lower} className={lipInk} strokeWidth={1.5} {...line} />
          <path d={`M ${cx - hw + 2} ${cy} Q ${cx} ${cy + 1.5} ${cx + hw - 2} ${cy}`} className={lipInk} strokeWidth={1.6} {...line} />
        </>
      ) : (
        <>
          <defs>
            <clipPath id={clip}>
              <path d={opening} />
            </clipPath>
          </defs>
          <path d={opening} className={MOUTH} />
          <g clipPath={`url(#${clip})`}>
            {f.tongue === "low" && <ellipse cx={cx} cy={cy + bot + 1} rx={hw * 0.55} ry={5} className={`${TONGUE} ${INK}`} strokeWidth={0.8} />}
            {f.tongue === "tip_up" && (
              // the tongue rises BEHIND the upper teeth: drawn first, so the teeth cover its tip;
              // the centre line is the underside of the raised tongue
              <>
                <path d={`M ${cx - 12} ${cy + bot + 2} C ${cx - 12} ${cy} ${cx - 7} ${cy - top + 1} ${cx} ${cy - top + 1} C ${cx + 7} ${cy - top + 1} ${cx + 12} ${cy} ${cx + 12} ${cy + bot + 2} Z`} className={`${TONGUE} ${focusTongue ? ACCENT : INK}`} strokeWidth={1.3} />
                <line x1={cx} y1={cy - top + 7} x2={cx} y2={cy + bot} className={INK} strokeWidth={0.6} />
              </>
            )}
            {f.upperTeeth && teethRow(cy - top - 1, 5.5)}
            {f.lowerTeeth && teethRow(cy + bot - 3.5, 4)}
          </g>
          {f.tongue === "out" && (
            <>
              <path d={`M ${cx - 11} ${cy - 1} C ${cx - 11} ${cy + bot + 8} ${cx + 11} ${cy + bot + 8} ${cx + 11} ${cy - 1}`} className={`${TONGUE} ${ACCENT}`} strokeWidth={1.4} />
              <line x1={cx} y1={cy + 1} x2={cx} y2={cy + bot + 3} className={INK} strokeWidth={0.6} />
            </>
          )}
          <path d={opening} className={lipInk} strokeWidth={1.1} {...line} />
          <path d={upper} className={lipInk} strokeWidth={1.4} {...line} />
          <path d={lower} className={lipInk} strokeWidth={1.4} {...line} />
        </>
      )}
      </g>
    </svg>
  );
}

// ---------- 2. side (outside profile) view: face looks LEFT ----------
function SideView({ e, focusLips }: { e: ArticulationEntry; focusLips: boolean }) {
  const s = side(e);
  const pr = s.protrude;
  const o = s.open;
  const lipInk = focusLips ? ACCENT : INK;
  const lipY = 47; // where the lips meet
  // profile pieces: nose, upper lip, lower lip, chin + jaw
  const nose = "M 36 4 Q 31 16 20 26 Q 17 30 22 31 Q 27 31 30 33";
  const upperLip = `M 30 33 Q ${29 - pr} 38 ${27 - pr} ${lipY - 3 - o / 2} Q ${26 - pr} ${lipY - o / 2} ${31 - pr * 0.4} ${lipY - o / 2}`;
  const lowerFront = s.lowerLipTucked ? 33 : 28 - pr;
  const lowerTop = s.lowerLipTucked ? lipY - 1 : lipY + o / 2;
  const lowerLip = `M ${lowerFront + 3} ${lowerTop} Q ${lowerFront - 1} ${lowerTop} ${lowerFront} ${lowerTop + 4} Q ${lowerFront + 1} ${lowerTop + 8} ${33 - pr * 0.3} ${lowerTop + 9}`;
  const chin = `M ${33 - pr * 0.3} ${lowerTop + 9} Q 37 ${lowerTop + 11} 34 ${lowerTop + 15} Q 29 ${lowerTop + 23} 38 ${lowerTop + 30} Q 50 ${lowerTop + 35} 74 ${lowerTop + 33}`;
  const throatY = Math.min(84, lowerTop + 36); // front of the neck, where the voice box is
  return (
    <svg viewBox="2 4 96 80" className="w-full" aria-hidden>
      <rect width={120} height={100} className={BG} />
      <path d={nose} className={INK} strokeWidth={1.3} {...line} />
      <path d="M 26 27 Q 29 26 30 28" className={INK} strokeWidth={0.9} {...line} />
      {/* teeth showing between the lips: each shows only a little past its own lip (see UPPER/LOWER_TOOTH_SHOWS),
          so an open mouth has a visible gap between them */}
      {s.lowerLipTucked ? (
        <path d={`M 31 ${lipY - 2} L 34.5 ${lipY - 2} L 34 ${lipY + 1.5} Q 32 ${lipY + 2} 31 ${lipY + 1} Z`} className={`${TEETH} ${INK}`} strokeWidth={0.8} />
      ) : (
        o >= 2 && (
          <path d={`M 31 ${lipY - o / 2 - 2} L 34.5 ${lipY - o / 2 - 2} L 34 ${lipY - o / 2 + UPPER_TOOTH_SHOWS} Q 32 ${lipY - o / 2 + UPPER_TOOTH_SHOWS + 0.8} 31 ${lipY - o / 2 + UPPER_TOOTH_SHOWS} Z`} className={`${TEETH} ${INK}`} strokeWidth={0.8} />
        )
      )}
      {o >= 3 && !s.lowerLipTucked && (
        <path d={`M 32 ${lipY + o / 2 - LOWER_TOOTH_SHOWS} Q 33.5 ${lipY + o / 2 - LOWER_TOOTH_SHOWS - 0.8} 35 ${lipY + o / 2 - LOWER_TOOTH_SHOWS} L 35 ${lipY + o / 2 + 2} L 32.5 ${lipY + o / 2 + 2} Z`} className={`${TEETH} ${INK}`} strokeWidth={0.8} />
      )}
      {s.tongueOut && (
        <path d={`M 34 ${lipY - 1} Q 26 ${lipY - 1} 26 ${lipY + 1.5} Q 27 ${lipY + 3.5} 34 ${lipY + 2.5}`} className={`${TONGUE} ${ACCENT}`} strokeWidth={1.3} />
      )}
      <path d={upperLip} className={lipInk} strokeWidth={1.4} {...line} />
      <path d={lowerLip} className={s.lowerLipTucked ? ACCENT : lipInk} strokeWidth={s.lowerLipTucked ? 1.7 : 1.4} {...line} />
      <path d={chin} className={INK} strokeWidth={1.3} {...line} />
      <path d={`M 74 ${lowerTop + 33} Q 76 ${lowerTop + 40} 78 100`} className={INK} strokeWidth={1.1} {...line} />
      {/* airflow: puff marks in front of the lips */}
      {Array.from({ length: s.puff }, (_, i) => (
        <path key={i} d={`M ${20 - pr - i * 4.5} ${lipY - 4} Q ${17 - pr - i * 4.5} ${lipY} ${20 - pr - i * 4.5} ${lipY + 4}`} className={ACCENT} strokeWidth={1.2} {...line} />
      ))}
      {/* air through the nose */}
      {s.nose && [0, 1].map((i) => <path key={i} d={`M ${18 - i * 4} 30 Q ${15 - i * 4} 33 ${18 - i * 4} 36`} className={ACCENT} strokeWidth={1.1} {...line} />)}
      {/* voice on: a buzz in the throat; tense: throat squeezed */}
      {s.voice && <path d={`M 77 ${throatY - 4} q 2 -2 4 0 t 4 0 t 4 0 t 4 0`} className={ACCENT} strokeWidth={1.1} {...line} />}
      {s.tight && <path d={`M 76 ${throatY - 9} l 4 4 l -4 4 M 92 ${throatY - 9} l -4 4 l 4 4`} className={ACCENT} strokeWidth={1.2} {...line} />}
    </svg>
  );
}

// ---------- 3. inside view (simple cut-away, line art) ----------
function InsideView({ e }: { e: ArticulationEntry }) {
  return <CutAway g={geometry(e.svg, e.kind, e.lips)} e={e} />;
}

// Two looks for the same drawing. "line" = the cream line art of the detail card (with its other views);
// "pop" = the site's style for the playing screen: black outlines, pink tongue, no background of its own (it
// sits on the card's tray colour), no dark mouth opening, and blue waves in front of the lips for a puff of air.
type Look = "line" | "pop";
const LOOK = {
  line: { bg: BG, ink: INK, tongue: `${TONGUE} ${ACCENT}`, teeth: TEETH, accent: "text-[#c2410c] dark:text-[#fb923c]", dot: `${ACCENT_FILL} stroke-white`, w: 1 },
  pop: { bg: "fill-tray", ink: "stroke-ink", tongue: "fill-[#FFB3D1] stroke-ink", teeth: "fill-white", accent: "text-blue", dot: "fill-blue stroke-ink", w: 1.3 },
} as const;
// The cut-away drawing from a Geometry alone, so the native animation (lib/animate.ts) can draw any
// in-between frame. With `e` (one sound's entry) it also draws that sound's contact dot / "gap" marks.
// `puff` (pop look only): how much air the sound pushes out (mouthViews side().puff, 0-3) -> that many blue waves.
export function CutAway({ g, e, mark, look = "line", puff = 0 }: { g: Geometry; e?: ArticulationEntry; mark?: Callout | null; look?: Look; puff?: number }) {
  const { ui } = useUi();
  const L = LOOK[look];
  const pop = look === "pop";
  const sw = (n: number) => n * L.w;
  const { body: b, tip: t, velumTip: v, teeth } = g;
  const lt = teeth.lowerTop;
  const tongue = tonguePath(g);
  const floorTop = floorPath(g);
  const roof = `M 50 86 L 56 80 L 62 77 L 72 72 L 85 68 L 100 66 L ${VELUM_START.x} ${VELUM_START.y}`;
  const { upper: face, lower: lowerFace } = facePaths(g); // Lib/mouth.ts faceOutline (tested)
  const upperTooth = `M 47 ${teeth.upperRoot} L 56 ${teeth.upperRoot} Q 55 84 51.5 ${teeth.upperTip + 0.5} Q 49 ${teeth.upperTip + 1} 48 ${teeth.upperTip - 1} Q 45.5 84 47 ${teeth.upperRoot} Z`;
  const lowerTooth = `M 49 ${lt + 1} Q 51 ${lt - 1.5} 53 ${lt + 0.5} Q 57 ${lt + 8} 57 ${teeth.lowerRoot} L 48 ${teeth.lowerRoot} Q 47.5 ${lt + 8} 49 ${lt + 1} Z`;
  const opening = pop ? null : mouthOpening(g); // null when the lips are shut (p, b, m)
  const id = useId().replace(/:/g, "");
  const fade = `mouth-${id}`;
  const touch = !e ? null : e.svg.contact ? (e.svg.tip === "down" || e.svg.tip === "palatal" ? b : t) : null;
  const vb = pop ? POP_VIEW : VIEW;
  // the label's box fits the text as the browser drew it (the estimate in lib/mouth.ts runs wide for the site font)
  const label = useRef<SVGTextElement>(null);
  const [drawn, setDrawn] = useState<{ text: string; w: number } | null>(null);
  useLayoutEffect(() => {
    if (pop && mark && label.current) setDrawn({ text: mark.text, w: label.current.getComputedTextLength() });
  }, [pop, mark?.text]); // eslint-disable-line react-hooks/exhaustive-deps
  const labelW = mark ? (pop && drawn?.text === mark.text ? drawn.w : textWidth(mark.text)) : 0;
  return (
    <svg viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`} className="w-full" aria-hidden>
      {pop && (
        // the lines that leave the picture (forehead, neck, throat) fade out instead of stopping at a hard edge
        <defs>
          <linearGradient id={`edge-${id}`} gradientUnits="userSpaceOnUse" x1={0} y1={vb.y} x2={0} y2={vb.y + vb.h}>
            <stop offset="0" stopColor="white" stopOpacity={0} />
            <stop offset="0.1" stopColor="white" />
            <stop offset="0.9" stopColor="white" />
            <stop offset="1" stopColor="white" stopOpacity={0} />
          </linearGradient>
          <mask id={`edges-${id}`} maskUnits="userSpaceOnUse" x={vb.x} y={vb.y} width={vb.w} height={vb.h}>
            <rect x={vb.x} y={vb.y} width={vb.w} height={vb.h} fill={`url(#edge-${id})`} />
          </mask>
          <clipPath id={`tongue-${id}`}>
            <path d={tongue} />
          </clipPath>
          <clipPath id={`shine-${id}`}>
            <rect x={t.x + 8} y={0} width={Math.max(0, b.x + 14 - (t.x + 8))} height={200} />
          </clipPath>
        </defs>
      )}
      <g mask={pop ? `url(#edges-${id})` : undefined}>
      {!pop && <rect x={0} y={0} width={220} height={200} className={L.bg} />}
      {/* line look: the open mouth dark between the lips, fading towards the back (tongue, teeth, face on top) */}
      {opening && (
        <>
          <defs>
            <linearGradient id={fade} gradientUnits="userSpaceOnUse" x1={Math.min(...opening.map((q) => q.x))} y1={0} x2={OPENING_BACK_X} y2={0}>
              <stop offset="0" className="[stop-color:#3b2a22] dark:[stop-color:#0b0908]" stopOpacity={0.85} />
              <stop offset="1" className="[stop-color:#3b2a22] dark:[stop-color:#0b0908]" stopOpacity={0} />
            </linearGradient>
          </defs>
          <path d={`M ${opening.map(p).join(" L ")} Z`} fill={`url(#${fade})`} />
        </>
      )}
      <path d={face} className={L.ink} strokeWidth={sw(1.6)} {...line} />
      <path d={lowerFace} className={L.ink} strokeWidth={sw(1.6)} {...line} />
      {/* roof of the mouth: hard palate, then the soft palate hanging at the back */}
      <path d={roof} className={L.ink} strokeWidth={sw(pop ? 1.7 : 2)} {...line} />
      <path d={`M ${VELUM_START.x} ${VELUM_START.y} Q ${VELUM_CTRL.x} ${VELUM_CTRL.y} ${p(v)}`} className={L.ink} strokeWidth={pop ? 3.6 : 3.5} {...line} />
      <path d={`M ${PHARYNX_X + 2} 62 Q ${PHARYNX_X + 6} 130 ${PHARYNX_X} 200`} className={L.ink} strokeWidth={sw(1.4)} {...line} />
      <path d={tongue} className={L.tongue} strokeWidth={sw(pop ? 1.6 : 1.8)} strokeLinejoin="round" />
      {pop && (
        // a soft shine along the top of the tongue: its own outline, nudged down and in, kept inside the tongue
        // and only over the middle of the body (not the tip, not the root)
        <g clipPath={`url(#tongue-${id})`}>
          <g clipPath={`url(#shine-${id})`}>
            <path d={tongue} transform="translate(1.5 3.2)" stroke="#FFD6E6" strokeWidth={2.4} {...line} />
          </g>
        </g>
      )}
      {/* floor of the mouth covers the tongue's lower part, so it sits in the jaw */}
      <path d={`${floorTop} L 157 200 L 58 200 Z`} className={L.bg} />
      <path d={floorTop} className={L.ink} strokeWidth={sw(1.4)} {...line} />
      <path d={upperTooth} className={`${L.teeth} ${L.ink}`} strokeWidth={sw(1.2)} strokeLinejoin="round" />
      <path d={lowerTooth} className={`${L.teeth} ${L.ink}`} strokeWidth={sw(1.2)} strokeLinejoin="round" />
      {/* pop look: the gust of air some sounds make (ㅋ, English p), as blue waves */}
      {pop && (
        <g className="text-blue" data-testid="waves">
          {soundWaves(g, puff).map((w, i) => (
            <path key={i} d={`M ${w.x + w.h * 0.45} ${w.y - w.h} Q ${w.x - w.h * 0.55} ${w.y} ${w.x + w.h * 0.45} ${w.y + w.h}`}
              fill="none" stroke="currentColor" strokeWidth={2.1} strokeLinecap="round" />
          ))}
        </g>
      )}
      </g>
      {/* tip up but NOT touching (English r, s, z, sh): mark the gap so the picture matches "not touching" */}
      {e && !e.svg.contact && ["raised", "alveolar", "postalveolar"].includes(e.svg.tip) && (
        <g className={L.accent}>
          <line x1={t.x} y1={t.y - 1.5} x2={t.x} y2={palateY(t.x) + 1.5} stroke="currentColor" strokeWidth={1.3} />
          <path d={`M ${t.x - 2} ${palateY(t.x) + 3} L ${t.x} ${palateY(t.x) + 1} L ${t.x + 2} ${palateY(t.x) + 3} M ${t.x - 2} ${t.y - 3} L ${t.x} ${t.y - 1} L ${t.x + 2} ${t.y - 3}`} fill="none" stroke="currentColor" strokeWidth={1} />
          <text x={t.x + 4} y={(t.y + palateY(t.x)) / 2 + 2.5} fill="currentColor" fontSize={7} fontWeight={600}>{say(ui)("gap")}</text>
        </g>
      )}
      {touch && <circle cx={touch.x} cy={touch.y} r={3.4} className={L.dot} strokeWidth={1.2} />}
      {/* "show what matters": a ring on the defining contact or shape, a thin line up to its plain-words label */}
      {mark && (
        <g className={L.accent} data-testid="mark">
          <line x1={mark.textAt.x + Math.min(labelW / 2, Math.max(4, mark.at.x - mark.textAt.x))} y1={mark.textAt.y + 2}
            x2={mark.at.x} y2={mark.at.y - 6} stroke="currentColor" strokeWidth={0.8} strokeDasharray="2 1.5" />
          <circle cx={mark.at.x} cy={mark.at.y} r={6} fill="currentColor" fillOpacity={0.18} stroke="currentColor" strokeWidth={pop ? 1.8 : 1.4} />
          {pop ? (
            <rect x={mark.textAt.x - 2.5} y={mark.textAt.y - 7.5} width={labelW + 5} height={10.5} rx={3} className="fill-white stroke-ink" strokeWidth={1} />
          ) : (
            <rect x={mark.textAt.x - 2} y={mark.textAt.y - 7} width={textWidth(mark.text) + 4} height={9.5} rx={2} className={L.bg} fillOpacity={0.9} />
          )}
          <text ref={label} x={mark.textAt.x} y={mark.textAt.y} fill="currentColor" fontSize={7} fontWeight={600}>{mark.text}</text>
        </g>
      )}
    </svg>
  );
}

function badges(e: ArticulationEntry): string[] {
  const out = [e.voicing === "voiced" ? "Voice on" : "Voice off"];
  if (e.manner === "nasal") out.push("Air through the nose");
  if (e.laryngeal === "aspirated") out.push("Big puff of air");
  if (e.laryngeal === "tense") out.push("Throat tight, no puff");
  if (e.laryngeal === "plain" && e.manner === "stop") out.push("Light puff");
  return out;
}

const VIEW_NAME: Record<View, string> = { front: "Mirror view", side: "Side view", inside: "Inside the mouth" };

export default function MouthDiagram({
  entry,
  title,
  tone = "target",
  description,
}: {
  entry: ArticulationEntry;
  title: string;
  tone?: "target" | "yours";
  description?: string; // the sound's description in the site language (default: the table's English)
}) {
  const { ui } = useUi();
  const sayIt = say(ui);
  const [, second] = views(entry);
  const vowel = entry.kind === "vowel" || entry.kind === "diphthong";
  // highlight the lips only when they ARE the key action (p/b/m, f/v via the side view, rounded vowels and w);
  // for English r / sh the lips round a little, but the key action is the tongue (inside view)
  const focusLips = vowel || entry.lips === "closed" || (entry.lips === "rounded" && second === "side");
  const focusTongue = entry.svg.tip === "alveolar" || entry.svg.tip === "dental";
  const ring = tone === "target" ? "border-green-600" : "border-amber-500";
  const s = side(entry);
  const marks: string[] = [];
  if (second === "side") {
    if (s.puff) marks.push(sayIt(") ) )  puff of air"));
    if (s.nose) marks.push(sayIt(")  air through the nose"));
    if (s.voice) marks.push(sayIt("∿  voice on (buzz in the throat)"));
    if (s.tight) marks.push(sayIt("> <  throat tight"));
  }
  return (
    <figure className={`flex flex-col gap-2 rounded-lg border-2 ${ring} p-3`} aria-label={`${title}: ${entry.description}`}>
      <figcaption className="flex flex-col">
        <span className="font-medium">{title}</span>
        <span className="text-base font-semibold text-[#c2410c] dark:text-[#fb923c]">{caption(entry, sayIt)}</span>
      </figcaption>
      <div className="grid grid-cols-2 gap-2">
        {(["front", second] as View[]).map((v) => (
          <div key={v} className="flex flex-col gap-0.5 overflow-hidden rounded-md border border-[#e5dccf] dark:border-[#3a322c]">
            {v === "front" && <FrontView e={entry} focusLips={focusLips} focusTongue={focusTongue} />}
            {v === "side" && <SideView e={entry} focusLips={focusLips} />}
            {v === "inside" && <InsideView e={entry} />}
            <span className="px-1.5 pb-1 text-[11px] text-neutral-500">{sayIt(VIEW_NAME[v])}</span>
          </div>
        ))}
      </div>
      {marks.length > 0 && <p className="text-[11px] text-neutral-500">{marks.join("   ·   ")}</p>}
      <ul className="flex flex-wrap gap-1.5 text-xs">
        {badges(entry).map((x) => (
          <li key={x} className="rounded bg-neutral-100 px-1.5 py-0.5 dark:bg-neutral-800">
            {sayIt(x)}
          </li>
        ))}
      </ul>
      <p className="text-sm text-neutral-600 dark:text-neutral-400">{description ?? entry.description}</p>
    </figure>
  );
}
