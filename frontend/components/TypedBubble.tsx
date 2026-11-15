"use client";
// Blueberry's speech bubble on the home page. useTypedLines() runs the clock (one keystroke every TICK_MS, lines in
// a fresh shuffle each round); <TypedBubble> draws it. The page calls the hook once and hands the same state to the
// phone bubble and the desktop bubble, so both say the same thing.
//
// - Hover (or keyboard focus) pauses the typing, so a GitHub / LinkedIn line can be clicked before it moves on.
// - Visitors who ask for less motion get one finished line and no clock at all.
// - Before the page is live in the browser the bubble is empty (the shuffle is random, so the server can't draw it).

import { useEffect, useRef, useState } from "react";
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

/** A KakaoTalk-style chat bubble: flat yellow, rounded, no outline, with a small hooked tail pointing at Blueberry.
 *  `tail`: "right" = phone (Blueberry beside it); "down" = desktop (Blueberry under it). */
export default function TypedBubble({ typed, tail, className = "" }: { typed: Typed; tail: "right" | "down"; className?: string }) {
  const down = tail === "down";
  return (
    <div {...pausing(typed)} data-testid="bubble"
      className={`rounded-[18px] bg-kakao ${down ? "px-7 py-4 text-center lg:rounded-[22px]" : "px-3.5 py-2.5"} ${className}`}>
      <Lines typed={typed} big={down} />
      {down ? (
        <svg aria-hidden="true" width="16" height="12" viewBox="0 0 16 12" className="absolute top-[calc(100%-1px)] left-[calc(50%-4px)]">
          <path d="M0 0 H16 Q8 4 2 12 Q3 5 0 0 Z" fill="#FEE500" />
        </svg>
      ) : (
        <svg aria-hidden="true" width="12" height="16" viewBox="0 0 12 16" className="absolute top-2.5 right-[-11px]">
          <path d="M0 0 V16 Q4 8 12 2 Q5 3 0 0 Z" fill="#FEE500" />
        </svg>
      )}
    </div>
  );
}
