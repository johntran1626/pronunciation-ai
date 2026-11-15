"use client";
// The home mascot: Blueberry in round glasses at a typewriter, typing the bubble's lines.
// - The carriage (roller + paper) slides one notch left per keystroke, the way a real one does, and a line of ink
//   grows on the paper; when the line is done the lever clicks softly, the carriage slides back and the paper moves up a line.
// - Typing sounds (lib/typingSound.ts) are off until Blueberry is tapped, then stay on (typing in the box doesn't
//   stop them) until Blueberry is tapped again. The page holds the on/off, so the phone and desktop copies agree,
//   and Home / Animate another turn it back off. They play only after the visitor's first click / tap / key (a
//   browser rule), and only from the copy of Blueberry that is on screen (the page draws one for each width).

import { useEffect, useId, useRef } from "react";
import { useUi } from "@/components/UiLang";
import { useTypedLines } from "@/components/TypedBubble";
import { HOME_LINES, soundFor, type Typing } from "@/lib/home";
import { play, unlock } from "@/lib/typingSound";

const TRAVEL = 36; // how far the carriage moves over one line, in drawing units

// how long each finished line's ink is on the paper (a fixed width per line, so lines look different)
const inkWidth = (line: number) => 20 + ((line * 13) % 17);

export default function TypewriterBlueberry({ typed, soundOn, onSoundChange, width, className = "" }: {
  typed: ReturnType<typeof useTypedLines>;
  soundOn: boolean;
  onSoundChange: (on: boolean) => void;
  width: number;
  className?: string;
}) {
  const { ui, t } = useUi();
  const clip = useId();
  const root = useRef<HTMLButtonElement | null>(null);
  const last = useRef<Typing | null>(null);

  // sound needs one gesture first; any click, tap or key on the page counts
  useEffect(() => {
    const go = () => unlock();
    document.addEventListener("pointerdown", go, { once: true });
    document.addEventListener("keydown", go, { once: true });
    return () => {
      document.removeEventListener("pointerdown", go);
      document.removeEventListener("keydown", go);
    };
  }, []);

  // one sound per tick of the typing clock
  const state = typed.state;
  useEffect(() => {
    const prev = last.current;
    last.current = state;
    if (!prev || !state || !soundOn) return;
    if (!root.current?.getClientRects().length) return; // this copy is hidden at this screen width
    const sound = soundFor(prev, state, HOME_LINES, ui);
    if (sound) play(sound);
  }, [state, soundOn, ui]);

  function toggle() {
    unlock();
    onSoundChange(!soundOn);
  }

  const shown = typed.shown;
  const progress = shown?.progress ?? 0;
  const typing = !!shown && !shown.done && !shown.returning; // keys moving (not while the carriage slides back)
  // the carriage starts right and moves left as the line is typed; a new line slides it back (slowly, visibly)
  const offset = TRAVEL / 2 - TRAVEL * progress;
  const back = !!shown?.returning || progress === 0;
  const pos = state?.pos ?? 0;
  const lineAt = (k: number) => (state && pos - k >= 0 ? state.order[pos - k] : null); // this line, and the ones above
  const height = Math.round((width * 156) / 160);

  return (
    <button
      ref={root}
      type="button"
      onClick={toggle}
      aria-pressed={soundOn}
      aria-label={`${t("typewriterLabel")}. ${t(soundOn ? "typingSoundOn" : "typingSoundOff")}`}
      title={t(soundOn ? "typingSoundOn" : "typingSoundOff")}
      className={`block cursor-pointer rounded-2xl ${className}`}
      data-testid="typewriter"
    >
      <svg width={width} height={height} viewBox="0 -24 160 156" overflow="visible" aria-hidden="true">
        {/* Blueberry, behind the typewriter, bobbing gently */}
        <g className="bob-body">
          <g transform="translate(20 0)">
            <path d="M56 9 C54 0 64 -2 62 8" fill="none" stroke="#111111" strokeWidth="4" strokeLinecap="round" />
            <path d="M60 8 C92 8 112 30 112 60 C112 88 90 104 60 104 C30 104 8 88 8 60 C8 30 28 8 60 8 Z"
              fill="#DCE8FF" stroke="#111111" strokeWidth="4" />
            <g className="blink">
              <ellipse cx="42" cy="56" rx="4.5" ry="5.5" fill="#111111" />
              <ellipse cx="78" cy="56" rx="4.5" ry="5.5" fill="#111111" />
            </g>
            {/* round glasses */}
            <circle cx="42" cy="54" r="13" fill="#FFFFFF" fillOpacity="0.35" stroke="#111111" strokeWidth="4" />
            <circle cx="78" cy="54" r="13" fill="#FFFFFF" fillOpacity="0.35" stroke="#111111" strokeWidth="4" />
            <path d="M55 52 Q60 48 65 52" fill="none" stroke="#111111" strokeWidth="4" strokeLinecap="round" />
            <ellipse cx="24" cy="70" rx="7" ry="4.5" fill="#FF9CC2" />
            <ellipse cx="96" cy="70" rx="7" ry="4.5" fill="#FF9CC2" />
            <ellipse cx="60" cy="74" rx="5" ry="4" fill="#3A0F24" />
          </g>
        </g>

        {/* the carriage: paper, roller, knobs and return lever; slides with the typing */}
        <g data-testid="carriage" style={{
          transform: `translateX(${offset}px)`,
          transition: back ? "transform 0.42s cubic-bezier(.3,1.3,.5,1)" : "transform 0.06s linear", // the slide back fits in the RETURN_TICKS
        }}>
          <clipPath id={clip}><rect x="58" y="84" width="44" height="18" /></clipPath>
          <rect x="58" y="84" width="44" height="22" fill="#FFFFFF" stroke="#111111" strokeWidth="3" />
          <g clipPath={`url(#${clip})`} stroke="#555555" strokeWidth="2" strokeLinecap="round">
            {[2, 1].map((k) => {
              const line = lineAt(k);
              return line === null ? null : <path key={k} d={`M62 ${96 - 4 * k} h${inkWidth(line)}`} />;
            })}
            {lineAt(0) !== null && progress > 0 && <path d={`M62 96 h${inkWidth(lineAt(0)!) * progress}`} />}
          </g>
          <path d="M30 98 L19 88" stroke="#111111" strokeWidth="3.5" strokeLinecap="round" />
          <circle cx="19" cy="88" r="3.5" fill="#111111" />
          <rect x="34" y="98" width="92" height="11" rx="5.5" fill="#C9CEDA" stroke="#111111" strokeWidth="3.5" />
          <circle cx="30" cy="103.5" r="6" fill="#FF85B8" stroke="#111111" strokeWidth="3" />
          <circle cx="130" cy="103.5" r="6" fill="#FF85B8" stroke="#111111" strokeWidth="3" />
        </g>

        {/* the typewriter body and its keys */}
        <g className={typing ? "tap" : undefined}>
          <path d="M38 110 H122 L140 130 H20 Z" fill="#E7EAF2" stroke="#111111" strokeWidth="4" strokeLinejoin="round" />
          <g fill="#FFFFFF" stroke="#111111" strokeWidth="2">
            {[0, 1, 2, 3, 4, 5, 6].map((i) => <circle key={`a${i}`} cx={46 + i * 11.3} cy="117" r="3.2" />)}
            {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => <circle key={`b${i}`} cx={40.5 + i * 11.3} cy="124.5" r="3.2" />)}
          </g>
        </g>
        {typing && (
          <g className="keys" stroke="#111111" strokeWidth="2.5" strokeLinecap="round">
            <path d="M15 118 L8 113" /><path d="M14 126 L6 126" />
            <path d="M145 118 L152 113" /><path d="M146 126 L154 126" />
          </g>
        )}
      </svg>
    </button>
  );
}
