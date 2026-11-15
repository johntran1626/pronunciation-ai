"use client";
// The site language (ENG / 한), shared by every component through context. English by default; the choice is
// remembered in this browser only (a convenience: if storage is blocked the site simply opens in English).
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { DEFAULT_UI, tr, type Key, type Ui } from "@/lib/i18n";

const KEY = "ui-lang";
const Ctx = createContext<{ ui: Ui; setUi: (u: Ui) => void }>({ ui: DEFAULT_UI, setUi: () => {} });

export function UiLangProvider({ children }: { children: ReactNode }) {
  const [ui, setUiState] = useState<Ui>(DEFAULT_UI);
  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved === "ko" || saved === "en") setUiState(saved); // eslint-disable-line react-hooks/set-state-in-effect -- read once after mount (no storage during server render)
    } catch {}
  }, []);
  useEffect(() => {
    document.documentElement.lang = ui; // so the browser picks Korean fonts and screen readers the right voice
  }, [ui]);
  const setUi = (u: Ui) => {
    setUiState(u);
    try { localStorage.setItem(KEY, u); } catch {}
  };
  return <Ctx.Provider value={{ ui, setUi }}>{children}</Ctx.Provider>;
}

/** The site language, plus `t(key, vars)` for a site string in it. */
export function useUi() {
  const { ui, setUi } = useContext(Ctx);
  return { ui, setUi, t: (key: Key, vars?: Record<string, string | number>) => tr(ui, key, vars) };
}

/** The ENG / 한 switch for the top corner. */
export function UiToggle() {
  const { ui, setUi, t } = useUi();
  return (
    <div role="group" aria-label={t("switchLabel")} className="flex overflow-hidden rounded-xl border-[2.5px] border-ink shadow-pop-xs" data-testid="ui-toggle">
      {(["en", "ko"] as Ui[]).map((u) => (
        <button key={u} type="button" aria-pressed={ui === u} onClick={() => setUi(u)}
          className={`px-2.5 py-1.5 font-display text-sm lg:px-3.5 lg:py-[7px] lg:text-base ${ui === u ? "bg-ink text-white" : "bg-white text-ink hover:bg-sky"}`}>
          {u === "en" ? "ENG" : "한"}
        </button>
      ))}
    </div>
  );
}
