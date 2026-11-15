"use client";
// The Autoplay switch in the type box. On by default: a new animation plays by itself.
// Off: it loads and waits on Play. On = pink track, knob right; off = white track, knob left.

import { useUi } from "@/components/UiLang";

export default function AutoplaySwitch({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  const { t } = useUi();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className="flex items-center gap-2 text-sm font-semibold lg:gap-2.5 lg:text-base"
      data-testid="autoplay"
    >
      {t("autoplay")}
      <span className={`relative inline-block h-6 w-[42px] rounded-full border-[2.5px] border-ink transition-colors lg:h-7 lg:w-12 ${on ? "bg-pink" : "bg-white"}`}>
        <span className={`absolute top-[2px] size-[15px] rounded-full bg-ink transition-all lg:top-[3px] lg:size-[17px] ${on ? "left-5 lg:left-[23px]" : "left-[2px] lg:left-[3px]"}`} />
      </span>
    </button>
  );
}
