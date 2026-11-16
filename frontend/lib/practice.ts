// The Practice button is the record button: press -> 3, 2, 1 -> recording (press again to stop) -> analyzing.
// Pure parts, tested in practice.test.ts; the button itself lives in app/page.tsx (usePractice in components/).

export const COUNTDOWN_MS = 2300; // "3 2 1" takes about 2.3 s on screen (faster than real seconds: less waiting)
export const PRE_ROLL = 0.15; // seconds kept from before the countdown ended, so an early first sound isn't cut
export const MIN_SECONDS = 0.7; // shorter than this is a mis-tap, not a sentence
const SILENT_PEAK = 0.01; // the loudest moment never got above this: muted / wrong mic (same as the debug panel)
const SILENT_RMS_DB = -60; // or the whole recording is this quiet on average: a tick or a click, then nothing

/** The digit to show this many milliseconds into the countdown (null = the countdown is over: record). */
export function countdownDigit(ms: number): 3 | 2 | 1 | null {
  if (ms >= COUNTDOWN_MS) return null;
  return (3 - Math.floor((3 * ms) / COUNTDOWN_MS)) as 3 | 2 | 1;
}

/** The mic opens when the button is pressed, so the countdown is in the recording: cut it off (keeping PRE_ROLL).
 * countdownEnd = seconds from the start of the recording to the end of the countdown. */
export function trimCountdown(samples: Float32Array<ArrayBuffer>, rate: number, countdownEnd: number): Float32Array<ArrayBuffer> {
  if (countdownEnd <= 0) return samples;
  return samples.slice(Math.min(samples.length, Math.round(Math.max(0, countdownEnd - PRE_ROLL) * rate)));
}

/** A recording not worth analyzing: "short" (under MIN_SECONDS) or "silent" (no real sound); null = analyze it. */
export function emptyRecording(stats: { seconds: number; peak: number; rmsDb: number }): "short" | "silent" | null {
  if (stats.seconds < MIN_SECONDS) return "short";
  if (stats.peak < SILENT_PEAK || stats.rmsDb < SILENT_RMS_DB) return "silent";
  return null;
}
