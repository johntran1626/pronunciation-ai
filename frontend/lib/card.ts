// Turning a red word into what its detail card shows. Pure functions, tested in card.test.ts.
import type { Lang, TipsTable, WordResult } from "./api.ts";
import { tipText, type Ui } from "./i18n.ts";

// One thing wrong in a word: which mistake, on which sound, and when that sound was (for replay).
// index = which sound of the word (0 = first): used to find the same sound in the native clip.
export type Issue = { pair: string; ipa: string; index: number; start: number | null; end: number | null };

// The red sounds of a word, one Issue per mistake type (a word with two bad R's gets one R card), in order.
export function issuesOf(word: WordResult): Issue[] {
  const seen = new Set<string>();
  const out: Issue[] = [];
  (word.phonemes ?? []).forEach((p, index) => {
    if (p.status !== "red" || !p.pair || seen.has(p.pair)) return;
    seen.add(p.pair);
    out.push({ pair: p.pair, ipa: p.ipa, index, start: p.start ?? null, end: p.end ?? null });
  });
  return out;
}

// What a tap on a word does. A word with a card opens / closes it and stays quiet (the card has
// its own replay buttons); any other word plays your audio for that part.
export function tapAction(word: WordResult): { play: boolean; toggleCard: boolean } {
  const hasCard = issuesOf(word).length > 0;
  return { play: !hasCard, toggleCard: hasCard };
}

export type Sound = { lang: Lang; sym: string }; // a key into articulation.json
export type Card = {
  pair: string;
  word: string;
  targetLabel: string;
  producedLabel: string | null;
  whatHappened: string;
  tip: string;
  practice: string[];
  target: Sound | null;
  produced: Sound | null;
  simple: boolean; // no mouth diagrams (word not heard, extra vowel): there's no single target sound to draw
  sound: { start: number; end: number } | null; // just the bad sound in YOUR recording (null: nothing to play)
  soundIndex: number | null; // Which sound of the word it is (null: no single sound, e.g. word not heard)
  reviewed: boolean;
  needsNativeReview: boolean;
};

// Issue + its word + tips.json -> the card. null when we have no tip for this mistake (never show a broken card).
export function buildCard(issue: Issue, word: WordResult, tips: TipsTable, lang: Lang, ui: Ui = "en"): Card | null {
  const raw = tips.tips[lang]?.[issue.pair];
  if (!raw) return null;
  const t = tipText(ui, lang, issue.pair, raw); // the words in the site language; sounds and flags unchanged
  const target = t.target ? { lang: t.target_lang, sym: t.target } : null;
  const produced = t.produced ? { lang: t.produced_lang, sym: t.produced } : null;
  const notHeard = issue.pair === "word_not_heard";
  return {
    pair: issue.pair,
    word: word.word,
    targetLabel: t.target_label,
    producedLabel: t.produced_label,
    whatHappened: t.what_happened.replace("{word}", word.word),
    tip: t.tip,
    practice: t.practice,
    target,
    produced,
    simple: !target || !produced,
    sound: !notHeard && issue.start != null && issue.end != null ? { start: issue.start, end: issue.end } : null,
    soundIndex: notHeard ? null : issue.index,
    reviewed: t.reviewed,
    needsNativeReview: t.needs_native_review ?? false,
  };
}
