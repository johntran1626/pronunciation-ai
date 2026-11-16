// The native mouth player's rules (no React here, so node --test can check them).
import type { TextLang } from "./api.ts";

export const SPEEDS = [1, 0.5];

/** The speed buttons' labels: 1× and .5× (the short form fits the phone row). */
export const speedLabel = (s: number) => `${String(s).replace(/^0\./, ".")}×`;

/** How far the scrubber's fill reaches, in % of the timeline: the middle of frame k's cell (n equal cells). */
export const scrubFill = (k: number, n: number) => (n > 0 ? (100 * (k + 0.5)) / n : 0);

/** Seconds the player keeps going after the last sound (its release), before Play comes back. */
export const END_PAD = 0.05;

/** Where playback stops: just after the last sound ends. The TTS file carries up to ~1 s of silence after the voice,
 * and waiting for the file's own end left Pause on screen after the timeline had finished. Never past the file. */
export function playEnd(soundEnds: number[], duration: number): number {
  return soundEnds.length ? Math.min(duration, Math.max(...soundEnds) + END_PAD) : duration;
}

/** The bits of an <audio> element the speed change touches. */
export type Media = {
  paused: boolean;
  ended: boolean;
  currentTime: number;
  playbackRate: number;
  defaultPlaybackRate: number;
  pause(): void;
  play(): Promise<void>;
};

/** Put the chosen speed on the clip, right now, playing or not. It never pauses or seeks, so a click can't be lost
 * to a restart that's still in progress. Both rates are set because some browsers fall back to the default rate on
 * play(). Returns true only if something had to change, so the player can call it every frame to undo a browser
 * that quietly put an old speed back (on play, on replay, after the end). */
export function applySpeed(a: Media, s: number): boolean {
  if (a.playbackRate === s && a.defaultPlaybackRate === s) return false;
  a.defaultPlaybackRate = s;
  a.playbackRate = s;
  return true;
}

/** React key for the player. `run` goes up with every new animation, so animating the same sentence again still
 * makes a fresh player: back to 1x, and it plays again. */
export const playerKey = (s: { run: number; lang: TextLang; text: string }) => `mouth:${s.run}:${s.lang}:${s.text}`;

// ---------- autoplay (on by default; remembered in this browser only) ----------
export const AUTOPLAY_DEFAULT = true;
const KEY = "autoplay";
type Store = { getItem(k: string): string | null; setItem(k: string, v: string): void };

/** The saved autoplay choice; nothing saved, or storage blocked, means on. */
export function readAutoplay(store: Store | null): boolean {
  try {
    const v = store?.getItem(KEY);
    return v === "off" ? false : v === "on" ? true : AUTOPLAY_DEFAULT;
  } catch {
    return AUTOPLAY_DEFAULT;
  }
}

export function saveAutoplay(store: Store | null, on: boolean): void {
  try {
    store?.setItem(KEY, on ? "on" : "off");
  } catch {}
}
