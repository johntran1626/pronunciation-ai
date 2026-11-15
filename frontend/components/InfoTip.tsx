"use client";
// A small (i) beside a switch. Hover, keyboard focus or a tap shows a short note on what the switch does
// (phones can't hover, so a tap opens it and a tap anywhere else closes it). Escape closes it too.
// `opens`: which way the note reaches from the (i): "left" (default) or "right" (for an (i) near the left edge).

import { useId, useState } from "react";

export default function InfoTip({ text, label, opens = "left" }: { text: string; label: string; opens?: "left" | "right" }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="relative inline-flex" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        aria-label={label}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onClick={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}
        className="grid size-5 place-items-center rounded-full border-2 border-ink bg-white font-display text-xs leading-none text-ink hover:bg-sky lg:size-[22px] lg:text-sm"
        data-testid="info"
      >
        i
      </button>
      {open && (
        <span role="tooltip" id={id}
          className={`absolute ${opens === "left" ? "right-[-6px]" : "left-[-6px]"} bottom-[calc(100%+10px)] z-30 w-60 rounded-xl border-[2.5px] border-ink bg-white px-3 py-2 text-left text-[13px] leading-snug font-medium text-ink shadow-pop-sm`}>
          {text}
        </span>
      )}
    </span>
  );
}
