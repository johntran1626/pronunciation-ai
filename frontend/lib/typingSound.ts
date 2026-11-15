// Typewriter sounds for the home page, made on the spot with the Web Audio API (no audio files to download).
// Browsers only allow sound after the visitor clicks, taps or presses a key, so unlock() is called from the
// first such gesture; until then play() does nothing.
import type { TypingSound } from "./home.ts";

let ctx: AudioContext | null = null;
let noise: AudioBuffer | null = null;

/** Make (or wake) the audio context. Call from a click / tap / key handler. */
export function unlock() {
  try {
    ctx ??= new AudioContext();
    if (ctx.state === "suspended") void ctx.resume();
    if (!noise) {
      // 0.3 s of white noise, reused by every click
      noise = ctx.createBuffer(1, Math.floor(ctx.sampleRate * 0.3), ctx.sampleRate);
      const d = noise.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    }
  } catch {} // no Web Audio: stay silent
}

/** A burst of filtered noise: short and bright = a key; long and sweeping = the carriage sliding back. */
function burst(c: AudioContext, at: number, length: number, freq: number, toFreq: number, volume: number) {
  const src = c.createBufferSource();
  src.buffer = noise;
  const band = c.createBiquadFilter();
  band.type = "bandpass";
  band.Q.value = 1.2;
  band.frequency.setValueAtTime(freq, at);
  band.frequency.exponentialRampToValueAtTime(toFreq, at + length);
  const gain = c.createGain();
  gain.gain.setValueAtTime(volume, at);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + length);
  src.connect(band).connect(gain).connect(c.destination);
  src.start(at, Math.random() * 0.2, length);
}

/** A small bell: a high sine that fades out. */
function bell(c: AudioContext, at: number) {
  const osc = c.createOscillator();
  osc.frequency.value = 2093; // C7
  const gain = c.createGain();
  gain.gain.setValueAtTime(0.05, at);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.7);
  osc.connect(gain).connect(c.destination);
  osc.start(at);
  osc.stop(at + 0.7);
}

export function play(sound: TypingSound) {
  if (!ctx || !noise || ctx.state !== "running") return;
  const now = ctx.currentTime;
  if (sound === "key") burst(ctx, now, 0.03, 2600 + Math.random() * 900, 1800, 0.12); // a little variety per key
  else if (sound === "ding") bell(ctx, now);
  else burst(ctx, now, 0.28, 900, 3000, 0.07); // the carriage zips back
}
