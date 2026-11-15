"use client";
// The loading screen between Animate and the animation: Blueberry in a random pose (a new one with every line),
// the bar, and short Korean lines about sounds typed jamo by jamo, each with its English gloss.
//
// The bar (lib/loading.ts) eases fast up to a random stop between 88% and 98% and waits there. When the page says the
// real answer is in (`done`), it fills smoothly to 100%, holds a moment, then calls onFinished so the animation shows.
// Visitors who ask for less motion get one finished line and a still Blueberry (the bar still moves: it is the news).

import { useEffect, useRef, useState, type ReactNode } from "react";
import LoadingBar from "@/components/LoadingBar";
import { useUi } from "@/components/UiLang";
import type { Key } from "@/lib/i18n";
import {
  DONE_HOLD_MS, FINISH_MS, TICK_MS, advanceLine, fakePct, finishPct, lineView, pickCap, startLines, type Pose,
} from "@/lib/loading";

const INK = "#111111";

// Blueberry's round body (shared by every pose), at the drawing's origin
const BODY = "M60 8 C92 8 112 30 112 60 C112 88 90 104 60 104 C30 104 8 88 8 60 C8 30 28 8 60 8 Z";
const Body = () => <path d={BODY} fill="#DCE8FF" stroke={INK} strokeWidth="4" />;
const Stem = () => <path d="M56 9 C54 0 64 -2 62 8" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />;
const Cheeks = ({ l = [26, 72], r = [94, 72] }: { l?: number[]; r?: number[] }) => (
  <>
    <ellipse cx={l[0]} cy={l[1]} rx="7" ry="4.5" fill="#FF9CC2" />
    <ellipse cx={r[0]} cy={r[1]} rx="7" ry="4.5" fill="#FF9CC2" />
  </>
);

// Each pose: its bilingual label, whether the whole picture bobs, and the drawing (160 x 152 units).
const POSE_ART: Record<Pose, { label: Key; bob: boolean; art: ReactNode }> = {
  nerd: {
    label: "poseNerd",
    bob: true,
    art: (
      <>
        <g transform="translate(20 0)">
          <Stem />
          <Body />
          <g className="blink">
            <ellipse cx="42" cy="56" rx="4.5" ry="5.5" fill={INK} />
            <ellipse cx="78" cy="56" rx="4.5" ry="5.5" fill={INK} />
          </g>
          <circle cx="42" cy="54" r="13" fill="#FFFFFF" fillOpacity="0.35" stroke={INK} strokeWidth="4" />
          <circle cx="78" cy="54" r="13" fill="#FFFFFF" fillOpacity="0.35" stroke={INK} strokeWidth="4" />
          <path d="M55 52 Q60 48 65 52" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />
          <Cheeks />
          <ellipse cx="60" cy="78" rx="5" ry="4" fill="#3A0F24" />
        </g>
        <g className="ld-tap">
          <rect x="36" y="80" width="88" height="46" rx="7" fill="#E7EAF2" stroke={INK} strokeWidth="4" />
          <path d="M80 97 C80 93 86 92 86 97 C86 101 80 104 80 106 C80 104 74 101 74 97 C74 92 80 93 80 97 Z"
            fill="#FF85B8" stroke={INK} strokeWidth="2" />
          <rect x="26" y="124" width="108" height="9" rx="4.5" fill="#C9CEDA" stroke={INK} strokeWidth="3.5" />
        </g>
        <g className="keys" stroke={INK} strokeWidth="2.5" strokeLinecap="round">
          <path d="M21 121 L14 116" /><path d="M20 129 L12 129" />
          <path d="M139 121 L146 116" /><path d="M140 129 L148 129" />
        </g>
      </>
    ),
  },
  detective: {
    label: "poseDetective",
    bob: true,
    art: (
      <g transform="translate(20 0)">
        <Body />
        <path d="M24 30 C28 -2 92 -2 96 30 Z" fill="#D6B48C" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
        <path d="M44 4 L40 30 M60 -1 L60 30 M76 4 L80 30 M30 18 L90 18" stroke="#8B6A45" strokeWidth="2.5" />
        <path d="M16 30 Q60 42 104 30 Q100 38 60 42 Q20 38 16 30 Z" fill="#C49C70" stroke={INK} strokeWidth="3.5" strokeLinejoin="round" />
        <circle cx="60" cy="-3" r="4.5" fill="#C49C70" stroke={INK} strokeWidth="3" />
        <g className="blink"><ellipse cx="40" cy="56" rx="5" ry="7" fill={INK} /></g>
        <Cheeks />
        <path d="M50 80 Q58 76 68 80" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />
        <g className="ld-search">
          <path d="M91 69 L110 90" stroke={INK} strokeWidth="8" strokeLinecap="round" />
          <circle cx="78" cy="55" r="19" fill="#FFFFFF" stroke={INK} strokeWidth="5" />
          <circle cx="78" cy="55" r="19" fill="#9CC0FF" fillOpacity="0.35" />
          <ellipse cx="78" cy="56" rx="7.5" ry="11" fill={INK} />
          <circle cx="81" cy="51" r="2.5" fill="#FFFFFF" />
        </g>
      </g>
    ),
  },
  pencil: {
    label: "posePencil",
    bob: true,
    art: (
      <>
        <g transform="translate(-10 0)">
          <Stem />
          <Body />
          <g className="blink">
            <ellipse cx="48" cy="58" rx="4.5" ry="5.5" fill={INK} />
            <ellipse cx="84" cy="58" rx="4.5" ry="5.5" fill={INK} />
          </g>
          <Cheeks />
          <path d="M58 78 Q66 82 74 78" fill="none" stroke={INK} strokeWidth="3.5" strokeLinecap="round" />
          <path d="M71 79 Q76 88 81 79 Z" fill="#FF7FB0" stroke={INK} strokeWidth="2.5" strokeLinejoin="round" />
        </g>
        <rect x="104" y="84" width="54" height="42" rx="4" fill="#FFF8E1" stroke={INK} strokeWidth="3.5" />
        <g fill="#FFFFFF" stroke={INK} strokeWidth="2">
          {[113, 123, 133, 143, 151].map((cx) => <circle key={cx} cx={cx} cy="84" r="2.5" />)}
        </g>
        {/* ㅎ (three strokes) then ㅇ, each drawn as the pencil tip passes */}
        <g fill="none" stroke={INK} strokeWidth="3" strokeLinecap="round">
          <path className="ld-h1" d="M120 92 L124 95" strokeDasharray="6" strokeDashoffset="6" />
          <path className="ld-h2" d="M114 99 H130" strokeDasharray="16" strokeDashoffset="16" />
          <path className="ld-h3" d="M122 103 a6 6 0 1 1 -0.01 0" strokeDasharray="38" strokeDashoffset="38" />
          <path className="ld-o1" d="M142 96 a8 8 0 1 1 -0.01 0" strokeDasharray="51" strokeDashoffset="51" />
        </g>
        <g className="ld-pen">
          <g transform="rotate(20)">
            <rect x="-4" y="-52" width="8" height="7" rx="2" fill="#FF9CC2" stroke={INK} strokeWidth="2.5" />
            <rect x="-4" y="-46" width="8" height="5" fill="#C9CEDA" stroke={INK} strokeWidth="2.5" />
            <rect x="-4" y="-42" width="8" height="32" fill="#FFD23F" stroke={INK} strokeWidth="2.5" />
            <path d="M-4 -10 L4 -10 L0 0 Z" fill="#F2C79A" stroke={INK} strokeWidth="2.5" strokeLinejoin="round" />
            <path d="M-1.6 -3.5 L1.6 -3.5 L0 0 Z" fill={INK} />
          </g>
        </g>
      </>
    ),
  },
  painter: {
    label: "posePainter",
    bob: true,
    art: (
      <>
        <g transform="translate(-10 0)">
          <Body />
          <g transform="rotate(-6 60 10)">
            <path d="M22 20 C20 2 44 -6 64 -4 C86 -2 100 8 98 18 C80 24 40 26 22 20 Z" fill="#E5383B" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
            <path d="M62 -4 L63 -11" stroke={INK} strokeWidth="4" strokeLinecap="round" />
          </g>
          <g className="blink">
            <ellipse cx="46" cy="54" rx="5" ry="7" fill={INK} />
            <ellipse cx="82" cy="54" rx="5" ry="7" fill={INK} />
          </g>
          <Cheeks l={[24, 70]} r={[90, 70]} />
          <path d="M54 74 Q64 84 74 74" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />
        </g>
        <path d="M102 104 L94 128 M146 104 L154 128 M124 104 L124 128" stroke="#8B6A45" strokeWidth="4" strokeLinecap="round" />
        <rect x="90" y="64" width="68" height="44" rx="3" fill="#FFFFFF" stroke={INK} strokeWidth="4" />
        <text x="124" y="95" textAnchor="middle" fontSize="24" fill="#7FCB98" className="font-display" lang="ko">한들</text>
        <rect className="ld-reveal" x="93" y="67" width="62" height="38" fill="#FFFFFF" />
        <rect x="88" y="106" width="72" height="5" rx="2" fill="#C49C70" stroke={INK} strokeWidth="2.5" />
        <g className="ld-float">
          <g transform="translate(-110 4)">
            <path d="M112 96 C112 84 128 80 142 84 C154 88 156 100 150 108 C146 114 138 110 134 116 C130 122 116 120 112 110 C110 104 112 100 112 96 Z"
              fill="#F2C79A" stroke={INK} strokeWidth="3.5" strokeLinejoin="round" />
            <circle cx="121" cy="108" r="3.5" fill="#FFFFFF" stroke={INK} strokeWidth="2" />
            <g stroke={INK} strokeWidth="1.5">
              <circle cx="122" cy="93" r="4.5" fill="#E5383B" />
              <circle cx="133" cy="89" r="4.5" fill="#FFD23F" />
              <circle cx="144" cy="93" r="4.5" fill="#2F6BFF" />
              <circle cx="146" cy="103" r="4.5" fill="#FF85B8" />
              <circle cx="132" cy="101" r="4.5" fill="#3CB371" />
            </g>
          </g>
        </g>
        <g className="ld-brush">
          <g transform="rotate(30)">
            <path d="M0 -14 L0 -44" stroke="#C49C70" strokeWidth="5" strokeLinecap="round" />
            <rect x="-3" y="-14" width="6" height="7" fill="#C9CEDA" stroke={INK} strokeWidth="2" />
            <ellipse cx="0" cy="-3" rx="3" ry="5" fill="#7FCB98" stroke={INK} strokeWidth="2" />
          </g>
        </g>
      </>
    ),
  },
  reader: {
    label: "poseReader",
    bob: false,
    art: (
      <>
        <g className="ld-read">
          <g transform="translate(20 0)">
            <Stem />
            <Body />
            <g className="blink">
              <ellipse cx="42" cy="61" rx="4.5" ry="5" fill={INK} />
              <ellipse cx="78" cy="61" rx="4.5" ry="5" fill={INK} />
            </g>
            <circle cx="78" cy="59" r="12" fill="#FFFFFF" fillOpacity="0.3" stroke="#C9A227" strokeWidth="3.5" />
            <path d="M89 65 C96 74 93 84 99 92" fill="none" stroke="#C9A227" strokeWidth="2" strokeLinecap="round" />
            <ellipse cx="26" cy="74" rx="7" ry="4.5" fill="#FF9CC2" />
            <ellipse cx="96" cy="76" rx="6" ry="4" fill="#FF9CC2" />
            <path d="M54 81 Q60 78 66 81" fill="none" stroke={INK} strokeWidth="3.5" strokeLinecap="round" />
          </g>
        </g>
        <path d="M80 102 C64 94 44 94 28 98 L28 131 C44 127 64 127 80 133 C96 127 116 127 132 131 L132 98 C116 94 96 94 80 102 Z"
          fill="#2F6BFF" stroke={INK} strokeWidth="3.5" strokeLinejoin="round" />
        <path d="M80 100 C66 93 48 93 34 97 L34 126 C48 122 66 122 80 128 Z" fill="#FFFFFF" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
        <path d="M80 100 C94 93 112 93 126 97 L126 126 C112 122 94 122 80 128 Z" fill="#FFFFFF" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
        <path d="M42 104 H72 M42 111 H72 M42 118 H64 M88 104 H118 M88 111 H118 M88 118 H110" stroke="#9AA3B5" strokeWidth="2" strokeLinecap="round" />
        <path className="ld-flip" d="M80 100 C94 93 112 93 126 97 L126 126 C112 122 94 122 80 128 Z"
          fill="#F4F8FF" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
      </>
    ),
  },
  sweeper: {
    label: "poseSweeper",
    bob: false,
    art: (
      <>
        <g className="ld-sway">
          <g transform="translate(-6 0)">
            <Stem />
            <Body />
            <g className="blink">
              <ellipse cx="48" cy="58" rx="4.5" ry="5.5" fill={INK} />
              <ellipse cx="82" cy="58" rx="4.5" ry="5.5" fill={INK} />
            </g>
            <Cheeks />
            <ellipse cx="66" cy="80" rx="4" ry="3.5" fill="#3A0F24" />
          </g>
        </g>
        <g className="ld-swing">
          <path d="M140 18 L114 106" stroke={INK} strokeWidth="7" strokeLinecap="round" />
          <path d="M140 18 L114 106" stroke="#C49C70" strokeWidth="3.5" strokeLinecap="round" />
          <path d="M102 104 L126 108 L128 128 L94 124 Z" fill="#F2C79A" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
          <path d="M104 112 L100 124 M112 113 L110 126 M120 114 L120 127" stroke="#C49C70" strokeWidth="2" />
          <path d="M101 107 L127 111" stroke="#E5383B" strokeWidth="4" />
        </g>
        <g className="ld-dust" fill="#E4E6EF" stroke={INK} strokeWidth="2">
          <circle cx="92" cy="127" r="6" /><circle cx="101" cy="123" r="5" /><circle cx="85" cy="122" r="4" />
        </g>
        <g className="ld-dust ld-dust-2" fill="#E4E6EF" stroke={INK} strokeWidth="2">
          <circle cx="138" cy="127" r="6" /><circle cx="147" cy="122" r="4.5" /><circle cx="131" cy="121" r="4" />
        </g>
        <g className="keys" stroke={INK} strokeWidth="2.5" strokeLinecap="round">
          <path d="M80 129 L72 129" /><path d="M154 129 L162 129" />
        </g>
      </>
    ),
  },
};

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export default function LoadingScreen({ done, onFinished }: { done: boolean; onFinished: () => void }) {
  const { t } = useUi();
  const [pct, setPct] = useState(0);
  // the screen only ever appears after a click, so the random start is made in the browser
  const [lines, setLines] = useState(() => {
    const s = startLines();
    return reducedMotion() ? { ...s, step: Number.MAX_SAFE_INTEGER } : s; // less motion: one finished line
  });
  const doneNow = useRef(done);
  const finish = useRef(onFinished);
  useEffect(() => {
    doneNow.current = done;
    finish.current = onFinished;
  }, [done, onFinished]);

  // the bar: one clock from the moment the screen appears; the real answer only switches it to "finish"
  useEffect(() => {
    const cap = pickCap();
    const start = performance.now();
    let doneAt: number | null = null;
    let from = 0;
    let last = 0;
    let id = 0;
    const tick = (now: number) => {
      if (doneNow.current && doneAt === null) {
        doneAt = now;
        from = last;
      }
      last = doneAt === null ? fakePct(now - start, cap) : finishPct(from, now - doneAt);
      setPct(last);
      if (doneAt !== null && now - doneAt >= FINISH_MS + DONE_HOLD_MS) return finish.current();
      id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, []);

  // the lines: one keystroke every TICK_MS (none when motion is reduced)
  useEffect(() => {
    if (reducedMotion()) return;
    const timer = setInterval(() => setLines((s) => advanceLine(s)), TICK_MS);
    return () => clearInterval(timer);
  }, []);

  const pose = POSE_ART[lines.pose];
  const { typed, gloss } = lineView(lines);

  return (
    <section className="mx-auto flex w-full max-w-[620px] flex-1 flex-col items-center justify-center py-6" data-testid="loading">
      <div className="flex flex-col items-center">
        <div className={`w-[220px] lg:w-[300px] ${pose.bob ? "ld-bob" : ""}`} data-pose={lines.pose}>
          <svg viewBox="0 -24 160 152" className="block h-auto w-full overflow-visible" role="img" aria-label={t(pose.label)}>
            {pose.art}
          </svg>
        </div>
        <span aria-hidden="true" className="ld-shadow -mt-1 block h-2.5 w-[130px] rounded-[50%] bg-ink lg:h-3.5 lg:w-[180px]" />
      </div>
      <div className="mt-[34px] w-full lg:mt-11">
        <LoadingBar pct={pct} />
      </div>
      <div className="mt-[18px] min-h-[58px] text-center lg:mt-[26px] lg:min-h-20">
        <p lang="ko" className="m-0 font-display text-[22px] lg:text-[32px]" data-testid="loading-line">
          {typed}
          <span className="caret text-blue" aria-hidden="true">|</span>
        </p>
        <p className="mt-1 mb-0 min-h-[18px] text-sm font-medium text-[#555555] lg:mt-1.5 lg:min-h-6 lg:text-lg">{gloss}</p>
      </div>
    </section>
  );
}
