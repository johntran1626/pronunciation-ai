// Turning a red word into what its detail card shows. Pure functions, tested in card.test.ts.
import type { Lang, TipsTable, WordResult } from "./api.ts";
import { tipText, tr, type Ui } from "./i18n.ts";
import { practiceFor, soundLabel } from "./sounds.ts";

// The every-sound English check (backend/any_sound.py): any sound swapped for another, or left out.
const SWAP = "sound_swap", MISSING = "sound_missing";

// One thing wrong in a word: which mistake, on which sound, and when that sound was (for replay).
// index = which sound of the word (0 = first): used to find the same sound in the native clip.
export type Issue = {
  pair: string; ipa: string; index: number; start: number | null; end: number | null;
  produced?: string | null; // what was probably said (the every-sound check names it)
};

// The red sounds of a word, one Issue per mistake type (a word with two bad R's gets one R card), in order.
// For the every-sound check the mistake is the exact swap (S said as D, T said as R: two cards).
export function issuesOf(word: WordResult): Issue[] {
  const seen = new Set<string>();
  const out: Issue[] = [];
  (word.phonemes ?? []).forEach((p, index) => {
    if (p.status !== "red" || !p.pair) return;
    const key = p.pair === SWAP || p.pair === MISSING ? `${p.pair}:${p.ipa}:${p.produced ?? ""}` : p.pair;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ pair: p.pair, ipa: p.ipa, index, start: p.start ?? null, end: p.end ?? null, produced: p.produced ?? null });
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

// A card for any English sound swapped or left out: both mouths from the sound table, plain names, practice words.
function anySoundCard(issue: Issue, word: WordResult, ui: Ui): Card | null {
  const missing = issue.pair === MISSING;
  if (!missing && !issue.produced) return null;
  const x = soundLabel(ui, issue.ipa);
  const y = missing ? null : soundLabel(ui, issue.produced!);
  return {
    pair: issue.pair,
    word: word.word,
    targetLabel: x,
    producedLabel: y,
    whatHappened: tr(ui, missing ? "missingHappened" : "swapHappened", { w: word.word, x, y: y ?? "" }),
    tip: tr(ui, missing ? "missingTip" : "swapTip", { x, y: y ?? "" }),
    practice: practiceFor(issue.ipa),
    target: { lang: "en", sym: issue.ipa },
    produced: missing ? null : { lang: "en", sym: issue.produced! },
    simple: false, // the correct mouth is always drawn (and what you probably said, for a swap)
    sound: issue.start != null && issue.end != null ? { start: issue.start, end: issue.end } : null,
    soundIndex: issue.index,
    reviewed: true, // no phonetic claim of its own: the pictures and descriptions come from the sound table
    needsNativeReview: false,
  };
}

// Issue + its word + tips.json -> the card. null when we have no tip for this mistake (never show a broken card).
export function buildCard(issue: Issue, word: WordResult, tips: TipsTable, lang: Lang, ui: Ui = "en"): Card | null {
  if (issue.pair === SWAP || issue.pair === MISSING) return anySoundCard(issue, word, ui);
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

// What hovering a red word previews: the card of each red sound that has a single target sound to draw
// (not a word that wasn't heard, not an extra vowel), so the preview can show the correct mouth.
export function hoverCards(word: WordResult, tips: TipsTable, lang: Lang, ui: Ui = "en"): Card[] {
  return issuesOf(word)
    .map((issue) => buildCard(issue, word, tips, lang, ui))
    .filter((c): c is Card => c !== null && c.target !== null);
}
