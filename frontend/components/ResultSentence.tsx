"use client"; // Tapping a word plays it. Tapping a RED word opens its detail card instead

import { useEffect, useState } from "react";
import DetailCard from "@/components/DetailCard";
import { useUi } from "@/components/UiLang";
import { describeChecksIn } from "@/lib/i18n";
import { loadCardData, type AnalyzeResult, type ArticulationTable, type DisplayPiece, type TipsTable, type WordResult } from "@/lib/api";
import { buildCard, issuesOf, tapAction } from "@/lib/card";
import { loadNativeClip, nativePart, type NativeClip } from "@/lib/native";
import { playSlice, stopPlayback } from "@/lib/replay";
import { jamoParts, summarize } from "@/lib/results";

// Red = color AND a wavy underline, so it still reads for color-blind users.
const RED = "text-red-600 underline decoration-wavy decoration-2 underline-offset-4 dark:text-red-400";
const GREEN = "text-green-700 dark:text-green-400";
const STYLE = { red: RED, green: GREEN, unchecked: "" }; // unchecked = plain text: no live check looked at it
const TAP =
  "cursor-pointer rounded px-0.5 hover:bg-neutral-100 focus-visible:outline-2 focus-visible:outline-blue-600 dark:hover:bg-neutral-800";
const PLAYING = "bg-blue-100 dark:bg-blue-900";


type Audio = { samples: Float32Array<ArrayBuffer>; rate: number }; // the learner's own recording (louder copy)

function Piece({ piece }: { piece: DisplayPiece }) {
  const parts = jamoParts(piece);
  if (!parts) return <span className={STYLE[piece.status]}>{piece.text}</span>;
  // A red Korean block: the block itself, with its letters written small above it and the wrong one(s) in red.
  return (
    <ruby className={RED}>
      {piece.text}
      <rt className="text-[0.5em] tracking-wider no-underline">
        {parts.map((p, i) => (
          <span key={i} className={p.red ? "font-bold text-red-600 dark:text-red-400" : "text-neutral-400"}>
            {p.jamo}
          </span>
        ))}
      </rt>
    </ruby>
  );
}

// The sentence, painted per piece (English letters; Korean syllable blocks), or a "couldn't match" message.
// With `audio`, each English word / Korean syllable is a button that plays YOUR audio for just that part.
export default function ResultSentence({ result, audio }: { result: AnalyzeResult; audio?: Audio }) {
  const { ui, t } = useUi();
  const [playing, setPlaying] = useState<string | null>(null); // which part is playing ("3" or "3-1")
  const [open, setOpen] = useState<number | null>(null); // which word's detail card is open
  const [data, setData] = useState<{ tips: TipsTable; articulation: ArticulationTable } | null>(null);
  const [dataError, setDataError] = useState<string | null>(null);
  const [native, setNative] = useState<NativeClip | null>(null); // The native clip, loaded when a card opens
  const [nativeError, setNativeError] = useState<string | null>(null);
  useEffect(() => stopPlayback, []); // leaving the result (new recording, new sentence) stops the sound
  useEffect(() => {
    if (open === null || native) return;
    let ignore = false; // a failed load is retried when a card is opened again (the clip loads -> "ready" wins)
    loadNativeClip(result.text, result.lang).then(
      (c) => !ignore && setNative(c),
      (e: Error) => !ignore && setNativeError(e.message),
    );
    return () => {
      ignore = true;
    };
  }, [open, native, result.text, result.lang]);
  const anyRed = result.words.some((w) => issuesOf(w).length > 0);
  useEffect(() => {
    if (!anyRed) return;
    let ignore = false;
    loadCardData().then(
      (d) => !ignore && setData(d),
      (e: Error) => !ignore && setDataError(e.message),
    );
    return () => {
      ignore = true;
    };
  }, [anyRed]);

  if (!result.matched) {
    return (
      <p className="rounded-lg bg-amber-50 p-3 text-amber-900 dark:bg-amber-950 dark:text-amber-200">
        {t(result.reason === "no_speech" ? "noSpeech" : "mismatch")} {t("estimated")}
      </p>
    );
  }

  // Play part of a clip: YOUR recording by default, or the native one.
  function play(key: string, start?: number | null, end?: number | null, clip: Audio | undefined = audio) {
    if (clip && playSlice(clip.samples, clip.rate, start, end, () => setPlaying((k) => (k === key ? null : k)))) {
      setPlaying(key);
    }
  }

  // The native version of word i (soundIndex null) or of one of its sounds; undefined = nothing to offer.
  function nativePlayer(i: number, key: string, soundIndex: number | null, ipa?: string) {
    if (!native) return undefined;
    const part = nativePart(native.timings, i, result.words[i].word, soundIndex, ipa);
    return part ? () => play(key, part.start, part.end, native) : undefined;
  }

  // Tap = hear your audio for that part; on a red word it ONLY opens (or closes) the card.
  function tap(i: number, key: string, start?: number | null, end?: number | null) {
    const action = tapAction(result.words[i]);
    if (action.play) play(key, start, end);
    if (action.toggleCard) {
      stopPlayback();
      setOpen((o) => (o === i ? null : i));
    }
  }

  // English: one button per word. Korean: one button per syllable block (falls back to the word's times).
  function renderWord(w: WordResult, i: number) {
    const korean = result.lang === "ko";
    const hasCard = issuesOf(w).length > 0;
    if (!audio && !hasCard) return w.display.map((piece, j) => <Piece key={j} piece={piece} />);
    if (!korean) {
      return (
        <button
          type="button"
          onClick={() => tap(i, `${i}`, w.start, w.end)}
          aria-label={t(hasCard ? "showFix" : "playYour", { w: w.word })}
          aria-expanded={hasCard ? open === i : undefined}
          className={`${TAP} ${playing === `${i}` ? PLAYING : ""}`}
        >
          {w.display.map((piece, j) => (
            <Piece key={j} piece={piece} />
          ))}
        </button>
      );
    }
    return w.display.map((piece, j) => (
      <button
        key={j}
        type="button"
        onClick={() => tap(i, `${i}-${j}`, piece.start ?? w.start, piece.end ?? w.end)}
        aria-label={t(hasCard ? "showFix" : "playYour", { w: piece.text })}
        className={`${TAP} ${playing === `${i}-${j}` ? PLAYING : ""}`}
      >
        <Piece piece={piece} />
      </button>
    ));
  }

  const { words, red } = summarize(result);
  const anyGreen = result.words.some((w) => w.status === "green");
  const notHeard = result.words.filter((w) => w.not_heard).length;
  const headline =
    red > 0
      ? t(red === 1 ? "headlineOne" : "headlineMany", { red, words, nh: notHeard ? t("notHeardCount", { n: notHeard }) : "" })
      : anyGreen
        ? t("noProblems")
        : result.checks.includes("word_heard") // heard every word, but no sound here has a check yet
          ? t("heardAll")
          : t("nothingGraded");

  return (
    <div className="flex flex-col gap-3">
      <p className="font-medium">{headline}</p>
      <p lang={result.lang} className="flex flex-wrap gap-x-3 gap-y-4 text-3xl leading-[2.2]">
        {result.words.map((w, i) => (
          <span key={i} title={w.not_heard ? t("notHeardTitle") : undefined}>
            {renderWord(w, i)}
          </span>
        ))}
      </p>
      {audio && (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          {t(result.lang === "ko" ? "tapSyllable" : "tapWord")}
          {anyRed ? t("tapRed") : "."}
        </p>
      )}
      {open !== null && dataError && <p className="text-sm text-red-600">{t("tipsError", { e: dataError })}</p>}
      {open !== null &&
        data &&
        issuesOf(result.words[open]).map((issue) => {
          const w = result.words[open];
          const card = buildCard(issue, w, data.tips, result.lang, ui);
          if (!card) return null;
          return (
            <DetailCard
              key={issue.pair}
              card={card}
              articulation={data.articulation}
              onPlaySound={audio && card.sound ? () => play(`${open}-sound`, card.sound!.start, card.sound!.end) : undefined}
              onPlayWord={audio && !w.not_heard ? () => play(`${open}`, w.start, w.end) : undefined}
              onPlayNativeSound={
                card.soundIndex !== null ? nativePlayer(open, `${open}-native-sound`, card.soundIndex, issue.ipa) : undefined
              }
              onPlayNativeWord={nativePlayer(open, `${open}-native`, null)}
              nativeStatus={native ? "ready" : nativeError ? nativeError : "loading"}
              onClose={() => setOpen(null)}
            />
          );
        })}
      <p className="text-sm text-neutral-500">
        <span className={GREEN}>{t("green")}</span>{t("greenMeans")}<span className={RED}>{t("red")}</span>
        {t("redMeans")} {describeChecksIn(ui, result.checks)}
      </p>
    </div>
  );
}
