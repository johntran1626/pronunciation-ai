// The native speaker's version of one word / sound, for the "Native" button in the detail card.
// nativePart is pure (tested in native.test.ts); loadNativeClip fetches. The backend's /tts/timings runs the same G2P as /analyze on the same text, so word
// number i and sound number k mean the same thing in both; we still check the word (and sound) to be safe.
import { fetchNativeTimings, fetchTts, ttsUrl, type Lang, type NativeTimings } from "./api.ts";
import { decodeWav16, louderForPlayback } from "./wav.ts";

export function nativePart(
  timings: NativeTimings | null,
  wordIndex: number,
  word: string,
  soundIndex: number | null, // null = the whole word
  ipa?: string, // the target sound, if known: refuse if the native clip has a different one there
): { start: number; end: number } | null {
  const w = timings?.words[wordIndex];
  if (!w || w.word.normalize("NFC") !== word.normalize("NFC")) return null; // never play the wrong word
  if (soundIndex === null) return { start: w.start, end: w.end };
  const p = w.phonemes[soundIndex];
  if (!p || (ipa !== undefined && p.ipa !== ipa)) return null;
  return { start: p.start, end: p.end };
}

// The native clip as samples (for the slice player) + its timings. Fetched once per sentence and kept for the page,
// so opening a second card (or the same one again) plays at once. A failed load is forgotten, so a retry can work.
export type NativeClip = { samples: Float32Array<ArrayBuffer>; rate: number; timings: NativeTimings };
const clips = new Map<string, Promise<NativeClip>>();

export function loadNativeClip(text: string, lang: Lang): Promise<NativeClip> {
  const key = ttsUrl(text, lang);
  let p = clips.get(key);
  if (!p) {
    p = Promise.all([fetchTts(text, lang), fetchNativeTimings(text, lang)]).then(async ([blob, timings]) => {
      const { samples, rate } = decodeWav16(await blob.arrayBuffer());
      // Same loudness as YOUR replay copy (peak 0.9), so "You" vs "Native" compares the sound, not the volume.
      return { samples: louderForPlayback(samples), rate, timings };
    });
    p.catch(() => clips.delete(key));
    clips.set(key, p);
  }
  return p;
}
