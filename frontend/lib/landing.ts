// The type-first landing page (no React here, so node --test can check it).
import type { Lang } from "./api.ts";
import { pickTranslation, type Translated } from "./translations.ts";

// Hangul syllable blocks, lone jamo (ㅋㅋ), and the old-style jamo block
const HANGUL = /[가-힣ㄱ-ㆎᄀ-ᇿ]/gu;
const LATIN = /[a-z]/giu;

/** Which language a typed sentence is in, from its letters: the larger share wins (a tie with any Hangul is
 * Korean). Digits and punctuation don't count; nothing to read gives null. The site language plays no part. */
export function detectLang(text: string): Lang | null {
  const ko = text.match(HANGUL)?.length ?? 0;
  const en = text.match(LATIN)?.length ?? 0;
  if (!ko && !en) return null;
  return ko >= en ? "ko" : "en";
}

// ---------- English input -> Korean ----------
/** "Translate to KR" and "Translate to KR and Animate" are offered for English input only. */
export const translateOffered = (lang: Lang | null) => lang === "en";

/** The Korean sentence to animate: whichever form the 존댓말 / 반말 switch shows. */
export const koreanToAnimate = (t: Translated, casual: boolean) => pickTranslation(t, casual)?.text ?? null;
