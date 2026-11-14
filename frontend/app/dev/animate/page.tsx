"use client";
// DEV ONLY (prototype, stop-motion frames): /dev/animate plays a NATIVE recording with a side-view mouth
// animation in sync. Data: frontend/public/spike/*.json from spikes/f_animation.py (aligner times + poses).
// /dev/animate?s=1&t=0.85 opens sentence 1 frozen at 0.85 s (for screenshots). Not linked from the app.
//
// One still frame per sound (lib/animate.ts framesFor / poseAt), Play starts
// at 0.5x, the slider moves frame by frame with the words under it, tapping a word jumps to its first frame, and
// landing on a frame plays just that sound (lib/replay.ts playSlice).

import { useEffect, useMemo, useRef, useState } from "react";
import { CutAway } from "@/components/MouthDiagram";
import { EASE, frameIndexAt, framesFor, poseAt, wordFrames, type Frame, type Sound } from "@/lib/animate";
import { playSlice, stopPlayback } from "@/lib/replay";

type Clip = {
  name: string; lang: "en" | "ko"; text: string; source: string; audio: string; duration: number;
  words: { word: string; start: number; end: number }[]; sounds: Sound[];
};

const SPEEDS = [1, 0.5, 0.25];
const SLICE_PAD = 0.02; // seconds of audio either side of one sound
const holdTime = (f: Frame) => f.start + 0.5 * (f.end - f.start); // the middle of a frame: always a still

export default function DevAnimate() {
  const [clips, setClips] = useState<Clip[]>([]);
  const [pick, setPick] = useState(0);
  const [t, setT] = useState(0);
  const [speed, setSpeed] = useState(0.5); // Slow by default, so each frame can be seen
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const pcm = useRef<{ name: string; samples: Float32Array<ArrayBuffer>; rate: number } | null>(null);

  useEffect(() => {
    fetch("/spike/index.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("run spikes/f_animation.py first"))))
      .then((names: string[]) => Promise.all(names.map((n) => fetch(`/spike/${n}.json`).then((r) => r.json()))))
      .then((cs: Clip[]) => {
        setClips(cs);
        const q = new URLSearchParams(window.location.search);
        if (q.get("s")) setPick(Number(q.get("s")));
        if (q.get("t")) setT(Number(q.get("t")));
      }, (e: Error) => setError(e.message));
  }, []);

  const clip = clips[pick];
  const frames = useMemo(() => (clip ? framesFor(clip.sounds) : []), [clip]);
  const spans = useMemo(() => (clip ? wordFrames(clip.words, frames) : []), [clip, frames]);

  // the clip's audio as samples, so one sound can be played on its own (decoded once per clip)
  useEffect(() => {
    if (!clip || pcm.current?.name === clip.name) return;
    let gone = false;
    fetch(clip.audio)
      .then((r) => r.arrayBuffer())
      .then((b) => new AudioContext().decodeAudioData(b))
      .then((buf) => {
        if (!gone) pcm.current = { name: clip.name, samples: new Float32Array(buf.getChannelData(0)), rate: buf.sampleRate };
      })
      .catch(() => {}); // no slices then; the full clip still plays
    return () => { gone = true; };
  }, [clip]);

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

  if (error) return <main className="p-8 text-red-700">{error}</main>;
  if (!clip) return <main className="p-8">Loading…</main>;

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
  // jump to frame i (slider, word, chip): stop the clip, show the frame's still, play that sound alone
  const land = (i: number) => {
    const f = frames[i];
    if (!f) return;
    pause();
    setT(holdTime(f));
    if (audio.current) audio.current.currentTime = f.start;
    const p = pcm.current;
    if (p?.name === clip.name) playSlice(p.samples, p.rate, f.start, f.end, undefined, SLICE_PAD);
  };

  const k = frameIndexAt(frames, t);
  const frame = frames[k];
  const shown = frame ? frame.sounds.map((i) => clip.sounds[i]) : [];
  const word = clip.words.findIndex((w) => t >= w.start && t <= w.end);

  return (
    <main className="mx-auto flex w-full max-w-xl flex-col gap-4 px-4 py-8">
      <p className="rounded bg-amber-100 p-3 text-sm text-amber-900 dark:bg-amber-900 dark:text-amber-100">
        Dev prototype. Target articulation from phonetics tables, timed to a native recording. Not a
        measurement of the speaker&apos;s mouth.
      </p>
      <div className="flex flex-wrap gap-2">
        {clips.map((c, i) => (
          <button key={c.name} onClick={() => { pause(); stopPlayback(); setPick(i); setT(0); }}
            className={`rounded border px-2 py-1 text-sm ${i === pick ? "border-green-600 bg-green-50 dark:bg-green-950" : "border-neutral-300"}`}>
            {c.lang === "ko" ? "Korean" : "English"} {i + 1}
          </button>
        ))}
      </div>
      <figure className="flex flex-col gap-1">
        <div className="overflow-hidden rounded-lg border-2 border-green-600" data-testid="mouth">
          <CutAway g={poseAt(frames, t, EASE * speed)} />
        </div>
        <figcaption className="text-xs text-neutral-500">Target position (native speaker), not your mouth</figcaption>
      </figure>
      <p className="h-12 text-sm" data-testid="now">
        {shown[0]?.entry ? (
          <><b className="text-base">[{shown.map((s) => s.ipa).join(" ")}]</b> {shown[0].entry.description}</>
        ) : <span className="text-neutral-500">(no sounds)</span>}
      </p>
      <div className="flex items-center gap-3">
        <button onClick={play} className="rounded bg-green-700 px-4 py-2 font-medium text-white">{playing ? "Pause" : "Play"}</button>
        {SPEEDS.map((s) => (
          <button key={s} onClick={() => { setSpeed(s); if (audio.current) audio.current.playbackRate = s; }}
            className={`rounded border px-2 py-1 text-sm ${s === speed ? "border-green-600" : "border-neutral-300"}`}>{s}×</button>
        ))}
        <span className="ml-auto font-mono text-sm tabular-nums">frame {k + 1}/{frames.length}</span>
      </div>
      {/* the slider moves one frame per step; the words underneath take the width of their frames */}
      <div className="flex flex-col gap-1">
        <input type="range" min={0} max={Math.max(0, frames.length - 1)} step={1} value={k} aria-label="frame"
          onChange={(e) => land(Number(e.target.value))} />
        <div className="flex text-sm" data-testid="words">
          {clip.words.map((w, i) => {
            const sp = spans[i];
            if (!sp) return null;
            return (
              <button key={i} onClick={() => land(sp.first)} style={{ flexGrow: sp.last - sp.first + 1, flexBasis: 0 }}
                className={`min-w-0 truncate border-l border-neutral-300 px-0.5 text-left ${i === word ? "font-semibold text-[#c2410c] dark:text-[#fb923c]" : ""}`}>
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
      <p className="text-xs text-neutral-500">{clip.text} · {clip.source}</p>
      <audio ref={audio} src={clip.audio} preload="auto" onEnded={() => setPlaying(false)} />
    </main>
  );
}
