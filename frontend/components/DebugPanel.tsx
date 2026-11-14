import type { AnalyzeResult } from "@/lib/api";
import type { AudioStats } from "@/lib/recorder";

// Local blob: URLs (browser memory only). sentUrl = the exact WAV sent to /analyze; playUrl = a louder copy to listen to.
export type Sent = { sentUrl: string; playUrl: string; stats: AudioStats; playSamples: Float32Array<ArrayBuffer> };

// DEBUG (added while chasing "always green"): what audio did we really send, and what did the model hear?
export default function DebugPanel({ sent, result }: { sent: Sent; result?: AnalyzeResult }) {
  const { micRate, seconds, peak, rmsDb } = sent.stats;
  const warnings: string[] = [];
  if (peak < 0.01) warnings.push("Almost silent: the mic may be muted, the wrong input, or blocked by the browser.");
  else if (rmsDb < -45) warnings.push("Very quiet: move closer or raise the input level (System Settings → Sound → Input).");
  if (peak >= 0.999) warnings.push("Clipping: the input is too loud.");
  const heard = result?.heard?.map((h) => h.symbol).join(" ");

  return (
    <details open className="rounded-lg border border-dashed border-neutral-400 p-3 text-sm">
      <summary className="cursor-pointer font-medium">Debug: what was sent and heard</summary>
      <div className="mt-2 flex flex-col gap-2">
        <p className="tabular-nums">
          Mic {micRate} Hz → sent 16000 Hz · {seconds.toFixed(2)} s · peak {peak.toFixed(3)} · loudness{" "}
          {rmsDb.toFixed(1)} dBFS
        </p>
        {warnings.map((w) => (
          <p key={w} className="text-amber-700 dark:text-amber-400">
            ⚠ {w}
          </p>
        ))}
        {result && (
          <p>
            Recognizer heard: <span className="font-mono">{heard || "(nothing)"}</span>
          </p>
        )}
        <audio controls src={sent.playUrl} className="w-full" />
        <p className="text-neutral-500">The player is volume-boosted for listening; the analysis used the original level.</p>
        <a href={sent.sentUrl} download="my-recording.wav" className="self-start underline">
          Download the exact recording that was analyzed (WAV, stays on your computer)
        </a>
        {result && (
          <details>
            <summary className="cursor-pointer text-neutral-500">Raw JSON</summary>
            <pre className="mt-2 max-h-80 overflow-auto rounded bg-neutral-100 p-2 text-xs dark:bg-neutral-900">
              {JSON.stringify(result, null, 1)}
            </pre>
          </details>
        )}
      </div>
    </details>
  );
}
