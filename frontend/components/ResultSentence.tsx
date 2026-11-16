"use client"; // Tapping a word plays it. Every red word's detail card is open under the sentence; hovering a red word previews the mouth

import { useEffect, useState } from "react";
import DetailCard from "@/components/DetailCard";
import MouthDiagram from "@/components/MouthDiagram";
import { useUi } from "@/components/UiLang";
import { loadCardData, type AnalyzeResult, type ArticulationTable, type DisplayPiece, type Lang, type TipsTable, type WordResult } from "@/lib/api";
import { allCards, hoverCards, issuesOf } from "@/lib/card";
import { loadNativeAudio, wordToSay } from "@/lib/native";
import { compareEnd, playSlice, stopPlayback } from "@/lib/replay";
import { GREEN_STYLE, jamoParts, pieceStyle, RED_STYLE, summarize } from "@/lib/results";

const RED = RED_STYLE;
const GREEN = GREEN_STYLE;
const TAP = "cursor-pointer rounded-lg px-1 hover:bg-tray focus-visible:outline-2 focus-visible:outline-blue";
const PLAYING = "bg-sky hover:bg-sky";
const PREVIEW_W = 300; // px: the hover preview's width

type Audio = { samples: Float32Array<ArrayBuffer>; rate: number }; // the learner's own recording (louder copy)

function Piece({ piece }: { piece: DisplayPiece }) {
  const parts = jamoParts(piece);
  if (!parts) return <span className={pieceStyle(piece.status)}>{piece.text}</span>;
  // A red Korean block: the block itself, with its letters written small above it and the wrong one(s) in red.
  return (
    <ruby className={RED}>
      {piece.text}
      <rt className="text-[0.5em] tracking-wider no-underline">
        {parts.map((p, i) => (
          <span key={i} className={p.red ? "text-red-600" : "text-neutral-400"}>
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
  const [data, setData] = useState<{ tips: TipsTable; articulation: ArticulationTable } | null>(null);
  const [dataError, setDataError] = useState<string | null>(null);
  const [sayError, setSayError] = useState<{ card: string; message: string } | null>(null); // a native clip that failed
  const [hover, setHover] = useState<{ i: number; right: boolean } | null>(null); // the red word under the mouse
  useEffect(() => stopPlayback, []); // leaving the result (new recording, new sentence) stops the sound
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
      <p className="m-0 rounded-2xl border-[2.5px] border-ink bg-kakao px-4 py-3 font-medium text-ink shadow-pop-xs">
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

  // The whole of a clip (a native word said on its own)
  const playAll = (key: string, clip: Audio) => play(key, 0, clip.samples.length / clip.rate, clip);

  // The native voice saying a word on its own (the card's word or a practice word): fetched on the first tap, then
  // kept, so it plays at once after that. Fetching on tap (not when the cards appear) keeps a sentence with many red
  // words under the limit for new audio.
  function sayNative(text: string, lang: Lang, key: string, card: string) {
    setSayError(null);
    loadNativeAudio(text, lang).then((clip) => playAll(key, clip), (e: Error) => setSayError({ card, message: e.message }));
  }

  // Tap = hear your audio for that part (red words too: their cards are already open below).
  function tap(key: string, start?: number | null, end?: number | null) {
    setHover(null);
    play(key, start, end);
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
          onClick={() => tap(`${i}`, w.start, w.end)}
          aria-label={t("playYour", { w: w.word })}
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
        onClick={() => tap(`${i}-${j}`, piece.start ?? w.start, piece.end ?? w.end)}
        aria-label={t("playYour", { w: piece.text })}
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

  // Hovering a red word with a mouse: a snapshot of the correct mouth for its red sound(s), opening toward the
  // side with room. Touch screens skip it (a tap opens the full card); it hides while that word's card is open.
  function previewOf(w: WordResult, i: number) {
    if (!data || hover?.i !== i) return null;
    const cards = hoverCards(w, data.tips, result.lang, ui);
    if (!cards.length) return null;
    return (
      <div role="tooltip"
        className={`pointer-events-none absolute top-full z-30 mt-1 flex flex-col gap-2 rounded-2xl border-[2.5px] border-ink bg-white p-2 font-sans text-base leading-normal font-normal tracking-normal text-ink no-underline shadow-pop-sm ${hover.right ? "right-0" : "left-0"}`}
        style={{ width: PREVIEW_W }}>
        {cards.map((c) => {
          const entry = data.articulation.sounds[c.target!.lang][c.target!.sym];
          return entry ? <MouthDiagram key={c.pair} compact entry={entry} title={t("targetTag")} /> : null;
        })}
        <span className="px-1 text-xs font-medium text-neutral-600">{t("hoverHint")}</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-[20px] border-[2.5px] border-ink bg-white shadow-pop lg:rounded-3xl lg:shadow-pop-lg">
        <div className="flex flex-col gap-1 px-4 pt-3 pb-2 lg:px-6 lg:pt-5">
          <p className="m-0 font-display text-xl lg:text-2xl">{headline}</p>
          <div lang={result.lang} className="flex flex-wrap gap-x-2 gap-y-1 font-display text-[34px] leading-[1.9] lg:gap-x-3 lg:text-[46px]">
            {result.words.map((w, i) => (
              <span key={i} className="relative" title={w.not_heard ? t("notHeardTitle") : undefined}
                onPointerEnter={(e) => {
                  if (e.pointerType !== "mouse" || !issuesOf(w).length) return;
                  const left = e.currentTarget.getBoundingClientRect().left;
                  setHover({ i, right: left + PREVIEW_W > window.innerWidth - 16 });
                }}
                onPointerLeave={() => setHover((h) => (h?.i === i ? null : h))}>
                {renderWord(w, i)}
                {previewOf(w, i)}
              </span>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-1 rounded-b-[17.5px] border-t-[2.5px] border-ink bg-tray px-4 py-2.5 text-sm font-medium text-neutral-700 lg:rounded-b-[21.5px] lg:px-6 lg:py-3">
          {audio && (
            <p className="m-0">
              {t(result.lang === "ko" ? "tapSyllable" : "tapWord")}.
            </p>
          )}
          <p className="m-0 text-neutral-600">
            <span className={GREEN}>{t("green")}</span>{t("greenMeans")}<span className={RED}>{t("red")}</span>
            {t("redMeans")}
          </p>
        </div>
      </div>
      {anyRed && dataError && <p className="m-0 rounded-2xl border-[2.5px] border-ink bg-[#FFE4EF] px-4 py-3 text-sm font-medium shadow-pop-xs">{t("tipsError", { e: dataError })}</p>}
      {data &&
        allCards(result.words, data.tips, result.lang, ui, data.articulation.sounds).map(({ wordIndex: i, issue, card }) => {
          const w = result.words[i];
          const id = `${i}-${issue.pair}-${issue.ipa}-${issue.produced ?? ""}`;
          return (
            <DetailCard
              key={id}
              card={card}
              articulation={data.articulation}
              onPlayWord={audio && !w.not_heard && w.start != null && w.end != null ? () => play(`${id}-yours`, w.start, compareEnd(w.start!, w.end!)) : undefined}
              onPlayNativeWord={() => sayNative(wordToSay(w.word), result.lang, `${id}-native`, id)}
              onPlayPractice={(p) => sayNative(p, card.target?.lang ?? result.lang, `practice:${p}`, id)}
              playing={playing?.startsWith("practice:") ? playing.slice(9) : null}
              error={sayError?.card === id ? sayError.message : undefined}
            />
          );
        })}
    </div>
  );
}
