"use client";
// One translation line + a small 존댓말 / 반말 switch. The switch only appears when there are
// two forms; its position is shared by the whole page, so it stays where the learner left it between sentences.
import { hasBothForms, pickTranslation, type Translated } from "@/lib/translations";

type Props = { t: Translated; textLang: string; casual: boolean; onCasual: (v: boolean) => void };

export default function FormalityLine({ t, textLang, casual, onCasual }: Props) {
  const shown = pickTranslation(t, casual);
  if (!shown) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm text-neutral-500">
      <span lang={textLang}>{shown.text}</span>
      {hasBothForms(t) && (
        <button
          type="button"
          role="switch"
          aria-checked={casual}
          aria-label="Show 반말 (casual) instead of 존댓말 (polite)"
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
      )}
    </div>
  );
}
