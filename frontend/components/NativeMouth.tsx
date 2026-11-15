"use client";
// "Watch the native mouth": a side view of a native speaker's tongue, lips, jaw and soft palate, animated in sync
// with the native reference clip, for any sentence (pack or typed). It shows the TARGET articulation (phonetics
// tables, timed by the aligner), never the learner's own mouth.
//
// Loaded on the first tap: the clip + its timings (lib/native.ts, the same copy the detail card's "Native" button
// uses) and the articulation table (shared with the cards). One still frame per sound (lib/animate.ts), Play starts
// at 0.5x, the slider moves frame by frame with the words under it, and landing on a frame plays just that sound.

import { useEffect, useMemo, useRef, useState } from "react";
import { CutAway } from "@/components/MouthDiagram";
import { EASE, frameIndexAt, framesFor, poseAt, soundsFromTimings, wordFrames, type Frame, type Sound } from "@/lib/animate";
import { loadCardData, type Lang } from "@/lib/api";
import { loadNativeClip } from "@/lib/native";
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

const SPEEDS = [1, 0.5, 0.25];
const SLICE_PAD = 0.02; // seconds of audio either side of one sound
const holdTime = (f: Frame) => f.start + 0.5 * (f.end - f.start); // the middle of a frame: always a still

export default function NativeMouth({ text, lang }: { text: string; lang: Lang }) {
  const [clip, setClip] = useState<Clip | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [t, setT] = useState(0);
  const [speed, setSpeed] = useState(0.5); // slow by default, so each frame can be seen
  const [playing, setPlaying] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);

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

  async function open() {
    setBusy(true);
    setError(null);
    try {
      const [native, { articulation }] = await Promise.all([loadNativeClip(text, lang), loadCardData()]);
      const { words, sounds } = soundsFromTimings(native.timings, articulation.sounds[lang]);
      const url = URL.createObjectURL(new Blob([encodeWav16(native.samples, native.rate)], { type: "audio/wav" }));
      setClip({ url, samples: native.samples, rate: native.rate, duration: native.timings.duration_s, words, sounds });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const button =
    "rounded-md border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800";

  if (!clip)
    return (
      <div className="flex flex-col gap-2">
        <div>
          <button onClick={open} disabled={busy} className={button}>
            {busy ? "Loading…" : "Watch the native mouth"}
          </button>
        </div>
        {error && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>}
      </div>
    );

  const pause = () => {
    audio.current?.pause();
    setPlaying(false);
  };
  const play = () => {
    const a = audio.current;
    if (!a) return;
    if (playing) return pause();
    stopPlayback();
    if (a.currentTime >= clip.duration - 0.01) a.currentTime = 0;
    a.playbackRate = speed;
    void a.play();
    setPlaying(true);
  };
  // jump to frame i (slider, word, sound chip): stop the clip, show the frame's still, play that sound alone
  const land = (i: number) => {
    const f = frames[i];
    if (!f) return;
    pause();
    setT(holdTime(f));
    if (audio.current) audio.current.currentTime = f.start;
    playSlice(clip.samples, clip.rate, f.start, f.end, undefined, SLICE_PAD);
  };

  const k = frameIndexAt(frames, t);
  const frame = frames[k];
  const shown = frame ? frame.sounds.map((i) => clip.sounds[i]) : [];
  const word = clip.words.findIndex((w) => t >= w.start && t <= w.end);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-neutral-200 p-3 dark:border-neutral-800" data-testid="native-mouth">
      <figure className="flex flex-col gap-1">
        <div className="mx-auto w-full max-w-sm overflow-hidden rounded-lg border-2 border-green-600" data-testid="mouth">
          <CutAway g={poseAt(frames, t, EASE * speed)} />
        </div>
        <figcaption className="text-xs text-neutral-500">
          A native speaker&apos;s target mouth position, from phonetics tables, timed to the native clip. Not your mouth.
        </figcaption>
      </figure>
      <p className="min-h-12 text-sm" data-testid="now">
        {shown[0]?.entry ? (
          <><b className="text-base">[{shown.map((s) => s.ipa).join(" ")}]</b> {shown[0].entry.description}</>
        ) : <span className="text-neutral-500">(no sounds)</span>}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={play} className="rounded-md bg-green-700 px-4 py-1.5 font-medium text-white">
          {playing ? "Pause" : "Play"}
        </button>
        {SPEEDS.map((s) => (
          <button key={s} onClick={() => { setSpeed(s); if (audio.current) audio.current.playbackRate = s; }}
            className={`rounded border px-2 py-1 text-sm ${s === speed ? "border-green-600" : "border-neutral-300 dark:border-neutral-700"}`}>
            {s}×
          </button>
        ))}
        <span className="ml-auto font-mono text-sm tabular-nums">frame {k + 1}/{frames.length}</span>
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
      <audio ref={audio} src={clip.url} preload="auto" onEnded={() => setPlaying(false)} />
    </div>
  );
}
