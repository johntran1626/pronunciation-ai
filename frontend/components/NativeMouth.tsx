"use client";
// The native mouth: a side view of a native speaker's tongue, lips, jaw and soft palate, animated in sync with the
// native reference clip, for any typed sentence. It shows the TARGET articulation (phonetics tables,
// timed by the aligner), never the learner's own mouth.
//
// Loads as soon as it appears: the clip + its timings (lib/native.ts, the same copy the detail card's "Native"
// button uses) and the articulation table (shared with the cards), then plays once at 1x (unless autoplay is
// off). If the browser blocks sound before any tap, it waits on Play instead. Play/Pause only plays and pauses;
// Replay, right after it, starts again from the top. The speed can change at any moment. A small sound button in
// the top-right corner mutes the clip (the picture keeps moving). One still frame per sound (lib/animate.ts);
// the slider moves frame by frame with the words under it, and landing on a frame plays just that sound.
// "Placement tips" (off by default) rings each sound's defining contact or shape, with a plain-words label.
// Blueberry, beside the picture, says what the current sound is (IPA + plain words).
// The timeline: the words over their sounds (dashed line between words), the sounds (one equal cell per frame),
// then the scrubber; Pause / Replay / speed sit under it. A long sentence scrolls sideways inside the timeline
// (each cell keeps a readable width) and follows the sound being played.
// Layout (a CSS grid): phone = one column: picture, tip, timeline, then `actions` (the page's buttons);
// desktop = picture on the left, tip + `actions` on the right, timeline under both.

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Blueberry from "@/components/Blueberry";
import InfoTip from "@/components/InfoTip";
import { CutAway } from "@/components/MouthDiagram";
import { useUi } from "@/components/UiLang";
import { descText, say } from "@/lib/i18n";
import {
  DEFAULT_SPEED, EASE, frameIndexAt, frameMark, framesFor, poseAt, soundsFromTimings, wordFrames, type Frame, type Sound,
} from "@/lib/animate";
import { loadCardData, type TextLang } from "@/lib/api";
import { side } from "@/lib/mouthViews";
import { loadNativeClip } from "@/lib/native";
import { SPEEDS, applySpeed, scrubFill, speedLabel } from "@/lib/player";
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

type Props = {
  text: string;
  lang: TextLang;
  autoplay?: boolean;
  muted?: boolean;
  onMuted?: (m: boolean) => void;
  actions?: ReactNode; // the page's buttons (Animate another, Practice), placed by the layout below
};

// the chunky buttons of the look: black outline, offset shadow that presses in
const POP = "border-[2.5px] border-ink shadow-pop-sm transition-[transform,box-shadow] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none";

export default function NativeMouth({ text, lang, autoplay = true, muted = false, onMuted, actions }: Props) {
  const { ui, t: tr } = useUi();
  const [clip, setClip] = useState<Clip | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0); // bumped by "Try again"
  const [t, setT] = useState(0);
  const [speed, setSpeed] = useState(DEFAULT_SPEED);
  const speedNow = useRef(DEFAULT_SPEED); // the same speed, for the clock and the audio events (never a stale copy)
  const [playing, setPlaying] = useState(false);
  const [ended, setEnded] = useState(false);
  const [showKey, setShowKey] = useState(false); // "placement tips", off by default
  const audio = useRef<HTMLAudioElement | null>(null);
  const strip = useRef<HTMLDivElement | null>(null); // the timeline's sideways scroller
  const autoplayed = useRef(false);

  // load as soon as the player appears (and again on "Try again")
  useEffect(() => {
    let live = true;
    Promise.all([loadNativeClip(text, lang), loadCardData()]).then(
      ([native, { articulation }]) => {
        if (!live) return;
        const { words, sounds } = soundsFromTimings(native.timings, articulation.sounds);
        const url = URL.createObjectURL(new Blob([encodeWav16(native.samples, native.rate)], { type: "audio/wav" }));
        setClip({ url, samples: native.samples, rate: native.rate, duration: native.timings.duration_s, words, sounds });
      },
      (e: Error) => live && setError(e.message),
    );
    return () => { live = false; };
  }, [text, lang, attempt]);

  // the object URL lives as long as this clip is shown
  useEffect(() => () => { if (clip) URL.revokeObjectURL(clip.url); }, [clip]);

  // while playing, redraw every screen frame from the audio clock (so the picture can't drift from the sound),
  // and keep the chosen speed on the clip in case the browser put an old one back
  useEffect(() => {
    if (!playing) return;
    let id = 0;
    const loop = () => {
      if (audio.current) {
        applySpeed(audio.current, speedNow.current);
        setT(audio.current.currentTime);
      }
      id = requestAnimationFrame(loop);
    };
    id = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(id);
  }, [playing]);

  // the sound button (React only sets `muted` on the first render, so keep the element in step)
  useEffect(() => { if (audio.current) audio.current.muted = muted; }, [muted, clip]);

  const frames = useMemo(() => (clip ? framesFor(clip.sounds) : []), [clip]);
  const spans = useMemo(() => (clip ? wordFrames(clip.words, frames) : []), [clip, frames]);
  const k = frameIndexAt(frames, t);
  // every different tip this clip can show (one per set of sounds), so the bubble is sized for the longest
  // and the timeline under it doesn't jump while the clip plays
  const tips = useMemo(() => {
    const seen = new Map<string, Sound[]>();
    if (clip) for (const f of frames) {
      const s = f.sounds.map((i) => clip.sounds[i]);
      seen.set(tipKey(s), s);
    }
    return [...seen.values()];
  }, [clip, frames]);

  // a long sentence: keep the current sound's cell in view inside the timeline (never scrolls the page)
  useEffect(() => {
    const el = strip.current;
    if (!el || !frames.length || el.scrollWidth <= el.clientWidth) return;
    const cell = el.scrollWidth / frames.length;
    const left = k * cell;
    if (left < el.scrollLeft || left + cell > el.scrollLeft + el.clientWidth) el.scrollLeft = left - (el.clientWidth - cell) / 2;
  }, [k, frames.length]);

  // nothing keeps sounding once the player is gone (Animate another, a new sentence)
  useEffect(() => () => stopPlayback(), []);

  // play from where it is (from the top once it has ended); `fromTop` = Replay
  function start(fromTop = false) {
    const a = audio.current;
    if (!a || !clip) return;
    stopPlayback();
    if (fromTop || ended || a.currentTime >= clip.duration - 0.01) a.currentTime = 0;
    applySpeed(a, speedNow.current);
    setEnded(false);
    a.play().then(
      () => { applySpeed(a, speedNow.current); setPlaying(true); }, // some browsers reset the rate on play()
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
          <p className="flex flex-wrap items-center gap-2 rounded-2xl border-[2.5px] border-ink bg-[#FFE4EF] px-4 py-3 font-medium shadow-pop-xs" role="alert">
            {error}
            <button onClick={() => { setError(null); setAttempt((n) => n + 1); }} className="underline">{tr("tryAgain")}</button>
          </p>
        ) : (
          <div className="flex h-[236px] animate-pulse items-center justify-center rounded-[20px] border-[2.5px] border-ink bg-tray font-medium shadow-pop lg:h-[420px] lg:rounded-3xl lg:shadow-pop-lg">
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
    if (!muted) playSlice(clip.samples, clip.rate, f.start, f.end, undefined, SLICE_PAD);
  };

  const frame = frames[k];
  const shown = frame ? frame.sounds.map((i) => clip.sounds[i]) : [];
  const word = clip.words.findIndex((w) => t >= w.start && t <= w.end);
  const pose = poseAt(frames, t, EASE * speed);
  const mark = showKey ? frameMark(shown, pose, say(ui)) : null;
  // blue air waves only for a sound that pushes out a gust of air (ㅋ, English p); a merged frame takes its biggest
  const puff = Math.max(0, ...shown.map((s) => (s.entry ? side(s.entry).puff : 0)));

  // what Blueberry says for a set of sounds: the IPA in blue, then the plain-words description
  const tip = (s: Sound[]) => s[0]?.entry ? (
    <><b className="font-display text-base font-normal text-blue lg:block lg:text-xl">[{s.map((x) => x.ipa).join(" ")}]</b>{" "}
      {descText(ui, s[0].lang, s[0].ipa, s[0].entry.description)}</>
  ) : <span className="text-neutral-500">{tr("noSounds")}</span>;

  // the slider's thumb lands on the middle of each sound's cell: inset it by half a cell minus half the thumb
  const inset = frames.length ? `calc(${50 / frames.length}% - var(--thumb) / 2)` : "0px";

  return (
    <div data-testid="native-mouth"
      className="grid grid-cols-1 gap-3.5 [grid-template-areas:'mouth'_'side'_'timeline'_'actions'] lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)] lg:gap-x-7 lg:gap-y-[18px] lg:[grid-template-areas:'mouth_side'_'mouth_actions'_'timeline_timeline']">
      {/* the picture, in its card, with the sound button in the corner */}
      <div className="relative flex items-center justify-center rounded-[20px] border-[2.5px] border-ink bg-tray px-4 py-3 shadow-pop [grid-area:mouth] lg:min-h-[420px] lg:rounded-3xl lg:px-20 lg:py-6 lg:shadow-pop-lg">
        <button type="button" onClick={() => onMuted?.(!muted)} aria-pressed={muted} aria-label={tr(muted ? "soundOn" : "soundOff")}
          title={tr(muted ? "soundOn" : "soundOff")} data-testid="sound"
          className={`absolute right-3 top-3 grid size-11 place-items-center rounded-xl bg-white text-ink lg:right-3.5 lg:top-3.5 lg:size-12 lg:rounded-[14px] ${POP}`}>
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M11 5 6 9H3v6h3l5 4z" />
            {muted ? <path d="m16 9 5 6m0-6-5 6" /> : <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" />}
          </svg>
        </button>
        <div className="w-full max-w-[460px]" data-testid="mouth">
          <CutAway g={pose} mark={mark} look="pop" puff={puff} />
        </div>
      </div>

      {/* Blueberry's tip for the sound on screen, then Placement tips */}
      <div className="flex min-w-0 flex-col gap-3 [grid-area:side] lg:gap-[18px] lg:self-end">
        <div className="flex items-end gap-2 lg:gap-2.5">
          <div className="nod flex-none">
            <Blueberry width={62} talking={playing} className="h-auto w-[46px] lg:w-[62px]" />
          </div>
          <p className="m-0 grid min-w-0 flex-1 rounded-[16px_16px_16px_4px] border-[2.5px] border-ink bg-white px-3 py-2 text-[15px] leading-[1.35] font-medium lg:rounded-[18px_18px_18px_4px] lg:px-4 lg:py-3 lg:text-[17px] lg:leading-[1.4] lg:shadow-pop-sm">
            {/* invisible copies of every tip hold the bubble at its biggest size */}
            {tips.map((s, i) => <span key={i} aria-hidden="true" className="invisible [grid-area:1/1]">{tip(s)}</span>)}
            <span className="[grid-area:1/1]" data-testid="now">{tip(shown)}</span>
          </p>
        </div>
        <div className="flex items-center gap-2 lg:gap-2.5">
          <button type="button" role="switch" aria-checked={showKey} onClick={() => setShowKey(!showKey)} data-testid="show-key"
            className="flex items-center gap-2 text-sm font-semibold lg:gap-2.5 lg:text-base">
            <span className={`relative inline-block h-6 w-[42px] rounded-full border-[2.5px] border-ink transition-colors lg:h-7 lg:w-12 ${showKey ? "bg-pink" : "bg-white"}`}>
              <span className={`absolute top-[2px] size-[15px] rounded-full bg-ink transition-all lg:top-[3px] lg:size-[17px] ${showKey ? "left-5 lg:left-[23px]" : "left-[2px] lg:left-[3px]"}`} />
            </span>
            {tr("placementTips")}
          </button>
          <InfoTip text={tr("placementInfo")} label={tr("infoAbout", { name: tr("placementTips") })} opens="right" />
        </div>
      </div>

      {/* the timeline: words over their sounds, the sounds (one equal cell per frame), the scrubber; then the controls */}
      <div className="flex min-w-0 flex-col [grid-area:timeline] lg:mt-2">
        <div ref={strip} className="overflow-x-auto [--cell:30px] lg:[--cell:44px]">
          <div className="flex flex-col gap-1.5 py-1 lg:gap-2" style={{ minWidth: `calc(${frames.length} * var(--cell))` }}>
            {/* each word placed by percentage: it starts at its first sound and spans its sounds (gaps stay gaps) */}
            <div className="relative h-7 font-display text-[17px] lg:h-9 lg:text-[22px]" data-testid="words" lang={lang === "mix" ? undefined : lang}>
              {clip.words.map((w, i) => {
                const sp = spans[i];
                if (!sp) return null;
                return (
                  <button key={i} onClick={() => land(sp.first)}
                    style={{ left: `${(100 * sp.first) / frames.length}%`, width: `${(100 * (sp.last - sp.first + 1)) / frames.length}%` }}
                    className={`absolute inset-y-0 truncate px-1 text-center ${i > 0 ? "rounded-r-lg border-l-[3px] border-dashed border-ink" : "rounded-lg"} ${i === word ? "bg-sky" : ""}`}>
                    {w.word}
                  </button>
                );
              })}
            </div>
            {/* no gap between cells (the words row has none), so the columns line up exactly; the chip sits inside */}
            <div className="flex text-[13px] font-semibold lg:text-[17px]" data-testid="frames">
              {frames.map((f, i) => {
                const ipa = f.sounds.map((j) => clip.sounds[j].ipa).join(" ");
                return (
                  <button key={i} onClick={() => land(i)} title={ipa} style={{ width: `${100 / frames.length}%` }} className="shrink-0 px-[1.5px] lg:px-[3px]">
                    <span className={`block overflow-hidden rounded-lg border-[2.5px] border-ink py-[5px] text-center whitespace-nowrap lg:rounded-[10px] lg:py-2 ${i === k ? "bg-pink" : "bg-white"}`}>
                      {ipa}
                    </span>
                  </button>
                );
              })}
            </div>
            {/* the scrubber: the bar draws the outline + pink fill; the range input on top only carries the thumb */}
            <div className="relative mt-1 h-3 rounded-full border-[2.5px] border-ink bg-white lg:mt-1.5 lg:h-3.5">
              <div className="h-full rounded-full bg-pink" style={{ width: `${scrubFill(k, frames.length)}%` }} />
              <input type="range" min={0} max={Math.max(0, frames.length - 1)} step={1} value={k} aria-label={tr("frame")}
                className="scrub absolute top-1/2 -translate-y-1/2 [--thumb:18px] lg:[--thumb:22px]"
                style={{ left: inset, width: `calc(100% - 2 * (${inset}))` }} onChange={(e) => land(Number(e.target.value))} />
            </div>
          </div>
        </div>

        <div className="mt-3 flex items-center gap-2 lg:mt-4 lg:justify-center lg:gap-3">
          <button onClick={playing ? pause : () => start()} data-testid="play"
            className={`flex h-[46px] flex-none items-center gap-2 rounded-[14px] bg-blue px-3.5 font-display text-[19px] text-white lg:h-[52px] lg:px-[22px] lg:text-[21px] ${POP}`}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              {playing ? <><rect x="5" y="4" width="5" height="16" rx="1.5" /><rect x="14" y="4" width="5" height="16" rx="1.5" /></> : <path d="M7 4.5v15a1 1 0 0 0 1.5.86l12-7.5a1 1 0 0 0 0-1.72l-12-7.5A1 1 0 0 0 7 4.5Z" />}
            </svg>
            {playing ? tr("pause") : tr("play")}
          </button>
          <button onClick={() => start(true)} data-testid="replay"
            className={`h-[46px] flex-none rounded-[14px] bg-white px-3 font-display text-[19px] text-ink lg:h-[52px] lg:px-[18px] lg:text-[21px] ${POP}`}>
            ↻ {tr("replay")}
          </button>
          <div role="group" aria-label={tr("speed")}
            className="flex min-w-[76px] flex-1 overflow-hidden rounded-xl border-[2.5px] border-ink lg:w-[220px] lg:flex-none lg:rounded-[14px] lg:shadow-pop-sm">
            {SPEEDS.map((s, i) => (
              <button key={s} onClick={() => { setSpeed(s); speedNow.current = s; if (audio.current) applySpeed(audio.current, s); }} aria-pressed={s === speed}
                className={`h-[41px] flex-1 font-display text-[15px] lg:h-[47px] lg:text-lg ${i ? "border-l-[2.5px] border-ink" : ""} ${s === speed ? "bg-ink text-white" : "bg-white text-ink"}`}>
                {speedLabel(s)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {actions && <div className="mt-2 flex flex-col gap-2.5 [grid-area:actions] lg:mt-0 lg:gap-3 lg:self-start">{actions}</div>}
      <audio ref={audio} src={clip.url} preload="auto" muted={muted}
        // plays once on its own as soon as the clip can play (autoplay on)
        onCanPlay={() => { if (!autoplayed.current) { autoplayed.current = true; if (autoplay) start(); } }}
        onPlaying={() => { if (audio.current) applySpeed(audio.current, speedNow.current); }}
        onEnded={() => { setPlaying(false); setEnded(true); if (audio.current) setT(audio.current.duration); }} />
    </div>
  );
}

// the same sounds give the same tip (an IPA + language list identifies it)
const tipKey = (s: Sound[]) => s.map((x) => `${x.lang}:${x.ipa}`).join(" ");
