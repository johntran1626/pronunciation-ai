"use client";
// The small Autoplay switch in the type box. On by default: a new animation plays by itself.
// Off: it loads and waits on Play.

import { useUi } from "@/components/UiLang";

export default function AutoplaySwitch({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  const { t } = useUi();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className="flex items-center gap-1.5 text-xs text-neutral-500"
      data-testid="autoplay"
    >
      <span className={on ? "font-medium text-neutral-600 dark:text-neutral-200" : ""}>{t("autoplay")}</span>
      <span className={`relative inline-block h-4 w-7 rounded-full transition-colors ${on ? "bg-green-600" : "bg-neutral-300 dark:bg-neutral-600"}`}>
        <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${on ? "left-3.5" : "left-0.5"}`} />
      </span>
    </button>
  );
}
