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
import InfoTip from "@/components/InfoTip";
import LoadingScreen from "@/components/LoadingScreen";
import SocialLinks from "@/components/SocialLinks";
import TypedBubble, { useTypedLines } from "@/components/TypedBubble";
import TypewriterBlueberry from "@/components/TypewriterBlueberry";
import { UiLangProvider, UiToggle, useUi } from "@/components/UiLang";
import { checkHealth, fetchCustom, loadCardData, type TextLang } from "@/lib/api";
import { MAX_CUSTOM_CHARS, checkLine } from "@/lib/custom";
import { problemText, type Key } from "@/lib/i18n";
import { detectLang, gradingLive, htmlLang, practiceOffered } from "@/lib/landing";
import { loadNativeClip } from "@/lib/native";
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
  const [busy, setBusy] = useState(false); // the loading screen is up
  const [ready, setReady] = useState<Omit<Shown, "run"> | null>(null); // the answer, once everything is in
  const [error, setError] = useState<string | null>(null);
  const [practice, setPractice] = useState(false);
  const [muted, setMuted] = useState(false); // the sound button on the animation; kept for the visit
  const [autoplay, setAutoplayState] = useState(AUTOPLAY_DEFAULT);
  const runs = useRef(0);
  const result = useRef<HTMLElement | null>(null);
  const typedLines = useTypedLines(); // Blueberry's bubble (the same lines on phone and desktop)

  const lang = detectLang(typed);
  const tooLong = typed.trim().length > MAX_CUSTOM_CHARS;
  // the typewriter's sounds: only while the visitor isn't typing and no animation is showing
  const typingSound = !typed && !shown && !busy;

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
    // the loading screen replaces the home (kept, hidden) until the sentence, its native clip + timings and the
    // articulation table are all in; the bar then reaches 100 and onFinished shows the animation
    setShown(null); // the old animation stops
    setReady(null);
    setBusy(true);
    setError(null);
    window.scrollTo({ top: 0 });
    try {
      // the backend writes numbers and short forms out the way they're said
      const checked = checkLine(await fetchCustom(typed.trim(), lang));
      // fetched now and kept (lib/native.ts, lib/api.ts), so the player starts at once
      await Promise.all([loadNativeClip(checked.text, lang), loadCardData()]);
      setReady({ text: checked.text, lang, note: checked.note, typed: typed.trim() });
    } catch (e) {
      setBusy(false);
      setError((e as Error).message);
    }
  }

  function loaded() {
    setBusy(false);
    if (ready) show(ready);
  }

  return (
    <main className="flex min-h-dvh w-full flex-col px-[22px] pt-5 pb-7 lg:px-10 lg:pt-7 lg:pb-12">
      <header className="mx-auto flex w-full max-w-[1160px] items-center justify-between">
        <SocialLinks />
        <UiToggle />
      </header>

      {busy && <LoadingScreen done={ready !== null} onFinished={loaded} />}

      {/* home: phone = one column (title, then Blueberry sitting on the box); desktop = two columns */}
      <div hidden={busy} className="mx-auto flex w-full max-w-[1160px] flex-1 flex-col justify-center lg:flex-row lg:flex-wrap lg:items-center lg:gap-16">
        <div className="flex min-w-0 flex-col items-center gap-[22px] lg:flex-[1_1_380px]">
          <h1 className="m-0 text-center font-display text-[30px] leading-[1.15] font-normal lg:text-[52px] lg:leading-[1.05]">
            {t("brand")}
            <span className="mt-1 block text-lg text-blue lg:mt-2 lg:text-[26px]">{t("byline")}</span>
          </h1>
          {/* desktop: the bubble above Blueberry at the typewriter, with a shadow on the ground */}
          <TypedBubble typed={typedLines} tail="down" className="relative mt-[18px] hidden w-full max-w-[400px] lg:block" />
          <div className="hidden flex-col items-center lg:flex">
            <TypewriterBlueberry typed={typedLines} typingSound={typingSound} width={240} />
            <span aria-hidden="true" className="ground -mt-1 block h-3 w-[200px] rounded-[50%] bg-ink" />
          </div>
        </div>

        {/* the box: usable the moment the page opens */}
        <form
          className="flex min-w-0 flex-col gap-[22px] lg:flex-[1.35_1_480px] lg:gap-6"
          onSubmit={(e) => {
            e.preventDefault(); // stay on the page
            void submit();
          }}
        >
          <div className="relative mt-[150px] lg:mt-0">
            {/* phone: the bubble to the left, Blueberry's typewriter standing on the box's top-right corner */}
            <TypedBubble typed={typedLines} tail="right" className="absolute right-[136px] bottom-[calc(100%+34px)] left-0 lg:hidden" />
            <div className="absolute right-0 bottom-[calc(100%-3px)] lg:hidden">
              <TypewriterBlueberry typed={typedLines} typingSound={typingSound} width={128} />
            </div>
            {/* no overflow-hidden here, so the Autoplay note can pop out of the box; the parts round their own corners */}
            <div className="relative rounded-[20px] border-[2.5px] border-ink bg-white shadow-pop lg:rounded-3xl lg:shadow-pop-lg">
              <div className="wongoji rounded-t-[17.5px] px-4 pt-4 pb-2.5 lg:rounded-t-[21.5px] lg:px-[22px] lg:pt-5 lg:pb-3">
                <span className="inline-block bg-white px-1 text-[13px] font-medium text-neutral-700 lg:text-[15px]" data-testid="detected">
                  {t(lang ? LANG_NAME[lang] : "langEither")}
                </span>
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
                  className="mt-1.5 block h-[102px] w-full resize-none bg-transparent p-0 text-2xl leading-[34px] font-medium break-keep text-ink outline-none placeholder:text-[#767676] lg:mt-2 lg:h-[200px] lg:text-[30px] lg:leading-[40px]"
                  data-testid="box"
                />
              </div>
              <div className="flex items-center gap-2.5 rounded-b-[17.5px] border-t-[2.5px] border-ink bg-tray px-3.5 py-2.5 lg:gap-3 lg:rounded-b-[21.5px] lg:px-[18px] lg:py-3">
                <span className={`text-xs font-medium lg:text-sm ${tooLong ? "text-red-600" : "text-neutral-700"}`}>
                  {typed.trim().length}/{MAX_CUSTOM_CHARS}
                </span>
                <div className="ml-auto flex items-center gap-2">
                  <AutoplaySwitch on={autoplay} onChange={setAutoplay} />
                  <InfoTip text={t("autoplayInfo")} label={t("infoAbout", { name: t("autoplay") })} />
                </div>
              </div>
            </div>
          </div>
          <button
            type="submit"
            disabled={busy}
            className="flex h-[62px] items-center justify-center gap-2.5 rounded-[18px] border-[2.5px] border-ink bg-blue font-display text-[26px] text-white shadow-pop transition-[transform,box-shadow] hover:-translate-y-px active:translate-x-[3px] active:translate-y-[3px] active:shadow-pop-xs disabled:opacity-60 lg:h-[74px] lg:gap-3 lg:rounded-[20px] lg:text-[32px] lg:shadow-pop-lg"
            data-testid="go"
          >
            {busy ? t("loading") : t("animate")}
            {!busy && (
              <svg className="size-[22px] lg:size-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
                strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M5 12h14" /><path d="m13 6 6 6-6 6" />
              </svg>
            )}
          </button>
          {error && <p className="m-0 rounded-2xl border-[2.5px] border-ink bg-[#FFE4EF] px-4 py-3 font-medium text-ink shadow-pop-xs" role="alert">{error}</p>}
        </form>
      </div>

      <div className="mx-auto flex w-full max-w-3xl min-w-0 flex-col gap-6">
        {/* the sentence, its animation, and practice */}
        {shown && (
          <section ref={result} className="mt-10 flex scroll-mt-4 flex-col gap-3" data-testid="result">
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
