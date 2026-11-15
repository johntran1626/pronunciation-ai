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
  const button = "rounded-md px-4 py-2 font-medium text-white disabled:opacity-50";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        {state.kind === "recording" ? (
          <button onClick={stop} className={`${button} bg-red-600 hover:bg-red-700`}>
            ■ {t("stop")}
          </button>
        ) : (
          <button onClick={start} disabled={busy} className={`${button} bg-blue-600 hover:bg-blue-700`}>
            ● {t(state.kind === "done" || state.kind === "error" ? "recordAgain" : "record")}
          </button>
        )}
        {state.kind === "recording" && (
          <span className="tabular-nums text-neutral-600 dark:text-neutral-300">
            {state.elapsed.toFixed(1)} s / {MAX_SECONDS} s
          </span>
        )}
        {state.kind === "working" && <span className="text-neutral-500">{state.what}</span>}
      </div>

      {state.kind === "error" && (
        <>
          <p className="rounded-lg bg-red-50 p-3 text-red-700 dark:bg-red-950 dark:text-red-300">{state.message}</p>
          {/* developer output: local `next dev` only, never on the public site */}
          {SHOW_DEV && state.sent && <DebugPanel sent={state.sent} />}
        </>
      )}

      {state.kind === "done" && (
        <div className="flex flex-col gap-3 border-t border-neutral-200 pt-4 dark:border-neutral-800">
          <ResultSentence result={state.result} audio={{ samples: state.sent.playSamples, rate: TARGET_RATE }} />
          {SHOW_DEV && <DebugPanel sent={state.sent} result={state.result} />}
        </div>
      )}
    </div>
  );
}
