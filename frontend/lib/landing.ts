// The type-first landing page (no React here, so node --test can check it).
import type { Lang, TextLang } from "./api.ts";

// Hangul syllable blocks, lone jamo (ㅋㅋ), and the old-style jamo block
const HANGUL = /[가-힣ㄱ-ㆎᄀ-ᇿ]/gu;
const LATIN = /[a-z]/giu;

/** Which language a typed sentence is in, from its letters: Hangul = Korean, Latin = English, both = "mix"
 * ("I want 떡볶이"). Digits and punctuation don't count; nothing to read gives null. The site language plays no part. */
export function detectLang(text: string): TextLang | null {
  const ko = text.match(HANGUL)?.length ?? 0;
  const en = text.match(LATIN)?.length ?? 0;
  if (ko && en) return "mix";
  if (!ko && !en) return null;
  return ko ? "ko" : "en";
}

/** "Practice it yourself" (record + green/red) only for one-language sentences: scoring was never measured on
 * mixed ones, and a wrong red is the worst thing this app can show. */
// The hint under Practice. Korean has its own: it says that sounds the Korean checks can't confirm stay plain.
export const practiceHintKey = (lang: Lang) => (lang === "ko" ? "practiceHintKo" : "practiceHint");
export const practiceOffered = (lang: TextLang): lang is Lang => lang !== "mix";

/** The HTML lang attribute (Korean fonts, screen readers): a mixed sentence has no single one. */
export const htmlLang = (lang: TextLang | null) => (lang === "mix" || !lang ? undefined : lang);
