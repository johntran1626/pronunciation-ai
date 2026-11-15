"use client"; // runs in the browser: it reacts to typing and clicks and fetches from the backend

// Type-first: one big box. The language comes from what is typed (Hangul = Korean), the native mouth animation
// loads and plays for the sentence with no extra tap, and "Practice it yourself" opens the recorder + scoring.
// Sample sentences (Basics and Casual, both languages) sit in a small dropdown to the side for visitors with
// nothing to type. The Autoplay switch in the box (on by default) decides whether a new animation plays by itself.

import { useEffect, useRef, useState } from "react";
import AutoplaySwitch from "@/components/AutoplaySwitch";
import BackendStatus from "@/components/BackendStatus";
import FormalityLine from "@/components/FormalityLine";
import NativeMouth from "@/components/NativeMouth";
import Recorder from "@/components/Recorder";
import Translation from "@/components/Translation";
import { UiLangProvider, UiToggle, useUi } from "@/components/UiLang";
import { fetchCustom, fetchPack, fetchTranslation, type Lang, type Pack, type PackItem } from "@/lib/api";
import { MAX_CUSTOM_CHARS, checkLine } from "@/lib/custom";
import { problemText, type Key } from "@/lib/i18n";
import { SAMPLE_PACKS, detectLang, findSample, koreanToAnimate, sampleGroups, storedTranslation, translateOffered } from "@/lib/landing";
import { AUTOPLAY_DEFAULT, playerKey, readAutoplay, saveAutoplay } from "@/lib/player";
import type { Translated } from "@/lib/translations";

const LANG_NAME: Record<Lang, Key> = { en: "langEn", ko: "langKo" };

// The sentence being animated: a sample (with its pack line: translation, source), what was typed, or the Korean
// translation of typed English (`from`: the English and both Korean forms, so the 존댓말 / 반말 switch can re-animate).
type FromEnglish = { en: string; t: Translated };
// `run` counts animations, so showing the same sentence again still gets a fresh player (1x, plays again).
type Shown = { run: number; text: string; lang: Lang; item: PackItem | null; note: string | null; typed: string | null; from?: FromEnglish };
type Busy = null | "animate" | "kr" | "kr-animate";

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
  const [busy, setBusy] = useState<Busy>(null);
  const [kr, setKr] = useState<FromEnglish | null>(null); // "Translate to KR" without animating
  const [picked, setPicked] = useState<PackItem | null>(null); // the last sample tapped (English ones carry Korean)
  const [error, setError] = useState<string | null>(null);
  const [practice, setPractice] = useState(false);
  const [casual, setCasual] = useState(false); // 존댓말 by default; one setting for the page
  const [samples, setSamples] = useState<Pack[]>([]);
  const [sampleLang, setSampleLang] = useState<Lang>("en");
  const [autoplay, setAutoplayState] = useState(AUTOPLAY_DEFAULT);
  const runs = useRef(0);
  const result = useRef<HTMLElement | null>(null);

  const lang = detectLang(typed);
  const tooLong = typed.trim().length > MAX_CUSTOM_CHARS;

  // the four sample packs, once
  useEffect(() => {
    let live = true;
    Promise.all([...SAMPLE_PACKS.en, ...SAMPLE_PACKS.ko].map(fetchPack)).then(
      (packs) => live && setSamples(packs),
      () => {}, // samples are optional; typing still works without them
    );
    return () => { live = false; };
  }, []);

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
    setBusy("animate");
    setError(null);
    try {
      // the backend writes numbers and short forms out the way they're said
      const checked = checkLine(await fetchCustom(typed.trim(), lang));
      show({ text: checked.text, lang, item: null, note: checked.note, typed: typed.trim() });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  // English -> Korean: a sample's stored Korean, else the backend's translation (both forms)
  async function toKorean(en: string): Promise<Translated | null> {
    return storedTranslation(picked, en) ?? (await fetchTranslation(en, "en"));
  }

  // animate one Korean form of an English sentence (numbers in the Korean are written out first, as for typing)
  async function animateKorean(from: FromEnglish, c: boolean) {
    const ko = koreanToAnimate(from.t, c);
    if (!ko) return;
    const checked = checkLine(await fetchCustom(ko, "ko"));
    show({ text: checked.text, lang: "ko", item: null, note: null, typed: null, from });
  }

  async function translate(animate: boolean) {
    const problem = problemText(ui, typed);
    if (problem) return setError(problem);
    const en = typed.trim();
    setBusy(animate ? "kr-animate" : "kr");
    setError(null);
    try {
      const found = await toKorean(en);
      if (!found) return setError(t("errTranslate"));
      if (animate) {
        setKr(null);
        await animateKorean({ en, t: found }, casual);
      } else setKr({ en, t: found });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  // the 존댓말 / 반말 switch: one setting for the page; on an animated translation it animates the other form
  function flipCasual(c: boolean) {
    setCasual(c);
    if (shown?.from) void animateKorean(shown.from, c).catch((e: Error) => setError(e.message));
  }

  function pickSample(it: PackItem, l: Lang) {
    setTyped(it.text);
    setPicked(it);
    setKr(null);
    show({ text: it.text, lang: l, item: it, note: null, typed: null });
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-4 py-8 sm:py-12">
      <header className="flex items-center justify-between">
        <span className="text-sm font-semibold tracking-wide text-neutral-500">{t("brand")}</span>
        <UiToggle />
      </header>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_16rem]">
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
                onChange={(e) => { setTyped(e.target.value); setError(null); setKr(null); }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { // isComposing: Korean IME
                    e.preventDefault();
                    void submit();
                  }
                }}
                lang={lang ?? undefined}
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
                <div className="ml-auto flex flex-wrap justify-end gap-2">
                  {translateOffered(lang) && (
                    <>
                      <button type="button" onClick={() => void translate(false)} disabled={!!busy} data-testid="kr"
                        className="rounded-full border border-neutral-300 px-4 py-2 text-sm hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:hover:bg-neutral-800">
                        {busy === "kr" ? t("translating") : t("translateKr")}
                      </button>
                      <button type="button" onClick={() => void translate(true)} disabled={!!busy} data-testid="kr-animate"
                        className="rounded-full border border-green-700 px-4 py-2 text-sm text-green-800 hover:bg-green-50 disabled:opacity-40 dark:text-green-300 dark:hover:bg-green-950">
                        {busy === "kr-animate" ? t("translating") : t("translateKrAnimate")}
                      </button>
                    </>
                  )}
                  <button
                    type="submit"
                    disabled={!!busy || !typed.trim()}
                    className="rounded-full bg-green-700 px-5 py-2 font-medium text-white transition hover:bg-green-800 disabled:opacity-40"
                    data-testid="go"
                  >
                    {busy === "animate" ? t("loading") : t("animate")}
                  </button>
                </div>
              </div>
            </div>
            {/* "Translate to KR": the Korean, and only now the 존댓말 / 반말 switch */}
            {kr && kr.en === typed.trim() && (
              <div className="rounded-xl bg-neutral-50 px-5 py-3 dark:bg-neutral-900" data-testid="kr-result">
                <FormalityLine t={kr.t} textLang="ko" casual={casual} onCasual={setCasual} big />
              </div>
            )}
            {error && <p className="rounded-lg bg-red-50 p-3 text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>}
          </form>

          {/* the sentence, its animation, and practice */}
          {shown && (
            <section ref={result} className="flex scroll-mt-4 flex-col gap-3" data-testid="result">
              <p lang={shown.lang} className="text-2xl leading-relaxed">{shown.text}</p>
              {shown.from && (
                <div className="flex flex-col gap-1" data-testid="from-english">
                  <p className="text-sm text-neutral-500">{t("koreanFor", { en: "" })}<span lang="en">{shown.from.en}</span></p>
                  <FormalityLine t={shown.from.t} textLang="ko" casual={casual} onCasual={flipCasual} switchOnly />
                </div>
              )}
              {shown.note && (
                <p className="text-sm text-neutral-500">
                  {t("numbersNote")} {t("youTyped")} <span lang={shown.lang}>{shown.typed}</span>
                </p>
              )}
              {/* a Korean sentence: its English meaning (a translation of typed English already shows it above) */}
              {shown.lang === "ko" && !shown.from &&
                (shown.item ? (
                  <FormalityLine t={shown.item} textLang="en" casual={casual} onCasual={setCasual} />
                ) : (
                  <Translation text={shown.text} lang="ko" casual={casual} onCasual={setCasual} />
                ))}
              {shown.item?.credit && (
                <p className="text-xs text-neutral-500">
                  {t("source")}{" "}
                  <a href={shown.item.source_url} target="_blank" rel="noreferrer" className="underline">
                    {shown.item.credit}
                  </a>
                  , {shown.item.license}.
                </p>
              )}
              {/* key: every new animation gets a fresh player (1x; it loads, and plays on its own if Autoplay is on) */}
              <NativeMouth key={playerKey(shown)} text={shown.text} lang={shown.lang} autoplay={autoplay} />
              {practice ? (
                <Recorder key={`rec:${shown.lang}:${shown.text}`} text={shown.text} lang={shown.lang} />
              ) : (
                <div>
                  <button onClick={() => setPractice(true)} data-testid="practice"
                    className="rounded-full border-2 border-blue-600 px-5 py-2 font-medium text-blue-700 hover:bg-blue-50 dark:text-blue-300 dark:hover:bg-blue-950">
                    {t("practice")}
                  </button>
                  <p className="mt-1 text-xs text-neutral-500">{t("practiceHint")}</p>
                </div>
              )}
            </section>
          )}
        </div>

        {/* samples: a small dropdown to the side (below the box on phones) */}
        <aside className="flex flex-col gap-2 text-sm lg:pt-2" data-testid="samples">
          <span className="text-neutral-500">{t("samplesTitle")}</span>
          <div className="flex gap-1" role="tablist">
            {(["en", "ko"] as Lang[]).map((l) => (
              <button key={l} role="tab" aria-selected={sampleLang === l} onClick={() => setSampleLang(l)}
                className={`rounded-full px-3 py-0.5 text-xs ${sampleLang === l ? "bg-neutral-800 text-white dark:bg-neutral-200 dark:text-neutral-900" : "text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"}`}>
                {t(l === "en" ? "tabEn" : "tabKo")}
              </button>
            ))}
          </div>
          <select
            value={shown?.item && shown.lang === sampleLang ? shown.item.id : ""}
            onChange={(e) => { const f = findSample(samples, e.target.value); if (f) pickSample(f.item, f.lang); }}
            lang={sampleLang}
            aria-label={t("samplesTitle")}
            className="w-full rounded-lg border border-neutral-300 bg-white px-2 py-1.5 text-neutral-700 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200"
            data-testid="sample-pick"
          >
            <option value="" disabled>{t("samplePick")}</option>
            {sampleGroups(samples, sampleLang).map((g) => (
              <optgroup key={g.id} label={g.name === "Basics" || g.name === "Casual" ? t(`pack_${g.name}`) : g.name}>
                {g.items.map((it) => <option key={it.id} value={it.id}>{it.text}</option>)}
              </optgroup>
            ))}
          </select>
        </aside>
      </div>

      <footer className="mt-auto pt-8">
        <BackendStatus />
      </footer>
    </main>
  );
}
