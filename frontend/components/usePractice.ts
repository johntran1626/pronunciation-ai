"use client";
// The Practice button's whole job, as a hook: press -> 3, 2, 1 -> recording (press again to stop, or 15 s) ->
// analyzing -> the result. A too-short or silent recording is not sent: it comes back as `empty` so the page can say
// so (Blueberry's bubble) and the button is ready again. The mic opens on the press (so a permission prompt comes
// first and no sound is lost), and the countdown part is cut off the recording (lib/practice.ts trimCountdown).

import { useEffect, useRef, useState } from "react";
import { analyze, type AnalyzeResult, type Lang } from "@/lib/api";
import { tr, type Ui } from "@/lib/i18n";
import { COUNTDOWN_MS, countdownDigit, emptyRecording, MIN_SECONDS, trimCountdown } from "@/lib/practice";
import { MAX_SECONDS, startRecording, toWav16k, type Recording } from "@/lib/recorder";
import type { Sent } from "./DebugPanel";

export type Phase =
  | { kind: "idle" }
  | { kind: "countdown"; digit: 3 | 2 | 1 }
  | { kind: "recording"; elapsed: number }
  | { kind: "analyzing" };

export type Outcome =
  | { kind: "done"; result: AnalyzeResult; sent: Sent; id: number }
  | { kind: "error"; message: string; sent?: Sent; id: number }
  | { kind: "empty"; why: "short" | "silent"; id: number }; // not analyzed

type NoId<T> = T extends unknown ? Omit<T, "id"> : never; // each kind of Outcome, before it gets its id

// a browser error as something a user can act on
function micErrorMessage(e: unknown, ui: Ui): string {
  const name = (e as { name?: string })?.name;
  if (name === "NotAllowedError") return tr(ui, "micDenied");
  if (name === "NotFoundError") return tr(ui, "micMissing");
  return (e as Error)?.message ?? String(e);
}

export function usePractice(text: string, lang: Lang, ui: Ui) {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const rec = useRef<Recording | null>(null);
  const t0 = useRef(0); // when the mic opened (performance.now)
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const outcomes = useRef(0);
  const urls = useRef<string[]>([]);

  const finish = (o: NoId<Outcome>) => setOutcome({ ...o, id: ++outcomes.current } as Outcome);

  // leaving the sentence mid-recording releases the mic and frees the recording's URLs
  useEffect(() => () => {
    clearInterval(timer.current);
    rec.current?.stop();
    rec.current = null;
    urls.current.forEach((u) => URL.revokeObjectURL(u));
  }, []);

  async function start() {
    if (!navigator.mediaDevices?.getUserMedia) return finish({ kind: "error", message: tr(ui, "cantRecord") });
    try {
      rec.current = await startRecording();
    } catch (e) {
      return finish({ kind: "error", message: micErrorMessage(e, ui) });
    }
    t0.current = performance.now();
    setPhase({ kind: "countdown", digit: 3 });
    timer.current = setInterval(() => {
      const ms = performance.now() - t0.current;
      const digit = countdownDigit(ms);
      if (digit) return setPhase({ kind: "countdown", digit });
      const elapsed = (ms - COUNTDOWN_MS) / 1000;
      if (elapsed >= MAX_SECONDS) return void stop(); // the hard 15 s cap (after the countdown)
      setPhase({ kind: "recording", elapsed });
    }, 50);
  }

  async function stop() {
    const r = rec.current;
    if (!r) return; // already stopped (a press and the 15 s cap can race)
    rec.current = null;
    clearInterval(timer.current);
    const raw = await r.stop();
    const samples = trimCountdown(raw.samples, raw.sampleRate, COUNTDOWN_MS / 1000);
    if (samples.length < MIN_SECONDS * raw.sampleRate) { // stopped during the countdown, or a mis-tap
      setPhase({ kind: "idle" });
      return finish({ kind: "empty", why: "short" });
    }
    setPhase({ kind: "analyzing" });
    let sent: Sent | undefined;
    try {
      const { wav, playback, playbackSamples, stats } = await toWav16k({ samples, sampleRate: raw.sampleRate });
      const why = emptyRecording(stats);
      if (why) {
        setPhase({ kind: "idle" });
        return finish({ kind: "empty", why });
      }
      urls.current.forEach((u) => URL.revokeObjectURL(u));
      urls.current = [URL.createObjectURL(wav), URL.createObjectURL(playback)];
      sent = { sentUrl: urls.current[0], playUrl: urls.current[1], stats, playSamples: playbackSamples };
      const result = await analyze(wav, text, lang);
      finish({ kind: "done", result, sent });
    } catch (e) {
      finish({ kind: "error", message: (e as Error).message, sent });
    }
    setPhase({ kind: "idle" });
  }

  // the one button: idle -> start; countdown or recording -> stop; analyzing -> nothing
  const press = () => (phase.kind === "idle" ? start() : phase.kind === "analyzing" ? undefined : stop());
  return { phase, outcome, press };
}
