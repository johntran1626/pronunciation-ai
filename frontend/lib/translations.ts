// Which Korean form to show: 존댓말 (polite) by default; a small switch flips to 반말 (casual).
// Used by pack sentences and Custom mode. Something with one translation (a Korean pack line's English meaning,
// Korean -> English in Custom mode) shows it as is; nothing (dev packs) gives null.

export type Translated = { translation: string | null; translation_informal?: string | null };
export type Shown = { form: "존댓말" | "반말" | null; text: string };

export const hasBothForms = (t: Translated) => Boolean(t.translation && t.translation_informal);

export function pickTranslation(t: Translated, casual: boolean): Shown | null {
  if (!t.translation) return null;
  if (!hasBothForms(t)) return { form: null, text: t.translation };
  return casual ? { form: "반말", text: t.translation_informal as string } : { form: "존댓말", text: t.translation };
}
