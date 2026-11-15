// The type-first landing page (no React here, so node --test can check it).
import type { Lang } from "./api.ts";
import { bySpeech, pickTranslation, type Translated } from "./translations.ts";

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

/** The sample packs shown beside the box: Basics and Casual, both languages. */
export const SAMPLE_PACKS: Record<Lang, string[]> = { en: ["en-basics", "en-casual"], ko: ["ko-basics", "ko-casual"] };

type Leveled = { speech?: "존댓말" | "반말" };
/** A pack's sample lines. Korean packs hold both speech levels: Basics offers the polite (존댓말) lines, Casual the
 * casual (반말) ones, since that's how each setting is spoken. Packs without levels (English) show every line. */
export function sampleLines<T extends Leveled>(pack: { id: string; items: T[] }): T[] {
  return bySpeech(pack.items, pack.id.endsWith("-casual"));
}

type SamplePack<T> = { id: string; name: string; lang: Lang; items: T[] };

/** The sample dropdown for one language: one group per pack, holding that pack's sample lines. */
export function sampleGroups<T extends Leveled>(packs: SamplePack<T>[], lang: Lang) {
  return packs.filter((p) => p.lang === lang).map((p) => ({ id: p.id, name: p.name, items: sampleLines(p) }));
}

/** The line picked in the dropdown (by item id), with its language; null if it isn't there. */
export function findSample<T extends Leveled & { id: string }>(packs: SamplePack<T>[], id: string) {
  for (const p of packs) {
    const item = p.items.find((i) => i.id === id);
    if (item) return { item, lang: p.lang };
  }
  return null;
}

// ---------- English input -> Korean ----------
/** "Translate to KR" and "Translate to KR and Animate" are offered for English input only. */
export const translateOffered = (lang: Lang | null) => lang === "en";

type Stored = { text: string; translation: string | null; translation_informal?: string | null };
/** An English sample already carries its Korean (both forms), so no translate call is needed, unless the box
 * was edited after picking it. null = ask the backend. */
export function storedTranslation(item: Stored | null, text: string): Translated | null {
  if (!item || item.text !== text || !item.translation) return null;
  return { translation: item.translation, translation_informal: item.translation_informal ?? null };
}

/** The Korean sentence to animate: whichever form the 존댓말 / 반말 switch shows. */
export const koreanToAnimate = (t: Translated, casual: boolean) => pickTranslation(t, casual)?.text ?? null;
