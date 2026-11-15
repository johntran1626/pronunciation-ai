"use client";
// Blueberry, the mascot: a limbless blue blob with a stem, blinking eyes, pink cheeks and a talking mouth.
// The loops (bob, blink, talk) are CSS classes in app/globals.css and stop when the visitor asks for less motion.

import { useUi } from "@/components/UiLang";

export default function Blueberry({ width, talking = true, className = "" }: {
  width: number;
  talking?: boolean;
  className?: string;
}) {
  const { t } = useUi();
  const height = Math.round((width * 104) / 112);
  return (
    <svg width={width} height={height} viewBox="0 -6 120 116" role="img" aria-label={t("mascotLabel")}
      className={className} data-testid="blueberry">
      <path d="M56 9 C54 0 64 -2 62 8" fill="none" stroke="#111111" strokeWidth="4" strokeLinecap="round" />
      <path d="M60 8 C92 8 112 30 112 60 C112 88 90 104 60 104 C30 104 8 88 8 60 C8 30 28 8 60 8 Z"
        fill="#DCE8FF" stroke="#111111" strokeWidth="4" />
      <g className="blink">
        <ellipse cx="42" cy="50" rx="5" ry="7" fill="#111111" />
        <ellipse cx="78" cy="50" rx="5" ry="7" fill="#111111" />
      </g>
      <ellipse cx="30" cy="66" rx="8" ry="5" fill="#FF9CC2" />
      <ellipse cx="90" cy="66" rx="8" ry="5" fill="#FF9CC2" />
      <g className={talking ? "talk" : undefined}>
        <path d="M48 68 Q60 92 72 68 Z" fill="#3A0F24" stroke="#111111" strokeWidth="3.5" strokeLinejoin="round" />
      </g>
    </svg>
  );
}
