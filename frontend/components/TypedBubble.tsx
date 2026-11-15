"use client";
// Blueberry's speech bubble on the home page. useTypedLines() runs the clock (one keystroke every TICK_MS, lines in
// a fresh shuffle each round); <TypedBubble> draws it. The page calls the hook once and hands the same state to the
// phone bubble and the desktop bubble, so both say the same thing.
//
// - Hover (or keyboard focus) pauses the typing, so a GitHub / LinkedIn line can be clicked before it moves on.
// - Visitors who ask for less motion get one finished line and no clock at all.
// - Before the page is live in the browser the bubble is empty (the shuffle is random, so the server can't draw it).

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { HOME_LINES, TICK_MS, advance, startTyping, view, type Typing } from "@/lib/home";

export function useTypedLines() {
  const [state, setState] = useState<Typing | null>(null);
  const paused = useRef(false);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const first = startTyping(HOME_LINES.length);
    if (reduced) {
      setState({ ...first, step: Number.MAX_SAFE_INTEGER }); // eslint-disable-line react-hooks/set-state-in-effect -- random start, browser only
      return;
    }
    setState(first);
    const timer = setInterval(() => {
      if (!paused.current) setState((s) => (s ? advance(s, HOME_LINES.length) : s));
    }, TICK_MS);
    return () => clearInterval(timer);
  }, []);

  return {
    state, // the raw position (the typewriter uses it for its sounds and paper)
    shown: state ? view(state, HOME_LINES) : null,
    pause: (on: boolean) => { paused.current = on; },
  };
}

type Typed = ReturnType<typeof useTypedLines>;

// The cloud's bumps: x = where along the edge (%), at = which edge, s = diameter in px on desktop (phone: 60%).
const BUMPS: { x: number; at: "top" | "bottom" | "left" | "right"; s: number }[] = [
  { x: 20, at: "top", s: 56 }, { x: 46, at: "top", s: 72 }, { x: 74, at: "top", s: 58 },
  { x: 30, at: "bottom", s: 52 }, { x: 64, at: "bottom", s: 58 },
  { x: 0, at: "left", s: 62 }, { x: 0, at: "right", s: 58 },
];

function bumpStyle(b: (typeof BUMPS)[number], k: number): CSSProperties {
  const s = b.s * k;
  const across = `calc(${b.x}% - ${s / 2}px)`;
  const middle = `calc(50% - ${s / 2}px)`;
  const out = -s * 0.38; // how far a bump sticks out past the body
  const place = { top: { left: across, top: out }, bottom: { left: across, bottom: out },
    left: { top: middle, left: out }, right: { top: middle, right: out } }[b.at];
  return { position: "absolute", width: s, height: s, borderRadius: "50%", ...place };
}

/** The cloud outline: the body + bumps drawn as one shape. `paint` styles every piece of one layer. */
function CloudLayer({ k, paint, className = "" }: { k: number; paint: string; className?: string }) {
  // a fixed corner radius (not a full pill), so a cloud that grows to more lines keeps its text inside the curve
  return (
    <div aria-hidden="true" className={`absolute inset-0 ${className}`}>
      <div className={`absolute inset-0 rounded-[44px] ${paint}`} />
      {BUMPS.map((b, i) => <div key={i} style={bumpStyle(b, k)} className={paint} />)}
    </div>
  );
}

/** The line's text: the Korean being typed (a link for the GitHub / LinkedIn lines) and its English gloss. */
function Lines({ typed, big }: { typed: Typed; big: boolean }) {
  const { shown } = typed;
  const text = (
    <>
      {shown?.typed}
      <span className="caret text-blue" aria-hidden="true">|</span>
    </>
  );
  return (
    <>
      <p lang="ko" className={`relative m-0 font-display leading-[1.3] break-keep ${big ? "text-[22px]" : "text-lg"}`}>
        {shown?.line.href ? (
          <a href={shown.line.href} target="_blank" rel="noopener noreferrer"
            className="underline decoration-blue decoration-2 underline-offset-4 hover:text-blue">{text}</a>
        ) : text}
      </p>
      <p lang="en" className={`relative mb-0 font-medium text-neutral-600 ${big ? "mt-1 min-h-[18px] text-sm" : "mt-[3px] min-h-4 text-xs"}`}>
        {shown?.gloss}
      </p>
    </>
  );
}

/** Hovering or focusing the bubble pauses the typing (time to click a link). */
const pausing = (typed: Typed) => ({
  onMouseEnter: () => typed.pause(true),
  onMouseLeave: () => typed.pause(false),
  onFocus: () => typed.pause(true),
  onBlur: () => typed.pause(false),
});

/** `tail`: "right" = phone: a speech bubble pointing at Blueberry beside it; "down" = desktop: a cloud thought
 *  bubble above Blueberry. */
export default function TypedBubble({ typed, tail, className = "" }: { typed: Typed; tail: "right" | "down"; className?: string }) {
  if (tail === "down") return <CloudBubble typed={typed} className={className} />;
  return (
    <div {...pausing(typed)} className={`rounded-[18px] border-[2.5px] border-ink bg-white px-3 py-2.5 shadow-pop-sm ${className}`}
      data-testid="bubble">
      <Lines typed={typed} big={false} />
      <span aria-hidden="true" className="absolute right-[-9px] bottom-4 size-3.5 rotate-45 border-t-[2.5px] border-r-[2.5px] border-ink bg-white" />
    </div>
  );
}

function CloudBubble({ typed, className }: { typed: Typed; className: string }) {
  const dot = "absolute rounded-full border-[2.5px] border-ink bg-white shadow-pop-xs";
  return (
    <div {...pausing(typed)} className={`px-10 py-4 text-center ${className}`} data-testid="bubble">
      {/* drawn three times: the offset shadow, the outlined pieces, then each piece's inside painted white,
          which covers the outlines where pieces overlap, so only the cloud's outer edge stays outlined */}
      <div data-testid="cloud">
        <CloudLayer k={1} paint="bg-ink" className="translate-x-[3px] translate-y-[3px]" />
        <CloudLayer k={1} paint="border-[2.5px] border-ink bg-white" />
        <CloudLayer k={1} paint="border-[2.5px] border-transparent bg-white bg-clip-padding" />
      </div>
      {/* the little thought circles, trailing down toward Blueberry */}
      <div aria-hidden="true" data-testid="thought-dots">
        <span className={`${dot} bottom-[-36px] left-[calc(50%-10px)] size-5`} />
        <span className={`${dot} bottom-[-58px] left-[calc(50%+8px)] size-3`} />
      </div>
      <Lines typed={typed} big />
    </div>
  );
}
