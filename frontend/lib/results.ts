// Turning an /analyze result into what the screen shows. Pure functions, tested in results.test.ts.
import type { AnalyzeResult, DisplayPiece } from "./api.ts";
import { decompose, type JamoPart } from "./hangul.ts";

// For a RED Korean block: its letters, each marked red or not. null = nothing to break down
// (a green piece, or not a Hangul block, e.g. English letters).
export function jamoParts(piece: DisplayPiece): (JamoPart & { red: boolean })[] | null {
  if (piece.status !== "red") return null;
  const parts = decompose(piece.text);
  if (!parts) return null;
  return parts.map((p) => ({
    ...p,
    // Prefer the slot (onset/vowel/coda): 각 has ㄱ twice. Fall back to the letter if there are no slots.
    red: piece.red_slots ? piece.red_slots.includes(p.slot) : (piece.red_jamo ?? []).includes(p.jamo),
  }));
}

export function summarize(result: AnalyzeResult): { words: number; red: number } {
  return { words: result.words.length, red: result.words.filter((w) => w.status === "red").length };
}

// The honesty line under every result, built from the backend's list of live checks.
const CHECK_WORDS: Record<string, string> = {
  sentence_match: "that you read the sentence",
  word_heard: "that each word was heard",
  r_as_l: "R (said like L)",
  l_as_r: "L (said like R)",
  f_as_p: "F (said like P)",
  v_as_b: "V (said like B)",
  th_as_s: "TH (said like S or T)",
  dh_as_d: "TH (said like D)",
  ih_as_iy: "short i (ship vs sheep)",
  iy_as_ih: "long ee (sheep vs ship)",
  extra_vowel: "extra vowels after final consonants",
};

export function describeChecks(checks: string[]): string {
  if (checks.length === 0) return "No checks are switched on yet, so nothing was graded.";
  const parts = checks.map((c) => CHECK_WORDS[c] ?? c);
  const list =
    parts.length === 1
      ? parts[0]
      : parts.length === 2
        ? `${parts[0]} and ${parts[1]}`
        : `${parts.slice(0, -1).join(", ")}, and ${parts[parts.length - 1]}`;
  return `This version checks ${list}. Plain text = not checked yet.`;
}
