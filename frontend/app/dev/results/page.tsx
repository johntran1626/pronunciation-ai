// DEV ONLY: /dev/results shows HAND-MADE fake results, to check the green/red painting by eye.
// Needed because real Korean results are always green in v1 (no learner data to validate Korean reds). Not linked from the app.
import ResultSentence from "@/components/ResultSentence";
import type { AnalyzeResult, DisplayPiece, WordResult } from "@/lib/api";

type Red = Record<number, Pick<DisplayPiece, "red_jamo" | "red_slots">>; // block index -> what's wrong

function koreanWord(word: string, red: Red = {}): WordResult {
  const display: DisplayPiece[] = [...word].map((ch, i) =>
    red[i]
      ? { text: ch, status: "red", ...red[i] }
      : { text: ch, status: "green", red_jamo: [], red_slots: [] },
  );
  return { word, status: Object.keys(red).length ? "red" : "green", start: 0, end: 0, display };
}

function englishWord(pieces: [string, "green" | "red"][]): WordResult {
  return {
    word: pieces.map((p) => p[0]).join(""),
    status: pieces.some((p) => p[1] === "red") ? "red" : "green",
    start: 0,
    end: 0,
    display: pieces.map(([text, status]) => ({ text, status })),
  };
}

// "From now on we're pals." with the R in "From" marked red (as if said like L).
const BASE = { matched: true, reason: null, checks: ["sentence_match", "word_heard", "r_as_l"] } as const;

const ENGLISH: AnalyzeResult = {
  ...BASE,
  checks: [...BASE.checks],
  text: "From now on we're pals.",
  lang: "en",
  duration_s: 2,
  words: [
    {
      ...englishWord([["F", "green"], ["r", "red"], ["om", "green"]]),
      phonemes: [ // The red sound says which mistake, so tapping "From" opens its card
        { ipa: "f", status: "green", start: 0, end: 0.1 },
        { ipa: "ɹ", status: "red", pair: "r_as_l", produced: "l", start: 0.1, end: 0.2 },
        { ipa: "ʌ", status: "green", start: 0.2, end: 0.3 },
        { ipa: "m", status: "green", start: 0.3, end: 0.4 },
      ],
    },
    englishWord([["now", "green"]]),
    englishWord([["on", "green"]]),
    englishWord([["we're", "green"]]),
    englishWord([["pals", "green"]]),
  ],
};

// A dev-pack sentence. 엉 has ㅇ twice (silent start, [ŋ] end): only the END one is marked red.
// 날's final ㄹ is red too. (Fake errors, for the display only.)
const KOREAN: AnalyzeResult = {
  ...BASE,
  checks: ["sentence_match"],
  text: "낯선 곳에 묵다 보니 누굴 만날 때 차림새가 엉망이었다",
  lang: "ko",
  duration_s: 4,
  words: [
    koreanWord("낯선"),
    koreanWord("곳에"),
    koreanWord("묵다"),
    koreanWord("보니"),
    koreanWord("누굴"),
    koreanWord("만날", { 1: { red_jamo: ["ㄹ"], red_slots: ["coda"] } }),
    koreanWord("때"),
    koreanWord("차림새가"),
    koreanWord("엉망이었다", { 0: { red_jamo: ["ㅇ"], red_slots: ["coda"] } }),
  ],
};

const ALL_GREEN: AnalyzeResult = { ...ENGLISH, words: ENGLISH.words.map((w) => englishWord([[w.word, "green"]])) };

// States: a skipped word, a recording that didn't match, and nothing checked (Korean today).
const SKIPPED: AnalyzeResult = {
  ...ENGLISH,
  words: ENGLISH.words.map((w) =>
    w.word === "now"
      ? {
          ...englishWord([["now", "red"]]),
          not_heard: true,
          phonemes: [
            { ipa: "n", status: "red", pair: "word_not_heard", produced: null, start: 0.4, end: 0.5 },
            { ipa: "aʊ", status: "red", pair: "word_not_heard", produced: null, start: 0.5, end: 0.6 },
          ],
        }
      : englishWord([[w.word, "green"]]),
  ),
};
const NO_MATCH: AnalyzeResult = { ...ENGLISH, matched: false, reason: "mismatch" };
const NO_SPEECH: AnalyzeResult = { ...ENGLISH, matched: false, reason: "no_speech" };
const UNCHECKED: AnalyzeResult = {
  ...KOREAN,
  words: KOREAN.words.map((w) => ({ ...w, status: "unchecked", display: w.display.map((d) => ({ ...d, status: "unchecked" })) })),
};

export default function DevResults() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-10 px-4 py-12">
      <p className="rounded bg-amber-100 p-3 text-amber-900 dark:bg-amber-900 dark:text-amber-100">
        DEV ONLY: fake, hand-made results to check the colors. Not real analysis. Tap the red &quot;From&quot; or
        &quot;now&quot; to open a detail card (all cards: /dev/cards).
      </p>
      <ResultSentence result={ENGLISH} />
      <ResultSentence result={KOREAN} />
      <ResultSentence result={ALL_GREEN} />
      <ResultSentence result={SKIPPED} />
      <ResultSentence result={NO_MATCH} />
      <ResultSentence result={NO_SPEECH} />
      <ResultSentence result={UNCHECKED} />
    </main>
  );
}
