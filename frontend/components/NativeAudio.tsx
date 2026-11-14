"use client";

import { useEffect, useRef, useState } from "react";
import { fetchTts, ttsUrl, type Lang } from "@/lib/api";

// "hear it first". Plays the native reference (Azure TTS via our backend) at normal or slower speed.
// Clips are kept in memory per page, so a second tap plays instantly without asking the backend again.
const clips = new Map<string, string>(); // ttsUrl -> object URL of the downloaded WAV

export default function NativeAudio({ text, lang }: { text: string; lang: Lang }) {
  const [busy, setBusy] = useState<"normal" | "slow" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);

  // A new sentence (or leaving the page) stops whatever is playing.
  useEffect(() => () => player.current?.pause(), [text]);

  async function play(slow: boolean) {
    setError(null);
    setBusy(slow ? "slow" : "normal");
    try {
      const key = ttsUrl(text, lang, { slow });
      let url = clips.get(key);
      if (!url) {
        url = URL.createObjectURL(await fetchTts(text, lang, { slow }));
        clips.set(key, url);
      }
      player.current?.pause();
      player.current = new Audio(url);
      await player.current.play();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const button =
    "rounded-md border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800";
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={() => play(false)} disabled={busy !== null} className={button}>
          ▶ {busy === "normal" ? "Loading…" : "Hear native"}
        </button>
        <button onClick={() => play(true)} disabled={busy !== null} className={button}>
          ▶ {busy === "slow" ? "Loading…" : "Slower"}
        </button>
        <span className="text-xs text-neutral-500">Computer voice (Azure), standard {lang === "ko" ? "Seoul Korean" : "American English"}</span>
      </div>
      {error && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>}
    </div>
  );
}
