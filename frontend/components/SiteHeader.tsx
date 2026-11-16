"use client";
// The header on every page: GitHub / LinkedIn on the left; on the right, the Development tab, the Home button (a
// house icon) and the ENG / 한 switch, side by side on phone and desktop.
// On the home page Home resets the page (onHome); on the other pages it is a link back to it.

import Link from "next/link";
import { usePathname } from "next/navigation";
import SocialLinks from "@/components/SocialLinks";
import { UiToggle, useUi } from "@/components/UiLang";
import { TABS, activeTab } from "@/lib/tabs";

const pill = "rounded-xl border-[2.5px] border-ink font-display text-sm shadow-pop-xs lg:text-base";

export default function SiteHeader({ onHome }: { onHome?: () => void }) {
  const { t } = useUi();
  const active = activeTab(usePathname() ?? "/");
  const homeLook = `grid size-[34px] place-items-center bg-white text-ink hover:bg-sky lg:size-[38px] ${pill}`;
  return (
    <header className="mx-auto flex w-full max-w-[1160px] items-center justify-between gap-2">
      <SocialLinks />
      <div className="flex items-center gap-2 lg:gap-2.5">
        <nav aria-label={t("tabsLabel")} className="flex" data-testid="tabs">
          {TABS.map((tab) => (
            <Link key={tab.href} href={tab.href} aria-current={active === tab.href ? "page" : undefined}
              className={`px-2.5 py-1.5 lg:px-3.5 lg:py-[7px] ${pill} ${active === tab.href ? "bg-ink text-white" : "bg-white text-ink hover:bg-sky"}`}>
              {t(tab.label)}
            </Link>
          ))}
        </nav>
        {onHome ? (
          <button type="button" onClick={onHome} data-testid="home" aria-label={t("home")} title={t("home")} className={homeLook}>
            <HomeIcon />
          </button>
        ) : (
          <Link href="/" data-testid="home" aria-label={t("home")} title={t("home")} className={homeLook}><HomeIcon /></Link>
        )}
        <UiToggle />
      </div>
    </header>
  );
}

function HomeIcon() {
  return (
    <svg className="size-[18px] lg:size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 11 12 3l9 8" /><path d="M5 9.5V21h14V9.5" />
    </svg>
  );
}
