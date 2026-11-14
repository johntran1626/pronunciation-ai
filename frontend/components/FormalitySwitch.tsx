"use client";
// The small 존댓말 / 반말 switch. One page-wide setting: it flips a Korean translation (English packs, Custom
// mode) and filters a Korean pack's lines. 존댓말 (polite) is the default.

type Props = { casual: boolean; onCasual: (v: boolean) => void; label?: string };

export default function FormalitySwitch({ casual, onCasual, label = "Show 반말 (casual) instead of 존댓말 (polite)" }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={casual}
      aria-label={label}
      onClick={() => onCasual(!casual)}
      className="flex items-center gap-1.5 text-xs text-neutral-400"
    >
      <span className={casual ? "" : "font-medium text-neutral-600 dark:text-neutral-200"}>존댓말</span>
      <span
        className={`relative inline-block h-4 w-7 rounded-full transition-colors ${
          casual ? "bg-blue-600" : "bg-neutral-300 dark:bg-neutral-600"
        }`}
      >
        <span
          className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${casual ? "left-3.5" : "left-0.5"}`}
        />
      </span>
      <span className={casual ? "font-medium text-neutral-600 dark:text-neutral-200" : ""}>반말</span>
    </button>
  );
}
