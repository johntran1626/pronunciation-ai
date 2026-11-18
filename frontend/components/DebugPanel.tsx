"use client";

import { useEffect, useRef, useState } from "react";
import type { AnalyzeResult } from "@/lib/api";
import type { AudioStats } from "@/lib/recorder";
import { useUi } from "@/components/UiLang";

// Local blob: URLs (browser memory only). sentUrl = the exact WAV sent to /analyze; playUrl = a louder copy to listen to.
export type Sent = { sentUrl: string; playUrl: string; stats: AudioStats; playSamples: Float32Array<ArrayBuffer> };

const BTN =
  "inline-flex items-center gap-2 rounded-xl border-[2.5px] border-ink bg-white px-3 py-1.5 font-display text-base text-ink shadow-pop-xs transition-[transform,box-shadow] hover:bg-sky active:translate-x-[2px] active:translate-y-[2px] active:shadow-none";

// Under the results (green or red): the exact audio we sent, what the recognizer heard, and the raw reply.
export default function DebugPanel({ sent, result }: { sent: Sent; result?: AnalyzeResult }) {
  const { t } = useUi();
  const { seconds, peak, rmsDb } = sent.stats;
  const warnings: string[] = [];
  if (peak < 0.01) warnings.push(t("debugSilent"));
  else if (rmsDb < -45) warnings.push(t("debugQuiet"));
  if (peak >= 0.999) warnings.push(t("debugClipping"));
  const heard = result?.heard?.map((h) => h.symbol).join(" ");

  // Play / stop the louder listening copy
  const player = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  useEffect(() => () => player.current?.pause(), [sent.playUrl]);
  function toggle() {
    if (playing) {
      player.current?.pause();
      setPlaying(false);
      return;
    }
    player.current?.pause();
    const a = new Audio(sent.playUrl);
    a.onended = () => setPlaying(false);
    player.current = a;
    a.play().then(() => setPlaying(true), () => setPlaying(false));
  }

  return (
    <details open className="rounded-2xl border-[2.5px] border-ink bg-tray px-4 py-3 text-sm shadow-pop-xs">
      <summary className="cursor-pointer font-display text-lg">
        {t("debugTitle")}
      </summary>
      <div className="mt-3 flex flex-col gap-3">
        {warnings.map((w) => (
          <p key={w} className="m-0 rounded-xl border-2 border-ink bg-kakao px-3 py-2 font-medium">
            ⚠ {w}
          </p>
        ))}
        {result && (
          <p className="m-0 font-medium">
            {t("debugHeard")}{" "}
            <span className="rounded-lg border-2 border-ink bg-white px-2 py-0.5 font-mono">{heard || t("debugNothing")}</span>
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={toggle} className={BTN}>
            {playing ? t("debugStop") : t("debugPlay")}
          </button>
          <span className="font-medium tabular-nums">{seconds.toFixed(1)} s</span>
        </div>
        <a href={sent.sentUrl} download="my-recording.wav" className={`${BTN} self-start`}>
          {t("debugDownload")}
          <span className="font-sans text-xs font-medium text-neutral-600">{t("debugDownloadNote")}</span>
        </a>
        {result && (
          <details>
            <summary className="cursor-pointer font-display text-base">{t("debugJson")}</summary>
            <pre className="mt-2 max-h-80 overflow-auto rounded-xl border-2 border-ink bg-white p-2 text-xs">
              {JSON.stringify(result, null, 1)}
            </pre>
          </details>
        )}
      </div>
    </details>
  );
}
