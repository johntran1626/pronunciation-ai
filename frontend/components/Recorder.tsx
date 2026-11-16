"use client";

import { useEffect, useRef, useState } from "react";
import { useUi } from "@/components/UiLang";
import { analyze, type AnalyzeResult, type Lang } from "@/lib/api";
import { SHOW_DEV } from "@/lib/devOnly";
import { tr, type Ui } from "@/lib/i18n";
import { MAX_SECONDS, startRecording, TARGET_RATE, toWav16k, type Recording } from "@/lib/recorder";
import DebugPanel, { type Sent } from "./DebugPanel";
import ResultSentence from "./ResultSentence";

type State =
  | { kind: "idle" }
  | { kind: "recording"; elapsed: number }
  | { kind: "working"; what: string }
  | { kind: "done"; result: AnalyzeResult; sent: Sent }
  | { kind: "error"; message: string; sent?: Sent }; // sent = the audio we sent, for the debug panel

// Turn a browser error into something a user can act on.
function micErrorMessage(e: unknown, ui: Ui): string {
  const name = (e as { name?: string })?.name;
  if (name === "NotAllowedError") return tr(ui, "micDenied");
  if (name === "NotFoundError") return tr(ui, "micMissing");
  return (e as Error)?.message ?? String(e);
}

// Record -> stop (or auto-stop at 15 s) -> convert to WAV -> POST /analyze -> paint the result.
export default function Recorder({ text, lang }: { text: string; lang: Lang }) {
  const { ui, t } = useUi();
  const [state, setState] = useState<State>({ kind: "idle" });
  const recording = useRef<Recording | null>(null); // the live recording, if any
  const timers = useRef<{ tick?: ReturnType<typeof setInterval>; limit?: ReturnType<typeof setTimeout> }>({});

  // The last recording as a playable URL (browser memory only; never uploaded anywhere except /analyze).
  const audioUrls = useRef<string[]>([]);
  function newAudioUrls(...blobs: Blob[]) {
    audioUrls.current.forEach((u) => URL.revokeObjectURL(u)); // free the previous recording
    audioUrls.current = blobs.map((b) => URL.createObjectURL(b));
    return audioUrls.current;
  }

  function clearTimers() {
    clearInterval(timers.current.tick);
    clearTimeout(timers.current.limit);
  }

  // If the user picks another sentence mid-recording, this component goes away: release the mic.
  useEffect(
    () => () => {
      clearTimers();
      recording.current?.stop();
      recording.current = null;
      audioUrls.current.forEach((u) => URL.revokeObjectURL(u));
    },
    [],
  );

  async function start() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setState({ kind: "error", message: t("cantRecord") });
      return;
    }
    try {
      recording.current = await startRecording();
    } catch (e) {
      setState({ kind: "error", message: micErrorMessage(e, ui) });
      return;
    }
    const startedAt = performance.now();
    setState({ kind: "recording", elapsed: 0 });
    timers.current.tick = setInterval(
      () => setState({ kind: "recording", elapsed: (performance.now() - startedAt) / 1000 }),
      100,
    );
    timers.current.limit = setTimeout(stop, MAX_SECONDS * 1000); // hard 15 s cap
  }

  async function stop() {
    const rec = recording.current;
    if (!rec) return; // already stopped (button click and the 15 s timer can race)
    recording.current = null;
    clearTimers();
    let sent: Sent | undefined;
    try {
      setState({ kind: "working", what: t("preparing") });
      const { wav, playback, playbackSamples, stats } = await toWav16k(await rec.stop());
      const [sentUrl, playUrl] = newAudioUrls(wav, playback);
      sent = { sentUrl, playUrl, stats, playSamples: playbackSamples };
      setState({ kind: "working", what: t("analyzing") });
      setState({ kind: "done", result: await analyze(wav, text, lang), sent });
    } catch (e) {
      setState({ kind: "error", message: (e as Error).message, sent });
    }
  }

  const busy = state.kind === "working";
  const button =
    "flex h-[50px] items-center gap-2 rounded-2xl border-[2.5px] border-ink px-5 font-display text-xl shadow-pop-sm transition-[transform,box-shadow] active:translate-x-[3px] active:translate-y-[3px] active:shadow-pop-xs disabled:opacity-60 lg:h-[54px] lg:text-[21px]";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        {state.kind === "recording" ? (
          <button onClick={stop} className={`${button} bg-pink text-ink`}>
            ■ {t("stop")}
          </button>
        ) : (
          <button onClick={start} disabled={busy} className={`${button} bg-blue text-white`}>
            ● {t(state.kind === "done" || state.kind === "error" ? "recordAgain" : "record")}
          </button>
        )}
        {state.kind === "recording" && (
          <span className="font-display text-lg tabular-nums">
            {state.elapsed.toFixed(1)} s / {MAX_SECONDS} s
          </span>
        )}
        {state.kind === "working" && <span className="font-medium text-neutral-600">{state.what}</span>}
      </div>

      {state.kind === "error" && (
        <>
          <p className="m-0 rounded-2xl border-[2.5px] border-ink bg-[#FFE4EF] px-4 py-3 font-medium text-ink shadow-pop-xs" role="alert">{state.message}</p>
          {/* developer output: local `next dev` only, never on the public site */}
          {SHOW_DEV && state.sent && <DebugPanel sent={state.sent} />}
        </>
      )}

      {state.kind === "done" && (
        <div className="flex flex-col gap-4">
          <ResultSentence result={state.result} audio={{ samples: state.sent.playSamples, rate: TARGET_RATE }} />
          {SHOW_DEV && <DebugPanel sent={state.sent} result={state.result} />}
        </div>
      )}
    </div>
  );
}
