"use client"; // runs in the browser: it reacts to clicks and fetches from the backend

import { useEffect, useState } from "react";
import BackendStatus from "@/components/BackendStatus";
import NativeAudio from "@/components/NativeAudio";
import Recorder from "@/components/Recorder";
import FormalityLine from "@/components/FormalityLine";
import Translation from "@/components/Translation";
import { fetchCustom, fetchPack, fetchPacks, type CustomText, type Lang, type Pack, type PackSummary } from "@/lib/api";
import { MAX_CUSTOM_CHARS, checkLine, typedProblem } from "@/lib/custom";
import { tagLabel } from "@/lib/tags";

// "type your own" sits next to the packs; this id can't clash with a pack file name.
const CUSTOM = "__custom__";

const DIRECTIONS: { lang: Lang; label: string }[] = [
  { lang: "ko", label: "I'm learning Korean" },
  { lang: "en", label: "I'm learning English" },
];

// Shared look for a choice button; `on` = currently selected.
const choice = (on: boolean) =>
  `rounded-lg border px-4 py-3 text-left transition-colors ${
    on
      ? "border-blue-600 bg-blue-50 dark:bg-blue-950"
      : "border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
  }`;

export default function Home() {
  // The user's choices, in order: direction -> pack -> sentence.
  const [lang, setLang] = useState<Lang | null>(null);
  const [packs, setPacks] = useState<PackSummary[] | null>(null);
  const [packId, setPackId] = useState<string | null>(null);
  const [pack, setPack] = useState<Pack | null>(null);
  const [itemId, setItemId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Custom mode: what the user typed, and the backend's spoken-words version of it (null = not checked yet).
  const [typed, setTyped] = useState("");
  const [custom, setCustom] = useState<CustomText | null>(null);
  const [customBusy, setCustomBusy] = useState(false);
  const [customError, setCustomError] = useState<string | null>(null);
  // Korean translations: 존댓말 by default; the small switch flips to 반말. One setting for the page.
  const [casual, setCasual] = useState(false);

  function resetCustom() {
    setTyped("");
    setCustom(null);
    setCustomError(null);
  }

  // Choosing an earlier step clears everything after it (in the click, so effects only fetch).
  function chooseLang(l: Lang) {
    setLang(l);
    setPacks(null);
    setPackId(null);
    setPack(null);
    setItemId(null);
    setError(null);
    resetCustom();
  }
  function choosePack(id: string) {
    setPackId(id);
    setPack(null);
    setItemId(null);
    setError(null);
    resetCustom();
  }

  // Editing the sentence drops the old check, so we never score text the user no longer sees.
  function editTyped(t: string) {
    setTyped(t);
    setCustom(null);
    setCustomError(null);
  }

  // "Check it": quick local checks, then the backend writes numbers / short forms out as spoken words.
  async function checkTyped() {
    if (!lang) return;
    const problem = typedProblem(typed);
    if (problem) return setCustomError(problem);
    setCustomBusy(true);
    setCustomError(null);
    try {
      setCustom(await fetchCustom(typed.trim(), lang));
    } catch (e) {
      setCustomError((e as Error).message);
    } finally {
      setCustomBusy(false);
    }
  }

  // When the direction changes: load the packs for that language.
  useEffect(() => {
    if (!lang) return;
    let ignore = false; // drop a late reply if the user already switched direction
    fetchPacks(lang).then(
      (list) => !ignore && setPacks(list),
      (e: Error) => !ignore && setError(e.message),
    );
    return () => {
      ignore = true;
    };
  }, [lang]);

  // When a pack is chosen: load its sentences.
  useEffect(() => {
    if (!packId || packId === CUSTOM) return; // Custom mode has no pack to load
    let ignore = false;
    fetchPack(packId).then(
      (p) => !ignore && setPack(p),
      (e: Error) => !ignore && setError(e.message),
    );
    return () => {
      ignore = true;
    };
  }, [packId]);

  const item = pack?.items.find((it) => it.id === itemId) ?? null;
  const isCustom = packId === CUSTOM;
  const line = custom ? checkLine(custom) : null;

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-4 py-12">
      <header>
        <h1 className="text-3xl font-semibold">Pronunciation coach</h1>
        <p className="mt-1 text-neutral-500">Record a sentence, see which sounds need work.</p>
      </header>

      {/* 1. Direction */}
      <section className="flex flex-col gap-3">
        <h2 className="font-medium">1. What are you learning?</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {DIRECTIONS.map((d) => (
            <button key={d.lang} onClick={() => chooseLang(d.lang)} className={choice(lang === d.lang)}>
              {d.label}
            </button>
          ))}
        </div>
      </section>

      {error && <p className="rounded-lg bg-red-50 p-3 text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>}

      {/* 2. Pack */}
      {lang && (
        <section className="flex flex-col gap-3">
          <h2 className="font-medium">2. Pick a sentence pack</h2>
          {!packs && !error && <p className="text-neutral-500">Loading packs…</p>}
          {packs?.length === 0 && <p className="text-neutral-500">No packs for this language yet.</p>}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {packs?.map((p) => (
              <button key={p.id} onClick={() => choosePack(p.id)} className={choice(packId === p.id)}>
                <span className="block">{p.name}</span>
                <span className="block text-sm text-neutral-500">{p.count} sentences</span>
                {p.dev_only && (
                  <span className="mt-1 inline-block rounded bg-amber-100 px-1.5 text-xs text-amber-900 dark:bg-amber-900 dark:text-amber-100">
                    dev only · not reviewed
                  </span>
                )}
              </button>
            ))}
            {packs && (
              <button onClick={() => choosePack(CUSTOM)} className={choice(isCustom)}>
                <span className="block">Custom</span>
                <span className="block text-sm text-neutral-500">Type your own sentence</span>
              </button>
            )}
          </div>
        </section>
      )}

      {/* 3. Custom mode: type a sentence */}
      {lang && isCustom && (
        <section className="flex flex-col gap-3">
          <h2 className="font-medium">3. Type a sentence</h2>
          <form
            className="flex flex-col gap-2 sm:flex-row"
            onSubmit={(e) => {
              e.preventDefault(); // stay on the page (a form would reload it)
              checkTyped();
            }}
          >
            <input
              value={typed}
              onChange={(e) => editTyped(e.target.value)}
              lang={lang}
              placeholder={lang === "ko" ? "예: 커피 2잔 주세요." : "e.g. I'd like 2 coffees, please."}
              className="flex-1 rounded-lg border border-neutral-300 bg-transparent px-3 py-2 dark:border-neutral-700"
            />
            <button
              type="submit"
              disabled={customBusy}
              className="rounded-md bg-blue-600 px-4 py-2 font-medium text-white disabled:opacity-50"
            >
              {customBusy ? "Checking…" : "Check it"}
            </button>
          </form>
          <p className={`text-sm ${typed.trim().length > MAX_CUSTOM_CHARS ? "text-red-600" : "text-neutral-500"}`}>
            {typed.trim().length}/{MAX_CUSTOM_CHARS} characters
          </p>
          {customError && (
            <p className="rounded-lg bg-red-50 p-3 text-red-700 dark:bg-red-950 dark:text-red-300">{customError}</p>
          )}
        </section>
      )}

      {/* 3. Sentence */}
      {packId && !isCustom && (
        <section className="flex flex-col gap-3">
          <h2 className="font-medium">3. Pick a sentence</h2>
          {!pack && !error && <p className="text-neutral-500">Loading sentences…</p>}
          {pack?.dev_only && (
            <p className="text-sm text-neutral-500">
              {pack.note} Source: {pack.source}. License: {pack.license}.
            </p>
          )}
          <ol className="flex flex-col gap-2">
            {pack?.items.map((it) => (
              <li key={it.id}>
                <button onClick={() => setItemId(it.id)} lang={pack.lang} className={`w-full ${choice(itemId === it.id)}`}>
                  {it.text}
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* 4. The chosen sentence + the recorder */}
      {item && pack && (
        <section className="flex flex-col gap-3 rounded-lg border border-neutral-300 p-5 dark:border-neutral-700">
          <p lang={pack.lang} className="text-2xl leading-relaxed">
            {item.text}
          </p>
          {item.translation ? (
            <FormalityLine t={item} textLang={pack.lang === "en" ? "ko" : "en"} casual={casual} onCasual={setCasual} />
          ) : (
            <p className="text-sm text-neutral-500">No translation yet (dev pack).</p>
          )}
          {item.tags.length > 0 && (
            <p className="flex flex-wrap gap-1.5 text-sm">
              <span className="text-neutral-500">Practices:</span>
              {item.tags.map((t) => (
                <span key={t} className="rounded bg-neutral-100 px-1.5 dark:bg-neutral-800">
                  {tagLabel(t)}
                </span>
              ))}
            </p>
          )}
          {/* Hear it first, then record */}
          <NativeAudio text={item.text} lang={pack.lang} />
          {/* key: a new sentence gets a fresh recorder (old result and any live recording are dropped) */}
          <Recorder key={item.id} text={item.text} lang={pack.lang} />
        </section>
      )}

      {/* 4. Custom mode: the sentence we'll actually score + the same hear / record flow as a pack sentence */}
      {lang && isCustom && line && (
        <section className="flex flex-col gap-3 rounded-lg border border-neutral-300 p-5 dark:border-neutral-700">
          <p className="text-sm text-neutral-500">We&apos;ll check:</p>
          <p lang={lang} className="text-2xl leading-relaxed">
            {line.text}
          </p>
          <Translation text={line.text} lang={lang} casual={casual} onCasual={setCasual} />
          {line.note && (
            <p className="text-sm text-neutral-500">
              {line.note} You typed: <span lang={lang}>{custom?.typed}</span>
            </p>
          )}
          <NativeAudio text={line.text} lang={lang} />
          {/* key: a new checked sentence gets a fresh recorder */}
          <Recorder key={`custom:${line.text}`} text={line.text} lang={lang} />
        </section>
      )}

      <footer className="mt-auto pt-8">
        <BackendStatus />
      </footer>
    </main>
  );
}
