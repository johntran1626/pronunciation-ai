"use client"; // runs in the browser: it reacts to typing and clicks and fetches from the backend

// Type-first: one big box. The language comes from what is typed (Hangul = Korean, both = mixed), the native mouth
// animation loads and plays for the sentence with no extra tap, and "Practice it yourself" opens the recorder +
// scoring (one-language sentences only).
// One button, Animate, for English, Korean and mixed text alike.
// The Autoplay switch in the box (on by default) decides whether a new animation plays by itself.

import { useEffect, useRef, useState } from "react";
import AutoplaySwitch from "@/components/AutoplaySwitch";
import NativeMouth from "@/components/NativeMouth";
import Recorder from "@/components/Recorder";
import Translation from "@/components/Translation";
import { UiLangProvider, UiToggle, useUi } from "@/components/UiLang";
import { checkHealth, fetchCustom, type TextLang } from "@/lib/api";
import { MAX_CUSTOM_CHARS, checkLine } from "@/lib/custom";
import { problemText, type Key } from "@/lib/i18n";
import { detectLang, gradingLive, htmlLang, practiceOffered } from "@/lib/landing";
import { AUTOPLAY_DEFAULT, playerKey, readAutoplay, saveAutoplay } from "@/lib/player";

const LANG_NAME: Record<TextLang, Key> = { en: "langEn", ko: "langKo", mix: "langMix" };

// The sentence being animated. `run` counts animations, so showing the same sentence again still gets a fresh
// player (1x, plays again).
type Shown = { run: number; text: string; lang: TextLang; note: string | null; typed: string };

export default function Home() {
  return (
    <UiLangProvider>
      <Coach />
    </UiLangProvider>
  );
}

function Coach() {
  const { ui, t } = useUi();
  const [typed, setTyped] = useState("");
  const [shown, setShown] = useState<Shown | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [practice, setPractice] = useState(false);
  const [muted, setMuted] = useState(false); // the sound button on the animation; kept for the visit
  const [autoplay, setAutoplayState] = useState(AUTOPLAY_DEFAULT);
  const runs = useRef(0);
  const result = useRef<HTMLElement | null>(null);

  const lang = detectLang(typed);
  const tooLong = typed.trim().length > MAX_CUSTOM_CHARS;

  // wake the backend as the page opens (a sleeping server starts while the visitor types); nothing is shown
  useEffect(() => { checkHealth().catch(() => {}); }, []);

  // the saved Autoplay choice, read once after mount (no storage during server render)
  useEffect(() => {
    let store: Storage | null = null;
    try { store = localStorage; } catch {}
    setAutoplayState(readAutoplay(store)); // eslint-disable-line react-hooks/set-state-in-effect -- read once after mount
  }, []);
  function setAutoplay(on: boolean) {
    setAutoplayState(on);
    try { saveAutoplay(localStorage, on); } catch {}
  }

  function show(s: Omit<Shown, "run">) {
    setShown({ ...s, run: ++runs.current });
    setPractice(false);
    setError(null);
    // bring the animation into view on small screens (the box stays above it)
    requestAnimationFrame(() => result.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
  }

  async function submit() {
    const problem = problemText(ui, typed);
    if (problem) return setError(problem);
    if (!lang) return setError(t("errNoLang"));
    setBusy(true);
    setError(null);
    try {
      // the backend writes numbers and short forms out the way they're said
      const checked = checkLine(await fetchCustom(typed.trim(), lang));
      show({ text: checked.text, lang, note: checked.note, typed: typed.trim() });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 py-8 sm:py-12">
      <header className="flex items-center justify-between">
        <span className="text-sm font-semibold tracking-wide text-neutral-500">{t("brand")}</span>
        <UiToggle />
      </header>

      <div className="flex min-w-0 flex-col gap-6">
        {/* the box: usable the moment the page opens */}
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault(); // stay on the page
            void submit();
          }}
        >
          <div className="rounded-2xl border-2 border-neutral-300 bg-white shadow-sm transition focus-within:border-green-600 focus-within:shadow-[0_0_0_6px_rgba(22,163,74,0.15)] dark:border-neutral-700 dark:bg-neutral-900">
            <textarea
              autoFocus
              rows={3}
              value={typed}
              onChange={(e) => { setTyped(e.target.value); setError(null); }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { // isComposing: Korean IME
                  e.preventDefault();
                  void submit();
                }
              }}
              lang={htmlLang(lang)}
              aria-label={t("boxLabel")}
              placeholder={t("placeholder")}
              className="block w-full resize-none bg-transparent break-keep px-5 pt-5 pb-2 text-2xl leading-snug outline-none placeholder:text-neutral-400 placeholder:uppercase placeholder:tracking-wide sm:text-3xl max-sm:text-xl"
              data-testid="box"
            />
            <div className="flex flex-wrap items-center gap-3 px-5 pb-4">
              <span className="text-sm text-neutral-500" data-testid="detected">
                {t(lang ? LANG_NAME[lang] : "langEither")}
              </span>
              <span className={`text-xs ${tooLong ? "text-red-600" : "text-neutral-400"}`}>
                {typed.trim().length}/{MAX_CUSTOM_CHARS}
              </span>
              <AutoplaySwitch on={autoplay} onChange={setAutoplay} />
              <div className="ml-auto">
                <button
                  type="submit"
                  disabled={busy || !typed.trim()}
                  className="rounded-full bg-green-700 px-5 py-2 font-medium text-white transition hover:bg-green-800 disabled:opacity-40"
                  data-testid="go"
                >
                  {busy ? t("loading") : t("animate")}
                </button>
              </div>
            </div>
          </div>
          {error && <p className="rounded-lg bg-red-50 p-3 text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>}
        </form>

        {/* the sentence, its animation, and practice */}
        {shown && (
          <section ref={result} className="flex scroll-mt-4 flex-col gap-3" data-testid="result">
            <p lang={htmlLang(shown.lang)} className="text-2xl leading-relaxed">{shown.text}</p>
            {shown.note && (
              <p className="text-sm text-neutral-500">
                {t("numbersNote")} {t("youTyped")} <span lang={htmlLang(shown.lang)}>{shown.typed}</span>
              </p>
            )}
            {/* a Korean sentence: its English meaning */}
            {shown.lang === "ko" && <Translation text={shown.text} />}
            {/* key: every new animation gets a fresh player (1x; it loads, and plays on its own if Autoplay is on) */}
            <NativeMouth key={playerKey(shown)} text={shown.text} lang={shown.lang} autoplay={autoplay} muted={muted} onMuted={setMuted} />
            {!practiceOffered(shown.lang) ? (
              <p className="text-sm text-neutral-500" data-testid="practice-mixed">{t("practiceMixed")}</p>
            ) : practice ? (
              <Recorder key={`rec:${shown.lang}:${shown.text}`} text={shown.text} lang={shown.lang} />
            ) : (
              <div>
                <button onClick={() => setPractice(true)} data-testid="practice"
                  className="rounded-full border-2 border-blue-600 px-5 py-2 font-medium text-blue-700 hover:bg-blue-50 dark:text-blue-300 dark:hover:bg-blue-950">
                  {t("practice")}
                </button>
                <p className="mt-1 text-xs text-neutral-500">{t(gradingLive(shown.lang) ? "practiceHint" : "practiceHintUngraded")}</p>
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
