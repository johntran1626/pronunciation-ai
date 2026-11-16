// Native reference audio: the whole sentence with its timings (the animation), and single words said on their own
// (the detail card's "Native" button and practice words). wordToSay is pure (tested in native.test.ts).
import { fetchNativeTimings, fetchTts, ttsUrl, type NativeTimings, type TextLang } from "./api.ts";
import { decodeWav16, louderForPlayback } from "./wav.ts";

/** A word from the sentence, ready to be said ON ITS OWN by the native voice: the punctuation around it goes
 * ("standing." -> "standing", "“soup”," -> "soup"); apostrophes and hyphens inside it stay (don't, red-eye's). */
export function wordToSay(word: string): string {
  return word.normalize("NFC").replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
}

// A native clip as samples, at the same loudness as YOUR replay copy (peak 0.9), so "You" vs "Native" compares the
// sound, not the volume. Fetched once per text and kept for the page; a failed load is forgotten, so a retry works.
type Samples = { samples: Float32Array<ArrayBuffer>; rate: number };
const audios = new Map<string, Promise<Samples>>();

export function loadNativeAudio(text: string, lang: TextLang): Promise<Samples> {
  const key = ttsUrl(text, lang);
  let p = audios.get(key);
  if (!p) {
    p = fetchTts(text, lang).then(async (blob) => {
      const { samples, rate } = decodeWav16(await blob.arrayBuffer());
      return { samples: louderForPlayback(samples), rate };
    });
    p.catch(() => audios.delete(key));
    audios.set(key, p);
  }
  return p;
}

// The native clip as samples (for the slice player) + its timings. Fetched once per sentence and kept for the page,
// so opening a second card (or the same one again) plays at once. A failed load is forgotten, so a retry can work.
export type NativeClip = { samples: Float32Array<ArrayBuffer>; rate: number; timings: NativeTimings };
const clips = new Map<string, Promise<NativeClip>>();

export function loadNativeClip(text: string, lang: TextLang): Promise<NativeClip> {
  const key = ttsUrl(text, lang);
  let p = clips.get(key);
  if (!p) {
    p = Promise.all([loadNativeAudio(text, lang), fetchNativeTimings(text, lang)]).then(([audio, timings]) => ({ ...audio, timings }));
    p.catch(() => clips.delete(key));
    clips.set(key, p);
  }
  return p;
}
