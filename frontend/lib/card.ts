// Turning a red word into what its detail card shows. Pure functions, tested in card.test.ts.
import type { ArticulationTable, Lang, TipsTable, WordResult } from "./api.ts";
import { say, tipText, tr, type Ui } from "./i18n.ts";
import { caption } from "./mouthViews.ts";
import { practiceFor, soundLabel } from "./sounds.ts";

// The every-sound checks (backend/any_sound.py, backend/korean_any_sound.py): any sound swapped for another, or left out.
const SWAP = "sound_swap", MISSING = "sound_missing";

// One thing wrong in a word: which mistake, on which sound, and when that sound was (for replay).
// index = which sound of the word (0 = first): used to find the same sound in the native clip.
export type Issue = {
  pair: string; ipa: string; index: number; start: number | null; end: number | null;
  produced?: string | null; // what was probably said (the every-sound check names it)
  unit?: string | null; // Korean: a glide + vowel judged as one sound ("jʌ" = ㅕ); both of its phonemes carry it
};

// The red sounds of a word, one Issue per mistake type (a word with two bad R's gets one R card), in order.
// For the every-sound check the mistake is the exact swap (S said as D, T said as R: two cards).
export function issuesOf(word: WordResult): Issue[] {
  const seen = new Set<string>();
  const out: Issue[] = [];
  (word.phonemes ?? []).forEach((p, index) => {
    if (p.status !== "red" || !p.pair) return;
    const key = p.pair === SWAP || p.pair === MISSING ? `${p.pair}:${p.unit ?? p.ipa}:${p.produced ?? ""}` : p.pair;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ pair: p.pair, ipa: p.ipa, index, start: p.start ?? null, end: p.end ?? null, produced: p.produced ?? null,
      ...(p.unit ? { unit: p.unit } : {}) });
  });
  return out;
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
  reviewed: boolean;
  needsNativeReview: boolean;
};

// The sound the mouth picture draws: a Korean glide + vowel ("jʌ" = ㅕ) is drawn with its vowel.
const drawn = (sym: string, lang: Lang) => (lang === "ko" && /^[jwɰ]./u.test(sym) ? sym.slice(1) : sym);

// A card for any sound swapped or left out: both mouths from the sound table, the sounds named (English: IPA with a
// familiar word for each; Korean: the jamo), and practice words. With the sound table (`sounds`), the tip repeats
// the green picture's one-line caption ("lips rounded and pushed forward, mouth almost closed"), so it says what to DO.
function anySoundCard(issue: Issue, word: WordResult, ui: Ui, lang: Lang, sounds?: ArticulationTable["sounds"]): Card | null {
  const missing = issue.pair === MISSING;
  if (!missing && !issue.produced) return null;
  const x = issue.unit ?? issue.ipa, y = issue.produced ?? "";
  const name = (sym: string) => (lang === "ko" ? soundLabel(ui, sym, "ko") : sym); // English cards keep the IPA
  const example = practiceFor(missing ? x : y, lang)[0]; // "cat" for [æ]: a word that has the sound it came out as
  const happened = missing ? (example ? "missingHappened" : "missingHappenedPlain") : example ? "swapHappened" : "swapHappenedPlain";
  const entry = sounds?.[lang][drawn(x, lang)];
  const line = entry ? caption(entry, say(ui)) : null;
  const how = line && ui === "en" ? line[0].toLowerCase() + line.slice(1) : line; // mid-sentence in English
  const tip = missing ? (how ? "missingTip" : "missingTipPlain") : how ? "swapTip" : "swapTipPlain";
  return {
    pair: issue.pair,
    word: word.word,
    targetLabel: soundLabel(ui, x, lang),
    producedLabel: missing ? null : soundLabel(ui, y, lang),
    whatHappened: tr(ui, happened, { w: word.word, x: name(x), y: name(y), ex: example ?? "" }),
    tip: tr(ui, tip, { w: word.word, x: name(x), how: how ?? "" }),
    practice: practiceFor(x, lang),
    target: { lang, sym: drawn(x, lang) },
    produced: missing ? null : { lang, sym: drawn(y, lang) },
    simple: false, // the correct mouth is always drawn (and what you probably said, for a swap)
    reviewed: true, // no phonetic claim of its own: the pictures and descriptions come from the sound table
    needsNativeReview: false,
  };
}

// Issue + its word + tips.json -> the card. null when we have no tip for this mistake (never show a broken card).
// `sounds` (articulation.json) lets the every-sound cards quote the picture's caption in their tip.
export function buildCard(issue: Issue, word: WordResult, tips: TipsTable, lang: Lang, ui: Ui = "en",
  sounds?: ArticulationTable["sounds"]): Card | null {
  if (issue.pair === SWAP || issue.pair === MISSING) return anySoundCard(issue, word, ui, lang, sounds);
  const raw = tips.tips[lang]?.[issue.pair];
  if (!raw) return null;
  const t = tipText(ui, lang, issue.pair, raw); // the words in the site language; sounds and flags unchanged
  const target = t.target ? { lang: t.target_lang, sym: t.target } : null;
  const produced = t.produced ? { lang: t.produced_lang, sym: t.produced } : null;
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

// Every red word's cards, in sentence order: the results show them all at once, top to bottom (no tapping needed).
export function allCards(words: WordResult[], tips: TipsTable, lang: Lang, ui: Ui = "en",
  sounds?: ArticulationTable["sounds"]): { wordIndex: number; issue: Issue; card: Card }[] {
  return words.flatMap((w, wordIndex) =>
    issuesOf(w).flatMap((issue) => {
      const card = buildCard(issue, w, tips, lang, ui, sounds);
      return card ? [{ wordIndex, issue, card }] : [];
    }));
}

// A sound's description without the example-word label in front ("ship: tongue a little lower..." -> "Tongue a little
// lower..."): the card already names the sound, so the label only repeats it.
export function plainDescription(text: string): string {
  const m = text.match(/^\S{1,12}\s?:\s+([\s\S]*)$/);
  if (!m) return text;
  return m[1].charAt(0).toUpperCase() + m[1].slice(1);
}
