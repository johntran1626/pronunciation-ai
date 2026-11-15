"use client";
// The native mouth: a side view of a native speaker's tongue, lips, jaw and soft palate, animated in sync with the
// native reference clip, for any sentence (pack or typed). It shows the TARGET articulation (phonetics tables,
// timed by the aligner), never the learner's own mouth.
//
// Loads as soon as it appears: the clip + its timings (lib/native.ts, the same copy the detail card's "Native"
// button uses) and the articulation table (shared with the cards), then plays once at 1x (unless autoplay is
// off). If the browser blocks sound before any tap, it waits on Play instead. At the end, the Play button becomes
// Replay (beside the speed buttons; nothing covers the picture). The speed can change at any moment. One still frame per sound (lib/animate.ts);
// the slider moves frame by frame with the words under it, and landing on a frame plays just that sound.
// "Show what matters" (off by default) rings each sound's defining contact or shape, with a plain-words label.

import { useEffect, useMemo, useRef, useState } from "react";
import { CutAway } from "@/components/MouthDiagram";
import { useUi } from "@/components/UiLang";
import { descText, say } from "@/lib/i18n";
import {
  DEFAULT_SPEED, EASE, frameIndexAt, frameMark, framesFor, poseAt, soundsFromTimings, wordFrames, type Frame, type Sound,
} from "@/lib/animate";
import { loadCardData, type Lang } from "@/lib/api";
import { loadNativeClip } from "@/lib/native";
import { SPEEDS, changeSpeed } from "@/lib/player";
import { playSlice, stopPlayback } from "@/lib/replay";
import { encodeWav16 } from "@/lib/wav";

type Clip = {
  url: string; // the clip as a WAV object URL, for the <audio> element whose clock drives the picture
  samples: Float32Array<ArrayBuffer>;
  rate: number;
  duration: number;
  words: { word: string; start: number; end: number }[];
  sounds: Sound[];
};

const SLICE_PAD = 0.02; // seconds of audio either side of one sound
const holdTime = (f: Frame) => f.start + 0.5 * (f.end - f.start); // the middle of a frame: always a still

export default function NativeMouth({ text, lang, autoplay = true }: { text: string; lang: Lang; autoplay?: boolean }) {
  const { ui, t: tr } = useUi();
  const [clip, setClip] = useState<Clip | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0); // bumped by "Try again"
  const [t, setT] = useState(0);
  const [speed, setSpeed] = useState(DEFAULT_SPEED);
  const [playing, setPlaying] = useState(false);
  const [ended, setEnded] = useState(false);
  const [showKey, setShowKey] = useState(false); // "show what matters", off by default
  const audio = useRef<HTMLAudioElement | null>(null);
  const autoplayed = useRef(false);

  // load as soon as the player appears (and again on "Try again")
  useEffect(() => {
    let live = true;
    Promise.all([loadNativeClip(text, lang), loadCardData()]).then(
      ([native, { articulation }]) => {
        if (!live) return;
        const { words, sounds } = soundsFromTimings(native.timings, articulation.sounds[lang]);
        const url = URL.createObjectURL(new Blob([encodeWav16(native.samples, native.rate)], { type: "audio/wav" }));
        setClip({ url, samples: native.samples, rate: native.rate, duration: native.timings.duration_s, words, sounds });
      },
      (e: Error) => live && setError(e.message),
    );
    return () => { live = false; };
  }, [text, lang, attempt]);

  // the object URL lives as long as this clip is shown
  useEffect(() => () => { if (clip) URL.revokeObjectURL(clip.url); }, [clip]);

  // while playing, redraw every screen frame from the audio clock (so the picture can't drift from the sound)
  useEffect(() => {
    if (!playing) return;
    let id = 0;
    const loop = () => {
      if (audio.current) setT(audio.current.currentTime);
      id = requestAnimationFrame(loop);
    };
    id = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(id);
  }, [playing]);

  const frames = useMemo(() => (clip ? framesFor(clip.sounds) : []), [clip]);
  const spans = useMemo(() => (clip ? wordFrames(clip.words, frames) : []), [clip, frames]);

  function start() {
    const a = audio.current;
    if (!a || !clip) return;
    stopPlayback();
    if (ended || a.currentTime >= clip.duration - 0.01) a.currentTime = 0;
    a.defaultPlaybackRate = speed;
    a.playbackRate = speed;
    setEnded(false);
    a.play().then(
      () => setPlaying(true),
      () => setPlaying(false), // sound blocked until the visitor taps: Play stays on screen
    );
  }
  const pause = () => {
    audio.current?.pause();
    setPlaying(false);
  };

  if (!clip)
    return (
      <div className="flex flex-col gap-2" data-testid="native-mouth">
        {error ? (
          <p className="flex flex-wrap items-center gap-2 rounded-lg bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
            <button onClick={() => { setError(null); setAttempt((n) => n + 1); }} className="underline">{tr("tryAgain")}</button>
          </p>
        ) : (
          <div className="mx-auto flex aspect-[170/150] w-full max-w-sm animate-pulse items-center justify-center rounded-lg border-2 border-neutral-200 text-sm text-neutral-500 dark:border-neutral-800">
            {tr("mouthLoading")}
          </div>
        )}
      </div>
    );

  // jump to frame i (slider, word, sound chip): stop the clip, show the frame's still, play that sound alone
  const land = (i: number) => {
    const f = frames[i];
    if (!f) return;
    pause();
    setEnded(false);
    setT(holdTime(f));
    if (audio.current) audio.current.currentTime = f.start;
    playSlice(clip.samples, clip.rate, f.start, f.end, undefined, SLICE_PAD);
  };

  const k = frameIndexAt(frames, t);
  const frame = frames[k];
  const shown = frame ? frame.sounds.map((i) => clip.sounds[i]) : [];
  const word = clip.words.findIndex((w) => t >= w.start && t <= w.end);
  const pose = poseAt(frames, t, EASE * speed);
  const mark = showKey ? frameMark(shown, pose, say(ui)) : null;

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-neutral-200 p-3 dark:border-neutral-800" data-testid="native-mouth">
      <figure className="flex flex-col gap-1">
        <div className="mx-auto w-full max-w-sm overflow-hidden rounded-lg border-2 border-green-600" data-testid="mouth">
          <CutAway g={pose} mark={mark} />
        </div>
        <figcaption className="text-xs text-neutral-500">
          {tr("mouthCaption")}
        </figcaption>
      </figure>
      <p className="min-h-12 text-sm" data-testid="now">
        {shown[0]?.entry ? (
          <><b className="text-base">[{shown.map((s) => s.ipa).join(" ")}]</b> {descText(ui, lang, shown[0].ipa, shown[0].entry.description)}</>
        ) : <span className="text-neutral-500">{tr("noSounds")}</span>}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={playing ? pause : start} data-testid="play" className="min-w-20 rounded-md bg-green-700 px-4 py-1.5 font-medium text-white">
          {playing ? tr("pause") : ended ? `↻ ${tr("replay")}` : tr("play")}
        </button>
        {SPEEDS.map((s) => (
          <button key={s} onClick={() => { setSpeed(s); if (audio.current) void changeSpeed(audio.current, s); }} aria-pressed={s === speed}
            className={`rounded border px-2 py-1 text-sm ${s === speed ? "border-green-600" : "border-neutral-300 dark:border-neutral-700"}`}>
            {s}×
          </button>
        ))}
        <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-sm">
          <input type="checkbox" checked={showKey} onChange={(e) => setShowKey(e.target.checked)} data-testid="show-key" />
          {tr("showKey")}
        </label>
      </div>
      {/* the slider moves one frame per step; the words underneath take the width of their frames */}
      <div className="flex flex-col gap-1">
        <input type="range" min={0} max={Math.max(0, frames.length - 1)} step={1} value={k} aria-label="frame"
          onChange={(e) => land(Number(e.target.value))} />
        <div className="flex text-sm" data-testid="words" lang={lang}>
          {clip.words.map((w, i) => {
            const sp = spans[i];
            if (!sp) return null;
            return (
              <button key={i} onClick={() => land(sp.first)} style={{ flexGrow: sp.last - sp.first + 1, flexBasis: 0 }}
                className={`min-w-0 truncate border-l border-neutral-300 px-0.5 text-left dark:border-neutral-700 ${i === word ? "font-semibold text-[#c2410c] dark:text-[#fb923c]" : ""}`}>
                {w.word}
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex flex-wrap gap-1 font-mono text-xs" data-testid="frames">
        {frames.map((f, i) => (
          <button key={i} onClick={() => land(i)}
            className={`rounded px-1 ${i === k ? "bg-[#c2410c] text-white" : "bg-neutral-100 dark:bg-neutral-800"}`}>
            {f.sounds.map((j) => clip.sounds[j].ipa).join(" ")}
          </button>
        ))}
      </div>
      <audio ref={audio} src={clip.url} preload="auto"
        // plays once on its own as soon as the clip can play (autoplay on)
        onCanPlay={() => { if (!autoplayed.current) { autoplayed.current = true; if (autoplay) start(); } }}
        onEnded={() => { setPlaying(false); setEnded(true); if (audio.current) setT(audio.current.duration); }} />
    </div>
  );
}
