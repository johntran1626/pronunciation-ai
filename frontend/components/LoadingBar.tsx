"use client";
// The loading bar: 10 outlined blocks, all blue, each filling by its own tenth, with the % beside it.
// The numbers come from lib/loading.ts (fakePct / finishPct); this only draws them.

import { useUi } from "@/components/UiLang";
import { barFills } from "@/lib/loading";

export default function LoadingBar({ pct }: { pct: number }) {
  const { t } = useUi();
  const whole = Math.floor(pct);
  return (
    <div className="flex w-full items-center gap-2.5 lg:gap-3.5">
      <div role="progressbar" aria-label={t("loadingLabel")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={whole}
        className="grid flex-1 grid-cols-10 gap-[3px] lg:gap-[5px]" data-testid="loading-bar">
        {barFills(pct).map((f, i) => (
          <span key={i} className="relative h-4 overflow-hidden rounded-md border-[2.5px] border-ink bg-white lg:h-[22px] lg:rounded-[7px]">
            <span className="absolute inset-y-0 left-0 bg-blue" style={{ width: `${f * 100}%` }} />
          </span>
        ))}
      </div>
      <span aria-hidden="true" className="w-[46px] flex-none text-right font-display text-xl text-blue lg:w-[60px] lg:text-[26px]" data-testid="loading-pct">
        {whole}%
      </span>
    </div>
  );
}
