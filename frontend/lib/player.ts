// The native mouth player's rules (no React here, so node --test can check them).
import type { TextLang } from "./api.ts";

export const SPEEDS = [1, 0.5, 0.25];

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

/** Switch speed at any moment. While playing, the clip pauses, takes the new rate and carries on from the same
 * spot: some browsers (Safari among them) ignore a rate change on a clip that's already playing, and some fall
 * back to the default rate on play(), so both rates are set. Paused or ended: just the rate for the next play. */
export async function changeSpeed(a: Media, s: number): Promise<void> {
  a.defaultPlaybackRate = s;
  if (a.paused || a.ended) {
    a.playbackRate = s;
    return;
  }
  const at = a.currentTime;
  a.pause();
  a.playbackRate = s;
  a.currentTime = at;
  try {
    await a.play();
  } catch {} // sound blocked: Play stays on screen
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
